import unittest

from desktop_py.core.fetcher_manifest import (
    add_fetch_evidence,
    fetch_step,
    finish_fetch_run,
    start_fetch_run,
)
from desktop_py.core.fetcher_support import CancelledError
from desktop_py.core.models import AccountConfig, FetchResult


class FetcherManifestTestCase(unittest.TestCase):
    def test_fetch_manifest_records_success_steps_and_evidence(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        manifest = start_fetch_run(account, profile_dir="browser_profile", output_dir="output/账号A")

        evidence = add_fetch_evidence(
            manifest,
            kind="network",
            label="退款接口响应",
            summary="捕获 1 条目标响应",
            metadata={"capture_count": 1},
        )
        with fetch_step(manifest, "打开退款反馈页", evidence=[evidence]):
            pass
        finish_fetch_run(manifest, result=FetchResult(account_name="账号A", ok=True, note="已完成详情页抓取。"))

        payload = manifest.to_dict()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["rule_version"], "2026-05-14.v1")
        self.assertEqual(payload["result_ok"], True)
        self.assertEqual(payload["steps"][0]["status"], "ok")
        self.assertEqual(payload["steps"][0]["evidence"][0]["metadata"]["capture_count"], 1)

    def test_fetch_manifest_records_failure_step(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        manifest = start_fetch_run(account)

        with self.assertRaisesRegex(RuntimeError, "页面结构变化"):
            with fetch_step(manifest, "定位业务 iframe"):
                raise RuntimeError("页面结构变化")
        finish_fetch_run(manifest, error=RuntimeError("页面结构变化"))

        payload = manifest.to_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertEqual(payload["steps"][0]["status"], "failed")
        self.assertEqual(payload["steps"][0]["error_message"], "页面结构变化")

    def test_fetch_manifest_records_cancelled_error(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        manifest = start_fetch_run(account)
        error = CancelledError("任务已取消")

        finish_fetch_run(manifest, error=error)

        payload = manifest.to_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_type"], "CancelledError")
        self.assertEqual(payload["error_message"], "任务已取消")
