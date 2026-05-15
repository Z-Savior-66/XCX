from desktop_py.core.fetcher_page_strategy import (
    build_detail_result,
    build_empty_refund_result,
    confirm_detail_deadline,
    extract_deadline_from_captures,
    fetch_paginated_refund_list_captures,
    filter_detail_captures,
    resolve_frame_locator,
)
from desktop_py.core.fetcher_support import FetchError
from desktop_py.core.notification_page_strategy import fetch_notifications
from py_tests.fetcher_test_support import (
    AccountConfig,
    FakeFrame,
    FakeLocator,
    FakePage,
    FetcherTestBase,
    FixturePage,
    Path,
    _fallback_from_responses,
    extract_labeled_datetime,
    is_login_timeout_page,
    json,
    patch,
    safe_page_content,
    wait_for_iframe_ready,
)

FEEDBACK_URL = (
    "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=golden-token"
)


class ReplayContext:
    def storage_state(self, path=None, indexed_db=False):
        return None


class ReplayFrameLocator:
    def __init__(self, text: str, html: str | None = None, action_count: int = 0):
        self._body = FakeLocator(count=1, text=text, html=html if html is not None else text)
        self._action = FakeLocator(count=action_count)

    def locator(self, selector):
        if selector == "body":
            return self._body
        return FakeLocator()

    def get_by_text(self, text, exact=False):
        if text == "处理" and exact:
            return self._action
        return FakeLocator()


class ReplayPage(FakePage):
    def __init__(self, html: str = "", account_name: str = "脱敏测试账号"):
        super().__init__()
        self.html = html
        self.account_name = account_name
        self.url = FEEDBACK_URL

    def content(self):
        return self.html


class ReplayHtmlPage:
    def __init__(self, html: str):
        self.html = html
        self.url = "https://mp.weixin.qq.com/"

    def wait_for_load_state(self, state=None, timeout=None):
        return None

    def wait_for_timeout(self, timeout):
        return None

    def content(self):
        return self.html

    def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        return None

    def locator(self, selector, **kwargs):
        if selector.startswith("text="):
            return FakeLocator(count=1 if selector.removeprefix("text=") in self.html else 0)
        return FakeLocator()

    def get_by_text(self, text, exact=False):
        return FakeLocator(count=1 if text in self.html else 0)


class FetcherReplayTestCase(FetcherTestBase):
    def read_golden(self) -> dict[str, object]:
        return json.loads(self.read_fixture("replay_golden_results.json"))

    def stable_result_dict(self, result):
        data = result.to_dict()
        data.pop("fetched_at", None)
        return data

    def confirm_detail_deadline_for_replay(self, **kwargs):
        return confirm_detail_deadline(
            **kwargs,
            extract_labeled_datetime_fn=extract_labeled_datetime,
            fallback_from_responses_fn=_fallback_from_responses,
            filter_detail_captures_fn=filter_detail_captures,
            wait_or_cancel_fn=lambda *_args, **_kwargs: None,
            retries=0,
        )

    def build_replay_detail_result(self):
        html = self.read_fixture("replay_detail_frame.html")
        page = ReplayPage(html=html)
        frame_locator = ReplayFrameLocator(text=html, html=html)
        account = AccountConfig(name="脱敏账号", state_path="storage/replay.json", is_entry_account=False)

        with (
            patch("desktop_py.core.fetcher_page_strategy.persist_storage_state"),
            patch("desktop_py.core.fetcher_page_strategy.write_fetch_result"),
        ):
            return build_detail_result(
                page=page,
                context=ReplayContext(),
                account=account,
                output_dir=Path("脱敏账号"),
                frame_locator=frame_locator,
                captures=[],
                feedback_url=FEEDBACK_URL,
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda current_page: current_page.content(),
                extract_current_account_name_fn=lambda current_page: current_page.account_name,
                confirm_detail_deadline_fn=self.confirm_detail_deadline_for_replay,
            )

    def build_replay_empty_result(self):
        html = self.read_fixture("replay_empty_list_frame.html")
        page = ReplayPage(html=html)
        frame_locator = ReplayFrameLocator(text=html, html=html)
        account = AccountConfig(name="脱敏账号", state_path="storage/replay.json", is_entry_account=False)

        with (
            patch("desktop_py.core.fetcher_page_strategy.persist_storage_state"),
            patch("desktop_py.core.fetcher_page_strategy.write_fetch_result"),
        ):
            return build_empty_refund_result(
                page=page,
                context=ReplayContext(),
                account=account,
                output_dir=Path("脱敏账号"),
                frame_locator=frame_locator,
                list_text=html,
                captures=[],
                feedback_url=FEEDBACK_URL,
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda current_page: current_page.content(),
                extract_current_account_name_fn=lambda current_page: current_page.account_name,
            )

    def test_replay_fetch_result_golden_matrix(self):
        golden = self.read_golden()
        cases = {
            "normal_detail": self.build_replay_detail_result,
            "empty_list": self.build_replay_empty_result,
        }

        for case_name, build_result in cases.items():
            with self.subTest(case=case_name):
                self.assertEqual(self.stable_result_dict(build_result()), golden[case_name])

    def test_replay_iframe_detail_fixture_extracts_deadline(self):
        detail_html = self.read_fixture("replay_detail_frame.html")
        frame = FakeFrame(text=detail_html)
        page = FakePage(
            locator_map={
                ("#js_iframe", None): FakeLocator(count=1, frame=frame),
            }
        )

        self.assertTrue(wait_for_iframe_ready(page, timeout_ms=1000))
        self.assertEqual(extract_labeled_datetime(detail_html, "处理截止时间"), "2026-05-20 18:30:00")

    def test_replay_response_fixture_golden_matrix(self):
        golden = self.read_golden()
        cases = {
            "changed_response_field": [json.loads(self.read_fixture("replay_response_changed_field.json"))],
            "appeal_deadline_priority": [json.loads(self.read_fixture("replay_refund_response_candidates.json"))],
        }

        expected = {
            "changed_response_field": golden["changed_response_field"],
            "appeal_deadline_priority": {"deadline_text": "2026-05-21 10:30:00"},
        }

        for case_name, payloads in cases.items():
            with self.subTest(case=case_name):
                self.assertEqual({"deadline_text": _fallback_from_responses(payloads)}, expected[case_name])

    def test_replay_paginated_refund_list_fixture_matches_golden(self):
        golden = self.read_golden()
        payload = json.loads(self.read_fixture("replay_paginated_refund_list.json"))
        captures = payload["captures"]
        requested_pages = payload["requested_pages"]

        def fake_request(_page, request_url: str):
            cur_page = request_url.split("cur_page=", 1)[1].split("&", 1)[0]
            return requested_pages[cur_page]

        extended_captures = fetch_paginated_refund_list_captures(
            page=object(),
            captures=captures,
            logger=None,
            log_fn=lambda _logger, _message: None,
            request_refund_list_page_fn=fake_request,
        )

        self.assertEqual(
            {
                "capture_count": len(extended_captures),
                "deadline_text": extract_deadline_from_captures(extended_captures),
            },
            golden["paginated_refund_list"],
        )

    def test_replay_missing_business_iframe_reports_structure_error(self):
        golden = self.read_golden()
        page = FixturePage(self.read_fixture("replay_missing_business_iframe.html"))

        with patch("desktop_py.core.fetcher_page_strategy.write_account_output_text") as mock_write:
            with self.assertRaises(FetchError) as context:
                resolve_frame_locator(
                    page,
                    output_dir=Path("脱敏账号"),
                    business_iframe_selector_fn=lambda current_page: "",
                    safe_page_content_fn=lambda current_page: current_page.html,
                )

        self.assertEqual(
            {"error_type": type(context.exception).__name__, "message": str(context.exception)},
            golden["missing_iframe_error"],
        )
        mock_write.assert_called_once_with("脱敏账号", "page.html", page.html)

    def test_replay_login_timeout_fixture_matches_golden(self):
        golden = self.read_golden()
        page = ReplayHtmlPage(self.read_fixture("replay_login_timeout.html"))

        self.assertEqual(
            {"is_login_timeout": is_login_timeout_page(page, safe_page_content_fn=safe_page_content)},
            golden["login_timeout"],
        )

    def test_replay_notification_failure_fixture_matches_golden(self):
        golden = self.read_golden()
        page = ReplayHtmlPage(self.read_fixture("replay_notification_failure.html"))
        account = AccountConfig(name="脱敏账号", state_path="storage/replay.json", is_entry_account=False)

        with (
            patch("desktop_py.core.notification_page_strategy.write_account_output_json"),
            patch("desktop_py.core.notification_page_strategy.write_account_output_text"),
        ):
            result = fetch_notifications(
                page,
                account=account,
                logger=None,
                output_dir=Path("脱敏账号"),
                log_fn=lambda _logger, _message: None,
                wait_for_url_contains_fn=lambda *_args, **_kwargs: None,
                safe_page_content_fn=lambda current_page: current_page.content(),
            )

        self.assertEqual(
            {
                "ok": result["ok"],
                "notifications": result["notifications"],
                "summary": result["summary"],
                "page_url": result["page_url"],
            },
            golden["notification_failure"],
        )

    def test_replay_cross_account_token_fixture_matches_golden(self):
        golden = self.read_golden()
        captures = json.loads(self.read_fixture("replay_cross_account_captures.json"))
        frame_locator = ReplayFrameLocator(text="", html="")

        deadline_text, _frame_text, _frame_html = self.confirm_detail_deadline_for_replay(
            page=ReplayPage(),
            frame_locator=frame_locator,
            captures=captures,
            feedback_url=FEEDBACK_URL,
            is_cancelled=None,
        )
        filtered_captures = filter_detail_captures(captures, FEEDBACK_URL)

        self.assertEqual(
            {
                "deadline_text": deadline_text,
                "filtered_tokens": [capture["token"] for capture in filtered_captures],
            },
            golden["cross_account_token"],
        )
