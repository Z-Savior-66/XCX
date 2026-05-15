import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_py.core.fetcher_runtime import (
    acquire_group_runtime,
    close_all_group_runtimes,
    evaluate_runtime_health,
    invalidate_group_runtime,
    record_runtime_failure,
    record_runtime_success,
    runtime_recycle_reason,
)
from desktop_py.core.models import AccountConfig


class FakeSyncManager:
    def __init__(self):
        self.exited = False

    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback):
        self.exited = True


class FakePage:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True
        return None

    def is_closed(self):
        return self.closed


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.storage_state_calls: list[tuple[str | None, bool]] = []

    def new_page(self):
        return self.page

    def storage_state(self, path=None, indexed_db=False):
        self.storage_state_calls.append((path, indexed_db))

    def close(self):
        return None


class FakeBrowser:
    def close(self):
        return None


def sync_playwright_fn():
    return FakeSyncManager()


def create_browser_context_fn(_playwright, _account, _headless, _profile_dir):
    return FakeBrowser(), FakeContext()


class FetcherRuntimeTestCase(unittest.TestCase):
    def tearDown(self):
        close_all_group_runtimes()

    def test_slow_runtime_creation_does_not_block_other_group(self):
        started = threading.Event()
        release = threading.Event()
        errors: list[Exception] = []

        account_a = AccountConfig(name="账号A", state_path="storage/a.json")
        account_b = AccountConfig(name="账号B", state_path="storage/b.json")

        def slow_create(_playwright, account, _headless, _profile_dir):
            if account.name == "账号A":
                started.set()
                release.wait(timeout=2)
            return FakeBrowser(), FakeContext()

        def acquire_a():
            try:
                acquire_group_runtime(
                    account_a,
                    headless=True,
                    profile_dir="",
                    sync_playwright_fn=sync_playwright_fn,
                    create_browser_context_fn=slow_create,
                )
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=acquire_a)
        thread.start()
        self.assertTrue(started.wait(timeout=1))

        runtime_b = acquire_group_runtime(
            account_b,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=slow_create,
        )

        release.set()
        thread.join(timeout=2)

        self.assertEqual(errors, [])
        self.assertEqual(runtime_b.group_key, "storage/b.json")

    def test_slow_runtime_invalidation_does_not_block_other_group(self):
        close_started = threading.Event()
        release_close = threading.Event()
        account_a = AccountConfig(name="账号A", state_path="storage/a.json")
        account_b = AccountConfig(name="账号B", state_path="storage/b.json")
        runtime_a = acquire_group_runtime(
            account_a,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=create_browser_context_fn,
        )

        def slow_close(_runtime):
            close_started.set()
            release_close.wait(timeout=2)

        thread = threading.Thread(target=lambda: invalidate_group_runtime(runtime_a, "失效"))
        with patch("desktop_py.core.fetcher_runtime._close_runtime", side_effect=slow_close):
            thread.start()
            self.assertTrue(close_started.wait(timeout=1))
            runtime_b = acquire_group_runtime(
                account_b,
                headless=True,
                profile_dir="",
                sync_playwright_fn=sync_playwright_fn,
                create_browser_context_fn=create_browser_context_fn,
            )
            release_close.set()
            thread.join(timeout=2)

        self.assertEqual(runtime_b.group_key, "storage/b.json")
        self.assertFalse(runtime_a.valid)
        self.assertFalse(runtime_a.busy)

    def test_failed_runtime_creation_does_not_poison_group_key(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        calls = 0

        def flaky_create(_playwright, _account, _headless, _profile_dir):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("启动失败")
            return FakeBrowser(), FakeContext()

        with self.assertRaisesRegex(RuntimeError, "启动失败"):
            acquire_group_runtime(
                account,
                headless=True,
                profile_dir="",
                sync_playwright_fn=sync_playwright_fn,
                create_browser_context_fn=flaky_create,
            )

        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=flaky_create,
        )

        self.assertEqual(runtime.group_key, "storage/a.json")
        self.assertEqual(calls, 2)

    def test_close_all_group_runtimes_persists_regular_state_file(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        context = FakeContext()

        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=lambda *_args: (FakeBrowser(), context),
        )
        self.assertEqual(runtime.state_path, Path(account.state_path))
        self.assertTrue(runtime.persist_state)

        close_all_group_runtimes()

        self.assertEqual(context.storage_state_calls, [("storage\\a.json", True)])

    def test_close_all_group_runtimes_persists_shared_profile_state_file(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        context = FakeContext()

        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="C:/profile",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=lambda *_args: (None, context),
        )
        self.assertEqual(runtime.state_path, Path(account.state_path))
        self.assertTrue(runtime.persist_state)

        close_all_group_runtimes()

        self.assertEqual(context.storage_state_calls, [("storage\\a.json", True)])

    def test_runtime_health_recycles_after_processed_threshold(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=create_browser_context_fn,
        )

        for _ in range(5):
            record_runtime_success(runtime)

        health = evaluate_runtime_health(runtime, max_processed_count=5)

        self.assertTrue(health.should_recycle)
        self.assertIn("批量抓取达到 5 个账号", health.reason)
        self.assertEqual(runtime_recycle_reason(runtime, max_processed_count=5), health.reason)

    def test_runtime_health_recycles_after_consecutive_failures(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=create_browser_context_fn,
        )

        record_runtime_failure(runtime, RuntimeError("第一次失败"))
        record_runtime_failure(runtime, RuntimeError("第二次失败"))

        health = evaluate_runtime_health(runtime)

        self.assertTrue(health.should_recycle)
        self.assertIn("连续错误 2 次", health.reason)

    def test_runtime_health_detects_closed_page(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        runtime = acquire_group_runtime(
            account,
            headless=True,
            profile_dir="",
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=create_browser_context_fn,
        )
        runtime.page.close()

        health = evaluate_runtime_health(runtime)

        self.assertTrue(health.should_recycle)
        self.assertIn("页面已关闭", health.reason)


if __name__ == "__main__":
    unittest.main()
