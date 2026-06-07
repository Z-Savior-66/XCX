from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    from desktop_py.ui.main_window_view import (
        append_log,
        refresh_summary_cards,
        set_status_text,
        should_show_runtime_log_message,
        format_runtime_log_message,
        _account_name_log_range,
        _format_account_result_block,
        _normalize_account_result_detail,
    )
    from desktop_py.core.models import AccountConfig, AppSettings


def _ensure_app():
    if not _HAS_QT:
        raise unittest.SkipTest("PySide6 is not installed")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@unittest.skipUnless(_HAS_QT, "PySide6 not available")
class SetStatusTextTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_set_status_text_updates_label(self):
        from PySide6.QtWidgets import QLabel
        window = QMainWindow()
        window._status_label = QLabel("当前状态：就绪")

        set_status_text(window, "抓取中")

        self.assertEqual(window._status_label.text(), "当前状态：抓取中")
        window.close()

    def test_set_status_text_noop_when_label_is_none(self):
        window = QMainWindow()
        window._status_label = None

        # Should not raise
        set_status_text(window, "任何状态")
        window.close()


@unittest.skipUnless(_HAS_QT, "PySide6 not available")
class AppendLogTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_append_log_adds_text(self):
        from PySide6.QtWidgets import QPlainTextEdit
        window = MagicMock()
        window.log_edit = QPlainTextEdit()

        append_log(window, "测试日志消息")

        text = window.log_edit.toPlainText()
        self.assertIn("测试日志消息", text)

    def test_append_log_skips_process_prefix_messages(self):
        from PySide6.QtWidgets import QPlainTextEdit
        window = MagicMock()
        window.log_edit = QPlainTextEdit()

        append_log(window, "已切换到账号：xxx")

        text = window.log_edit.toPlainText()
        self.assertEqual(text, "")

    def test_append_log_skips_current_account_prefix(self):
        from PySide6.QtWidgets import QPlainTextEdit
        window = MagicMock()
        window.log_edit = QPlainTextEdit()

        append_log(window, "当前已是目标账号：yyy")

        text = window.log_edit.toPlainText()
        self.assertEqual(text, "")

    def test_append_log_skips_empty_message(self):
        from PySide6.QtWidgets import QPlainTextEdit
        window = MagicMock()
        window.log_edit = QPlainTextEdit()

        append_log(window, "   ")

        text = window.log_edit.toPlainText()
        self.assertEqual(text, "")


class ShouldShowRuntimeLogMessageTestCase(unittest.TestCase):
    def test_empty_string_returns_false(self):
        self.assertFalse(should_show_runtime_log_message(""))

    def test_whitespace_only_returns_false(self):
        self.assertFalse(should_show_runtime_log_message("   "))

    def test_switched_to_account_prefix_returns_false(self):
        self.assertFalse(should_show_runtime_log_message("已切换到账号：xxx"))

    def test_current_account_prefix_returns_false(self):
        self.assertFalse(should_show_runtime_log_message("当前已是目标账号：yyy"))

    def test_normal_message_returns_true(self):
        self.assertTrue(should_show_runtime_log_message("开始抓取任务"))


class FormatRuntimeLogMessageTestCase(unittest.TestCase):
    def test_normal_message_passes_through(self):
        self.assertEqual(format_runtime_log_message("  hello  "), "hello")

    def test_success_message_formats_block(self):
        msg = "账号 MyAcc 抓取成功：详情"
        result = format_runtime_log_message(msg)
        self.assertIn("账号：MyAcc", result)
        self.assertIn("状态：成功", result)

    def test_failure_message_formats_block(self):
        msg = "账号 BadAcc 抓取失败：原因"
        result = format_runtime_log_message(msg)
        self.assertIn("账号：BadAcc", result)
        self.assertIn("状态：失败", result)


class AccountNameLogRangeTestCase(unittest.TestCase):
    def test_returns_negative_for_no_marker(self):
        start, end = _account_name_log_range("some random text")
        self.assertEqual(start, -1)
        self.assertEqual(end, -1)

    def test_returns_range_for_valid_text(self):
        text = "账号：张三｜状态：成功"
        start, end = _account_name_log_range(text)
        self.assertGreater(start, 0)
        self.assertGreater(end, start)
        self.assertEqual(text[start:end], "张三")


class NormalizeAccountResultDetailTestCase(unittest.TestCase):
    def test_numbered_line(self):
        result = _normalize_account_result_detail("1. 第一条详情")
        self.assertEqual(result, "1. 第一条详情")

    def test_unnumbered_line(self):
        result = _normalize_account_result_detail("普通详情")
        self.assertEqual(result, "普通详情")


class FormatAccountResultBlockTestCase(unittest.TestCase):
    def test_contains_header_and_details(self):
        block = _format_account_result_block("测试账号", "成功", "1. 详情一\n2. 详情二")
        self.assertIn("账号：测试账号｜状态：成功", block)
        self.assertIn("详情一", block)
        self.assertIn("详情二", block)

    def test_empty_detail(self):
        block = _format_account_result_block("账号A", "失败", "")
        self.assertIn("账号：账号A｜状态：失败", block)


@unittest.skipUnless(_HAS_QT, "PySide6 not available")
class RefreshSummaryCardsTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_refresh_summary_cards_with_accounts(self):
        from PySide6.QtWidgets import QLabel

        window = MagicMock()
        imported = [
            AccountConfig(name="a1", state_path="/a1", is_entry_account=False, enabled=True, last_status="抓取成功", last_fetch_at="2024-01-01"),
            AccountConfig(name="a2", state_path="/a2", is_entry_account=False, enabled=False, last_status="抓取失败", last_fetch_at="2024-01-02"),
            AccountConfig(name="entry", state_path="/entry", is_entry_account=True, enabled=True),
        ]
        window.accounts = imported

        labels = {}
        for key in ("total", "enabled", "healthy", "recent"):
            labels[key] = QLabel()
        window._summary_labels = labels

        refresh_summary_cards(window)

        self.assertEqual(labels["total"].text(), "2")
        self.assertEqual(labels["enabled"].text(), "1")
        self.assertEqual(labels["recent"].text(), "2024-01-02")

    def test_refresh_summary_cards_no_imported_accounts(self):
        from PySide6.QtWidgets import QLabel

        window = MagicMock()
        window.accounts = [
            AccountConfig(name="entry", state_path="/entry", is_entry_account=True, enabled=True),
        ]

        labels = {}
        for key in ("total", "enabled", "healthy", "recent"):
            labels[key] = QLabel()
        window._summary_labels = labels

        refresh_summary_cards(window)

        self.assertEqual(labels["total"].text(), "0")
        self.assertEqual(labels["enabled"].text(), "0")
        self.assertEqual(labels["recent"].text(), "暂无")


if __name__ == "__main__":
    unittest.main()
