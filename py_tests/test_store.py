import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from desktop_py.core.models import CONFIG_SCHEMA_VERSION, AccountConfig, AppSettings
from desktop_py.core.store import (
    SHARED_BROWSER_PROFILE_DIR_NAME,
    _write_text_atomic,
    account_output_file,
    account_state_path,
    acquire_app_instance_lock,
    cleanup_account_diagnostics,
    diagnostic_index_file,
    load_accounts,
    load_settings,
    prepare_shared_browser_profile_dir,
    runtime_root,
    save_accounts,
    save_settings,
    validate_shared_browser_profile_dir,
    write_account_output_json,
    write_account_output_text,
    write_diagnostic_index_json,
)


class StoreTestCase(unittest.TestCase):
    def test_account_state_path(self):
        path = account_state_path("账号 A-1")
        self.assertTrue(path.endswith("storage\\账号_A_1.json") or path.endswith("storage/账号_A_1.json"))

    def test_account_dict(self):
        account = AccountConfig(name="测试账号", state_path="storage/test.json")
        self.assertEqual(account.to_dict()["name"], "测试账号")
        self.assertEqual(account.to_dict()["schema_version"], CONFIG_SCHEMA_VERSION)
        self.assertTrue(account.to_dict()["is_entry_account"])

    def test_load_settings_defaults_auto_fetch_push_when_missing(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text('{"feishu_webhook":"demo"}\n', encoding="utf-8")

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                settings = load_settings()

        self.assertFalse(settings.auto_fetch_push_enabled)
        self.assertEqual(settings.diagnostic_retention_days, 14)
        self.assertEqual(settings.next_auto_renew_at, "")
        self.assertEqual(settings.next_auto_fetch_push_at, "")
        self.assertEqual(settings.auto_renew_schedule_reason, "")
        self.assertEqual(settings.auto_fetch_push_schedule_reason, "")
        self.assertEqual(settings.schedule_reason, "")
        self.assertEqual(settings.schema_version, CONFIG_SCHEMA_VERSION)

    def test_load_settings_supports_utf8_bom(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text('{"feishu_webhook":"demo"}\n', encoding="utf-8-sig")

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                settings = load_settings()

        self.assertEqual(settings.feishu_webhook, "demo")


    def test_load_settings_keeps_persisted_login_wait_seconds(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text('{"login_wait_seconds":45}\n', encoding="utf-8")

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                settings = load_settings()

        self.assertEqual(settings.login_wait_seconds, 45)

    def test_load_accounts_supports_utf8_bom(self):
        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            accounts_path.write_text('[{"name":"测试账号","state_path":"storage/test.json"}]\n', encoding="utf-8-sig")

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                accounts = load_accounts()

        self.assertEqual(accounts[0].name, "测试账号")
        self.assertEqual(accounts[0].schema_version, CONFIG_SCHEMA_VERSION)

    def test_load_accounts_ignores_unknown_fields(self):
        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            accounts_path.write_text(
                '[{"name":"测试账号","state_path":"storage/test.json","legacy_field":"旧版本字段"}]\n',
                encoding="utf-8",
            )

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                accounts = load_accounts()

        self.assertEqual(accounts[0].name, "测试账号")
        self.assertFalse(hasattr(accounts[0], "legacy_field"))

    def test_load_accounts_still_rejects_missing_required_fields(self):
        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            accounts_path.write_text('[{"name":"测试账号"}]\n', encoding="utf-8")

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                with self.assertRaises(TypeError):
                    load_accounts()

    def test_load_accounts_recovers_corrupt_json_with_backup(self):
        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            accounts_path.write_text("{", encoding="utf-8")

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                accounts = load_accounts()

            backups = list(Path(temp_dir).glob("accounts.json.*.corrupt"))
            backup_content = backups[0].read_text(encoding="utf-8")
            restored_content = accounts_path.read_text(encoding="utf-8")

        self.assertEqual(accounts, [])
        self.assertEqual(len(backups), 1)
        self.assertEqual(backup_content, "{")
        self.assertEqual(restored_content, "[]\n")

    def test_load_accounts_recovers_empty_json_file_with_backup(self):
        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            accounts_path.write_text("", encoding="utf-8")

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                accounts = load_accounts()

            backups = list(Path(temp_dir).glob("accounts.json.*.corrupt"))
            backup_content = backups[0].read_text(encoding="utf-8")
            restored_content = accounts_path.read_text(encoding="utf-8")

        self.assertEqual(accounts, [])
        self.assertEqual(len(backups), 1)
        self.assertEqual(backup_content, "")
        self.assertEqual(restored_content, "[]\n")

    def test_save_settings_persists_auto_fetch_push_enabled(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text("{}\n", encoding="utf-8")

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                save_settings(load_settings())
                settings = load_settings()
                settings.auto_fetch_push_enabled = True
                save_settings(settings)

            content = settings_path.read_text(encoding="utf-8")

        self.assertIn('"auto_fetch_push_enabled": true', content)

    def test_save_settings_persists_schedule_state(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings = AppSettings(
                next_auto_renew_at="2026-05-18 21:00:00",
                next_auto_fetch_push_at="2026-05-19 09:00:00",
                auto_renew_schedule_reason="失败退避",
                auto_fetch_push_schedule_reason="每天 09:00 自动执行",
                schedule_reason="失败退避",
            )

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                save_settings(settings)
                loaded = load_settings()

        self.assertEqual(loaded.next_auto_renew_at, "2026-05-18 21:00:00")
        self.assertEqual(loaded.next_auto_fetch_push_at, "2026-05-19 09:00:00")
        self.assertEqual(loaded.auto_renew_schedule_reason, "失败退避")
        self.assertEqual(loaded.auto_fetch_push_schedule_reason, "每天 09:00 自动执行")
        self.assertEqual(loaded.schedule_reason, "失败退避")

    def test_load_settings_recovers_corrupt_json_with_default_settings(self):
        with TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.json"
            settings_path.write_text("{", encoding="utf-8")

            with (
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
            ):
                settings = load_settings()

            backups = list(Path(temp_dir).glob("settings.json.*.corrupt"))
            restored_content = settings_path.read_text(encoding="utf-8")
            backup_content = backups[0].read_text(encoding="utf-8")

        self.assertEqual(settings, AppSettings())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backup_content, "{")
        self.assertIn('"schema_version": 1', restored_content)
        self.assertIn('"login_wait_seconds": 120', restored_content)

    def test_persistent_writes_use_atomic_writer(self):
        calls: list[tuple[Path, str]] = []

        def fake_write(path: Path, content: str, encoding: str = "utf-8") -> None:
            calls.append((path, content))

        with TemporaryDirectory() as temp_dir:
            accounts_path = Path(temp_dir) / "accounts.json"
            settings_path = Path(temp_dir) / "settings.json"
            output_root = Path(temp_dir) / "output"

            with (
                patch("desktop_py.core.store.ACCOUNTS_FILE", accounts_path),
                patch("desktop_py.core.store.SETTINGS_FILE", settings_path),
                patch("desktop_py.core.store.PY_OUTPUT_DIR", output_root),
                patch("desktop_py.core.store.ensure_runtime_dirs"),
                patch("desktop_py.core.store._write_text_atomic", side_effect=fake_write),
            ):
                save_accounts([AccountConfig(name="测试账号", state_path="storage/test.json")])
                save_settings(AppSettings(feishu_webhook="demo"))
                write_account_output_json("测试账号", "payload.json", {"ok": True})

        self.assertEqual(
            [path for path, _content in calls],
            [
                accounts_path,
                settings_path,
                output_root / "测试账号" / "payload.json",
            ],
        )
        self.assertIn('"name": "测试账号"', calls[0][1])
        self.assertIn('"feishu_webhook": "demo"', calls[1][1])
        self.assertIn('"ok": true', calls[2][1])

    def test_atomic_write_keeps_original_file_when_replace_fails(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "settings.json"
            target.write_text('{"old": true}\n', encoding="utf-8")

            with patch("desktop_py.core.store.Path.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    _write_text_atomic(target, '{"new": true}\n')

            self.assertEqual(target.read_text(encoding="utf-8"), '{"old": true}\n')
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_atomic_write_skips_replace_when_content_is_unchanged(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "settings.json"
            target.write_text('{"same": true}\n', encoding="utf-8")

            with patch("desktop_py.core.store.Path.replace") as mock_replace:
                _write_text_atomic(target, '{"same": true}\n')

            mock_replace.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf-8"), '{"same": true}\n')
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_atomic_write_handles_file_disappearing_after_exists_check(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "settings.json"

            with patch("desktop_py.core.store.Path.exists", return_value=True):
                _write_text_atomic(target, '{"new": true}\n')

            self.assertEqual(target.read_text(encoding="utf-8"), '{"new": true}\n')

    def test_atomic_write_retries_permission_error_and_writes_file(self):
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "settings.json"
            target.write_text('{"old": true}\n', encoding="utf-8")
            original_replace = Path.replace
            replace_calls = 0

            def flaky_replace(current_path: Path, next_path: Path) -> Path:
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 1:
                    raise PermissionError("replace denied")
                return original_replace(current_path, next_path)

            with (
                patch("desktop_py.core.store.Path.replace", autospec=True, side_effect=flaky_replace),
                patch("desktop_py.core.store.time.sleep"),
            ):
                _write_text_atomic(target, '{"new": true}\n')

            self.assertEqual(replace_calls, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"new": true}\n')
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_acquire_app_instance_lock_creates_lock_file(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                lock = acquire_app_instance_lock(
                    lock_path=lock_path,
                    process_id_fn=lambda: 4321,
                    now_fn=lambda: 1234.5,
                )

            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            lock_file_exists = lock_path.is_file()

        self.assertEqual(payload["pid"], 4321)
        self.assertEqual(payload["created_at"], 1234.5)
        self.assertEqual(lock.pid, 4321)
        self.assertEqual(lock.token, payload["token"])
        self.assertTrue(lock_file_exists)

    def test_acquire_app_instance_lock_rejects_active_existing_lock(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"
            lock_path.write_text(
                json.dumps({"pid": 4321, "token": "old-token", "created_at": 1000.0}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                with self.assertRaisesRegex(RuntimeError, "已在运行"):
                    acquire_app_instance_lock(
                        lock_path=lock_path,
                        stale_seconds=3600,
                        process_id_fn=lambda: 9876,
                        process_running_fn=lambda pid: pid == 4321,
                        now_fn=lambda: 1200.0,
                    )

            self.assertEqual(
                json.loads(lock_path.read_text(encoding="utf-8")),
                {"pid": 4321, "token": "old-token", "created_at": 1000.0},
            )

    def test_acquire_app_instance_lock_rejects_expired_but_running_lock(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"
            lock_path.write_text(
                json.dumps({"pid": 4321, "token": "old-token", "created_at": 1000.0}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                with self.assertRaisesRegex(RuntimeError, "已在运行"):
                    acquire_app_instance_lock(
                        lock_path=lock_path,
                        stale_seconds=60,
                        process_id_fn=lambda: 9876,
                        process_running_fn=lambda _pid: True,
                        now_fn=lambda: 1200.0,
                    )

            self.assertEqual(
                json.loads(lock_path.read_text(encoding="utf-8")),
                {"pid": 4321, "token": "old-token", "created_at": 1000.0},
            )

    def test_acquire_app_instance_lock_rebuilds_dead_process_lock(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"
            lock_path.write_text(
                json.dumps({"pid": 4321, "token": "old-token", "created_at": 1000.0}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                lock = acquire_app_instance_lock(
                    lock_path=lock_path,
                    stale_seconds=3600,
                    process_id_fn=lambda: 9876,
                    process_running_fn=lambda _pid: False,
                    now_fn=lambda: 1200.0,
                )

            payload = json.loads(lock_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["pid"], 9876)
        self.assertEqual(payload["token"], lock.token)
        self.assertEqual(lock.pid, 9876)

    def test_acquire_app_instance_lock_rebuilds_expired_dead_process_lock(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"
            lock_path.write_text(
                json.dumps({"pid": 4321, "token": "old-token", "created_at": 1000.0}, ensure_ascii=False),
                encoding="utf-8",
            )

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                lock = acquire_app_instance_lock(
                    lock_path=lock_path,
                    stale_seconds=60,
                    process_id_fn=lambda: 9876,
                    process_running_fn=lambda _pid: False,
                    now_fn=lambda: 1200.0,
                )

            payload = json.loads(lock_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["pid"], 9876)
        self.assertEqual(payload["token"], lock.token)
        self.assertEqual(lock.pid, 9876)

    def test_app_instance_lock_release_only_removes_matching_lock(self):
        with TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "app.lock"

            with patch("desktop_py.core.store.ensure_runtime_dirs"):
                lock = acquire_app_instance_lock(
                    lock_path=lock_path,
                    process_id_fn=lambda: 2468,
                    now_fn=lambda: 100.0,
                )

            lock_path.write_text(
                json.dumps({"pid": 1357, "token": lock.token, "created_at": 100.0}, ensure_ascii=False),
                encoding="utf-8",
            )
            lock.release()
            still_exists_after_mismatch = lock_path.exists()

            lock_path.write_text(
                json.dumps({"pid": 2468, "token": lock.token, "created_at": 100.0}, ensure_ascii=False),
                encoding="utf-8",
            )
            lock.release()
            removed_after_match = not lock_path.exists()

        self.assertTrue(still_exists_after_mismatch)
        self.assertTrue(removed_after_match)

    def test_runtime_root_uses_executable_directory_when_frozen(self):
        with (
            patch("desktop_py.core.store.os.access", return_value=True),
            patch("desktop_py.core.store.sys", frozen=True, executable=r"C:\\portable\\小程序工具\\小程序工具.exe"),
        ):
            root = runtime_root()

        self.assertEqual(root, Path(r"C:\portable\小程序工具"))

    def test_runtime_root_falls_back_to_local_appdata_when_frozen_dir_not_writable(self):
        fake_env = {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"}
        with (
            patch("desktop_py.core.store.os.access", return_value=False),
            patch(
                "desktop_py.core.store.sys", frozen=True, executable=r"C:\\Program Files\\小程序工具\\小程序工具.exe"
            ),
            patch.dict("desktop_py.core.store.os.environ", fake_env, clear=True),
        ):
            root = runtime_root()

        self.assertEqual(root, Path(r"C:\Users\Tester\AppData\Local\小程序工具"))

    def test_validate_shared_browser_profile_dir_accepts_empty_value(self):
        self.assertEqual(validate_shared_browser_profile_dir(""), "")

    def test_validate_shared_browser_profile_dir_rejects_default_user_data_dir(self):
        with TemporaryDirectory() as temp_dir:
            profile_root = Path(temp_dir) / "User Data"
            profile_root.mkdir()
            (profile_root / "Local State").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "默认用户资料目录"):
                validate_shared_browser_profile_dir(str(profile_root))

    def test_validate_shared_browser_profile_dir_rejects_locked_dir(self):
        with TemporaryDirectory() as temp_dir:
            profile_root = Path(temp_dir) / "automation"
            profile_root.mkdir()
            (profile_root / "SingletonLock").write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "正被浏览器占用"):
                validate_shared_browser_profile_dir(str(profile_root))

    def test_validate_shared_browser_profile_dir_returns_resolved_path(self):
        with TemporaryDirectory() as temp_dir:
            profile_root = Path(temp_dir) / "automation"
            profile_root.mkdir()

            validated = validate_shared_browser_profile_dir(str(profile_root))

        self.assertEqual(validated, str(profile_root.resolve()))

    def test_prepare_shared_browser_profile_dir_creates_dedicated_child_dir(self):
        with TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            prepared = prepare_shared_browser_profile_dir(str(parent))
            expected = parent / SHARED_BROWSER_PROFILE_DIR_NAME

            self.assertTrue(expected.is_dir())
            self.assertEqual(prepared, str(expected.resolve()))

    def test_prepare_shared_browser_profile_dir_does_not_nest_dedicated_dir(self):
        with TemporaryDirectory() as temp_dir:
            dedicated = Path(temp_dir) / SHARED_BROWSER_PROFILE_DIR_NAME
            dedicated.mkdir()

            prepared = prepare_shared_browser_profile_dir(str(dedicated))

        self.assertEqual(prepared, str(dedicated.resolve()))

    def test_prepare_shared_browser_profile_dir_rejects_file_parent(self):
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "not-dir.txt"
            file_path.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "父目录必须是文件夹"):
                prepare_shared_browser_profile_dir(str(file_path))

    def test_account_output_file_uses_safe_account_dir(self):
        path = account_output_file("账号 A-1", "result.json")

        self.assertTrue(
            str(path).endswith("output\\desktop_py\\账号_A_1\\result.json")
            or str(path).endswith("output/desktop_py/账号_A_1/result.json")
        )

    def test_write_account_output_text_creates_named_file(self):
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "output"
            with patch("desktop_py.core.store.PY_OUTPUT_DIR", output_root):
                write_account_output_text("测试账号", "note.txt", "内容")

                target = output_root / "测试账号" / "note.txt"
                self.assertEqual(target.read_text(encoding="utf-8"), "内容")

    def test_write_account_output_json_creates_named_file(self):
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "output"
            with patch("desktop_py.core.store.PY_OUTPUT_DIR", output_root):
                write_account_output_json("测试账号", "payload.json", {"ok": True})

                target = output_root / "测试账号" / "payload.json"
                self.assertIn('"ok": true', target.read_text(encoding="utf-8"))

    def test_write_diagnostic_index_json_creates_root_index_file(self):
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "output"
            target = output_root / "diagnostic_index.json"
            with (
                patch("desktop_py.core.store.PY_OUTPUT_DIR", output_root),
                patch("desktop_py.core.store.DIAGNOSTIC_INDEX_FILE", target),
            ):
                written_path = write_diagnostic_index_json({"run_id": "batch-1", "accounts": []})

                self.assertEqual(diagnostic_index_file(), target)
                self.assertEqual(written_path, target)
                self.assertIn('"run_id": "batch-1"', target.read_text(encoding="utf-8"))

    def test_cleanup_account_diagnostics_only_removes_old_diagnostic_files(self):
        with TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "output"
            with patch("desktop_py.core.store.PY_OUTPUT_DIR", output_root):
                account_dir = output_root / "测试账号"
                account_dir.mkdir(parents=True)
                old_manifest = account_dir / "fetch_manifest.json"
                old_page = account_dir / "page.html"
                result_file = account_dir / "result.json"
                fresh_responses = account_dir / "responses.json"
                for path in (old_manifest, old_page, result_file, fresh_responses):
                    path.write_text("{}", encoding="utf-8")
                old_time = 1000
                fresh_time = time.time()
                os.utime(old_manifest, (old_time, old_time))
                os.utime(old_page, (old_time, old_time))
                os.utime(result_file, (old_time, old_time))
                os.utime(fresh_responses, (fresh_time, fresh_time))

                removed = cleanup_account_diagnostics("测试账号", retention_days=1)
                old_manifest_exists = old_manifest.exists()
                old_page_exists = old_page.exists()
                result_file_exists = result_file.exists()
                fresh_responses_exists = fresh_responses.exists()

        self.assertEqual(removed, 2)
        self.assertFalse(old_manifest_exists)
        self.assertFalse(old_page_exists)
        self.assertTrue(result_file_exists)
        self.assertTrue(fresh_responses_exists)


if __name__ == "__main__":
    unittest.main()
