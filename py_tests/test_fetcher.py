from urllib.parse import parse_qs, urlparse

from desktop_py.core.fetcher_common import build_ios_refund_feedback_url
from py_tests.fetcher_test_support import (
    FakePage,
    FetcherTestBase,
    FixturePage,
    _fallback_from_responses,
    build_feedback_url,
    business_iframe_selector,
    extract_current_account_name,
    extract_labeled_datetime,
    find_switch_entry,
    json,
    patch,
)


class FetcherContractTestCase(FetcherTestBase):
    def test_build_feedback_url(self):
        url = build_feedback_url("https://mp.weixin.qq.com/wxamp/index/index?lang=zh_CN&token=2056634783")
        self.assertIn("plugin_uin=1010", url)
        self.assertIn("selected=2", url)
        self.assertIn("token=2056634783", url)

    def test_build_ios_refund_feedback_url(self):
        url = build_ios_refund_feedback_url("https://mp.weixin.qq.com/wxamp/index/index?lang=zh_CN&token=2056634783")
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["plugin_uin"], ["1039"])
        self.assertEqual(query["selected"], ["2"])
        self.assertEqual(query["submenu_selected"], ["3"])
        self.assertEqual(query["custom"], ["path=/old-teenager-refund-process"])
        self.assertEqual(query["token"], ["2056634783"])

    def test_contract_fixture_switch_account_menu_matches_title_selector(self):
        page = FixturePage(self.read_fixture("switch_account_menu.html"))

        result = find_switch_entry(page)

        self.assertIsNotNone(result)
        self.assertEqual(result.count(), 1)

    def test_contract_fixture_reports_missing_switch_account_entry(self):
        page = FixturePage(self.read_fixture("no_switch_account_menu.html"))

        result = find_switch_entry(page)

        self.assertIsNone(result)

    def test_contract_fixture_extracts_current_account_name_from_page_html(self):
        page = FakePage()
        page.set_content_results([self.read_fixture("switch_account_menu.html")])

        with patch(
            "desktop_py.core.fetcher.safe_page_content", return_value=self.read_fixture("switch_account_menu.html")
        ):
            self.assertEqual(extract_current_account_name(page), "主账号")

    def test_contract_fixture_prefers_js_iframe_selector(self):
        page = FixturePage(self.read_fixture("feedback_page_iframe.html"))

        self.assertEqual(business_iframe_selector(page), "#js_iframe")

    def test_contract_fixture_reports_missing_business_iframe(self):
        page = FixturePage(self.read_fixture("no_feedback_iframe.html"))

        self.assertEqual(business_iframe_selector(page), "")

    def test_contract_fixture_extracts_deadline_from_detail_text(self):
        deadline = extract_labeled_datetime(self.read_fixture("detail_frame.txt"), "处理截止时间")

        self.assertEqual(deadline, "2026-04-20 18:00")

    def test_contract_fixture_returns_empty_when_detail_text_has_no_deadline(self):
        deadline = extract_labeled_datetime(self.read_fixture("detail_without_deadline.txt"), "处理截止时间")

        self.assertEqual(deadline, "")

    def test_contract_fixture_extracts_deadline_from_response_payload(self):
        payload = json.loads(self.read_fixture("refund_response.json"))

        deadline = _fallback_from_responses([payload])

        self.assertEqual(deadline, "2026-04-21 10:19:34")

    def test_contract_fixture_returns_empty_when_response_has_no_deadline(self):
        payload = json.loads(self.read_fixture("refund_response_without_deadline.json"))

        deadline = _fallback_from_responses([payload])

        self.assertEqual(deadline, "")
