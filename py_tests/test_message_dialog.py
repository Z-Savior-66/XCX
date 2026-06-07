from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:
    from desktop_py.ui.message_dialog import MessageDialog


def _ensure_app():
    if not _HAS_QT:
        raise unittest.SkipTest("PySide6 is not installed")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@unittest.skipUnless(_HAS_QT, "PySide6 not available")
class MessageDialogSmokeTestCase(unittest.TestCase):
    """Smoke tests for MessageDialog -- verify construction does not crash."""

    @classmethod
    def setUpClass(cls):
        cls.app = _ensure_app()

    def test_show_info_calls_exec(self):
        """show_info should construct a dialog and call exec()."""
        parent = _make_parent()
        with patch.object(MessageDialog, "exec", return_value=0):
            result = MessageDialog.show_info(parent, "标题", "信息内容")
        self.assertEqual(result, 0)

    def test_show_warning_calls_exec(self):
        """show_warning should construct a dialog and call exec()."""
        parent = _make_parent()
        with patch.object(MessageDialog, "exec", return_value=0):
            result = MessageDialog.show_warning(parent, "警告", "警告内容")
        self.assertEqual(result, 0)

    def test_dialog_construction_with_default_tone(self):
        dialog = MessageDialog("提示", "默认信息")
        self.assertIsNotNone(dialog)
        dialog.close()

    def test_dialog_construction_with_warning_tone(self):
        dialog = MessageDialog("注意", "警告内容", tone="warning")
        self.assertIsNotNone(dialog)
        dialog.close()

    def test_dialog_construction_with_cancel_text(self):
        dialog = MessageDialog("确认", "是否继续？", cancel_text="取消")
        self.assertIsNotNone(dialog)
        dialog.close()

    def test_dialog_is_modal(self):
        dialog = MessageDialog("模态", "模态对话框")
        self.assertTrue(dialog.isModal())
        dialog.close()

    def test_dialog_has_frameless_hint(self):
        from PySide6.QtCore import Qt
        dialog = MessageDialog("无边框", "内容")
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        dialog.close()

    def test_dialog_fixed_width(self):
        dialog = MessageDialog("宽度", "内容")
        self.assertEqual(dialog.width(), 440)
        dialog.close()


def _make_parent():
    """Create a lightweight parent widget for dialog tests."""
    from PySide6.QtWidgets import QWidget
    parent = QWidget()
    parent.setWindowTitle("test_parent")
    return parent


if __name__ == "__main__":
    unittest.main()
