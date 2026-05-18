import unittest
from unittest.mock import patch

from desktop_py.core.fetcher_manifest import (
    add_batch_diagnostic_account,
    add_fetch_evidence,
    fetch_step,
    finish_batch_diagnostic_index,
    finish_fetch_run,
    start_batch_diagnostic_index,
    start_fetch_run,
    write_batch_diagnostic_index,
)
from desktop_py.core.fetcher_support import CancelledError, FetchError, FetchErrorCode
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

    def test_fetch_manifest_records_fetch_error_code_and_evidence(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        manifest = start_fetch_run(account)
        error = FetchError(
            "页面未出现业务 iframe",
            code=FetchErrorCode.BUSINESS_IFRAME_MISSING,
            evidence=[
                {
                    "kind": "html",
                    "label": "页面 HTML",
                    "path": "output/账号A/page.html",
                    "summary": "已保存页面 HTML。",
                    "metadata": {"page_url": "https://mp.weixin.qq.com/"},
                }
            ],
        )

        with self.assertRaises(FetchError):
            with fetch_step(manifest, "定位业务 iframe"):
                raise error
        finish_fetch_run(manifest, error=error)

        payload = manifest.to_dict()
        self.assertEqual(payload["error_code"], "business_iframe_missing")
        self.assertEqual(payload["steps"][0]["error_code"], "business_iframe_missing")
        self.assertEqual(payload["steps"][0]["evidence"][0]["path"], "output/账号A/page.html")
        self.assertEqual(payload["evidence"][0]["metadata"]["page_url"], "https://mp.weixin.qq.com/")

    def test_fetch_manifest_records_cancelled_error(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        manifest = start_fetch_run(account)
        error = CancelledError("任务已取消")

        finish_fetch_run(manifest, error=error)

        payload = manifest.to_dict()
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error_type"], "CancelledError")
        self.assertEqual(payload["error_message"], "任务已取消")

    def test_batch_diagnostic_index_summarizes_account_results(self):
        index = start_batch_diagnostic_index(total_accounts=2, profile_dir="browser_profile")
        add_batch_diagnostic_account(
            index,
            account_name="账号A",
            result=FetchResult(account_name="账号A", ok=True, note="抓取成功"),
            duration_ms=120,
            manifest_path="output/desktop_py/账号A/fetch_manifest.json",
            result_path="output/desktop_py/账号A/result.json",
        )
        add_batch_diagnostic_account(
            index,
            account_name="账号B",
            error=FetchError("缺少 token", code=FetchErrorCode.MISSING_TOKEN),
            duration_ms=30,
            manifest_path="output/desktop_py/账号B/fetch_manifest.json",
            result_path="output/desktop_py/账号B/result.json",
        )

        finish_batch_diagnostic_index(index)
        payload = index.to_dict()

        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["total_accounts"], 2)
        self.assertEqual(payload["success_count"], 1)
        self.assertEqual(payload["failure_count"], 1)
        self.assertEqual(payload["accounts"][0]["status"], "ok")
        self.assertEqual(payload["accounts"][0]["duration_ms"], 120)
        self.assertEqual(payload["accounts"][1]["error_code"], "missing_token")
        self.assertEqual(payload["accounts"][1]["manifest_path"], "output/desktop_py/账号B/fetch_manifest.json")

    def test_write_batch_diagnostic_index_persists_payload(self):
        index = start_batch_diagnostic_index(total_accounts=1)
        finish_batch_diagnostic_index(index)

        with patch("desktop_py.core.fetcher_manifest.write_diagnostic_index_json") as mock_write:
            write_batch_diagnostic_index(index)

        mock_write.assert_called_once_with(index.to_dict())
