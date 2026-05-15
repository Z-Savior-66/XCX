from py_tests.fetcher_test_support import (
    FakeResponse,
    FetcherTestBase,
    _capture_response_payload,
    _fallback_from_responses,
    build_notification_summary,
    classify_refund_response_type,
    extract_response_token,
    filter_target_unread_notifications,
    register_response_capture,
)


class FetcherResponseCaptureTestCase(FetcherTestBase):
    def test_filter_target_unread_notifications_only_keeps_unread_target_titles(self):
        items = [
            {
                "notify_id": "1",
                "class_name": "notice_item js_msg_item",
                "title": "小程序微信认证年审通知",
                "time_text": "2026-04-19",
                "content_text": "年审内容",
            },
            {
                "notify_id": "2",
                "class_name": "notice_item js_msg_item readed",
                "title": "小程序微信认证年审通知",
                "time_text": "2026-04-12",
                "content_text": "已读年审",
            },
            {
                "notify_id": "3",
                "class_name": "notice_item js_msg_item",
                "title": "其它通知",
                "time_text": "2026-04-10",
                "content_text": "其它内容",
            },
        ]

        result = filter_target_unread_notifications(items, "账号A")

        self.assertEqual(
            result,
            [
                {
                    "account_name": "账号A",
                    "notify_id": "1",
                    "title": "小程序微信认证年审通知",
                    "time_text": "2026-04-19",
                    "content_text": "年审内容",
                    "is_unread": True,
                    "matched_rule": "annual_review",
                    "rule_version": "2026-05-14.v1",
                }
            ],
        )

    def test_build_notification_summary_formats_count_and_titles(self):
        summary = build_notification_summary(
            [
                {"title": "小程序微信认证年审通知"},
                {"title": "你的账号收到一条侵权投诉"},
            ]
        )
        self.assertEqual(summary, "通知中心未读消息 2 条：小程序微信认证年审通知、你的账号收到一条侵权投诉")

    def test_fallback_from_responses_prefers_appeal_deadline_time(self):
        deadline = _fallback_from_responses(
            [
                {
                    "data": {
                        "user_refund_check_list": [
                            {
                                "ctrl_info": {
                                    "deadline_time": "1776147849",
                                    "appeal_deadline_time": "1776737974",
                                }
                            }
                        ]
                    }
                }
            ]
        )

        self.assertEqual(deadline, "2026-04-21 10:19:34")

    def test_capture_response_payload_keeps_json_body_for_fallback(self):
        response = FakeResponse(
            '{"data":{"user_refund_check_list":[{"ctrl_info":{"appeal_deadline_time":"1776737974"}}]}}',
            url="https://mp.weixin.qq.com/wxamp/cgi/getuserrefundchecklist?token=1",
        )

        payload = _capture_response_payload(response)

        self.assertEqual(
            payload["body"]["data"]["user_refund_check_list"][0]["ctrl_info"]["appeal_deadline_time"], "1776737974"
        )

    def test_capture_response_payload_adds_business_metadata(self):
        response = FakeResponse(
            '{"data":{"total_count":1,"user_refund_check_list":[{"ctrl_info":{"deadline_time":"1777046400"}}]}}',
            url="https://game.weixin.qq.com/cgi-bin/gamewxagbdatawap/getuserrefundchecklist?per_page=6&cur_page=0",
        )

        payload = _capture_response_payload(response)

        self.assertEqual(payload["response_type"], "list")
        self.assertIn("captured_at", payload)
        self.assertEqual(payload["token"], "")

    def test_capture_response_payload_ignores_unrelated_response_url(self):
        response = FakeResponse(
            '{"ok":true}',
            url="https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN",
        )

        payload = _capture_response_payload(response)

        self.assertIsNone(payload)

    def test_capture_response_payload_keeps_notification_center_response(self):
        response = FakeResponse(
            '{"list":[{"title":"小程序微信认证年审通知"}]}',
            url="https://mp.weixin.qq.com/wxamp/tools/wasysnotify?action=list&token=1",
        )

        payload = _capture_response_payload(response)

        self.assertEqual(payload["response_type"], "notification")
        self.assertEqual(payload["body"]["list"][0]["title"], "小程序微信认证年审通知")

    def test_classify_refund_response_type_distinguishes_list_and_detail(self):
        self.assertEqual(
            classify_refund_response_type(
                "https://game.weixin.qq.com/cgi-bin/gamewxagbdatawap/getuserrefundchecklist?per_page=6&cur_page=0",
                {},
            ),
            "list",
        )
        self.assertEqual(
            classify_refund_response_type(
                "https://game.weixin.qq.com/cgi-bin/gamewxagbdatawap/getuserrefundchecklist?cid=abc",
                {},
            ),
            "detail",
        )
        self.assertEqual(extract_response_token("https://mp.weixin.qq.com/wxamp/index/index?token=123"), "123")

    def test_offline_response_fixture_extracts_deadline_candidate(self):
        deadline = _fallback_from_responses(
            [
                {
                    "body": {
                        "data": {
                            "user_refund_check_list": [
                                {
                                    "ctrl_info": {
                                        "appeal_deadline_time": "2026-04-20 18:00",
                                    }
                                }
                            ]
                        }
                    }
                }
            ]
        )

        self.assertEqual(deadline, "2026-04-20 18:00")

    def test_register_response_capture_removes_listener_on_cleanup(self):
        events: dict[str, list] = {}

        class ListenerPage:
            def on(self, event_name, callback):
                events.setdefault(event_name, []).append(callback)

            def remove_listener(self, event_name, callback):
                events.setdefault(event_name, []).remove(callback)

        page = ListenerPage()

        captures, cleanup = register_response_capture(page, lambda response: {"url": response})

        self.assertEqual(len(events["response"]), 1)
        events["response"][0]("https://example.com/api")
        self.assertEqual(captures, [{"url": "https://example.com/api"}])

        cleanup()

        self.assertEqual(events["response"], [])
