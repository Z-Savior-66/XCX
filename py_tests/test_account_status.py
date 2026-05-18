import unittest

from desktop_py.core.account_status import (
    AUTO_PUSH_SKIP_NOTE,
    FETCH_STATUS_FAILURE,
    FETCH_STATUS_SUCCESS,
    LOGIN_STATUS_INVALID,
    LOGIN_STATUS_SAVED,
    LOGIN_STATUS_VALID,
    RESULT_STATUS_DONE,
    RESULT_STATUS_EMPTY,
    RESULT_STATUS_FAILED,
    STATUS_CHECKING,
    display_result_text,
    fetch_status_from_result,
    is_expected_empty_result_note,
)


class AccountStatusTestCase(unittest.TestCase):
    def test_fetch_status_from_result_keeps_expected_empty_notes_as_success(self):
        self.assertEqual(
            fetch_status_from_result(False, "页面未出现业务 iframe，可能是链接失效、无权限或登录态失效。"),
            FETCH_STATUS_SUCCESS,
        )
        self.assertEqual(fetch_status_from_result(False, "当前账号无待处理申请。"), FETCH_STATUS_SUCCESS)

    def test_fetch_status_from_result_marks_regular_failures(self):
        self.assertEqual(fetch_status_from_result(False, "未在详情页文本中提取到处理截止时间。"), FETCH_STATUS_FAILURE)

    def test_display_result_text_tracks_status_grouping(self):
        self.assertEqual(display_result_text(FETCH_STATUS_SUCCESS), RESULT_STATUS_DONE)
        self.assertEqual(display_result_text(LOGIN_STATUS_VALID), RESULT_STATUS_DONE)
        self.assertEqual(display_result_text(LOGIN_STATUS_SAVED), RESULT_STATUS_DONE)
        self.assertEqual(display_result_text(LOGIN_STATUS_INVALID), RESULT_STATUS_FAILED)
        self.assertEqual(display_result_text(STATUS_CHECKING), RESULT_STATUS_EMPTY)
        self.assertEqual(display_result_text(""), RESULT_STATUS_EMPTY)

    def test_expected_empty_note_detection_matches_current_copy(self):
        self.assertTrue(is_expected_empty_result_note("页面未出现业务 iframe，可能是链接失效、无权限或登录态失效。"))
        self.assertFalse(is_expected_empty_result_note(AUTO_PUSH_SKIP_NOTE))


if __name__ == "__main__":
    unittest.main()
