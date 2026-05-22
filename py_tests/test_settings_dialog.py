import unittest

from desktop_py.ui.settings_dialog import SettingsDialog
from py_tests.ui_test_support import AppSettings, MainWindow, UiTestBase, patch


class FakeSettingsDialog:
    class DialogCode:
        Accepted = 1

    def __init__(self, settings, **_kwargs):
        self.settings = settings

    def exec(self):
        return self.DialogCode.Accepted

    def build_settings(self):
        return AppSettings(
            feishu_webhook="https://example.test/hook",
            browser_profile_dir="C:/shared/profile",
            startup_enabled=True,
        )


class FakeUnchangedSettingsDialog(FakeSettingsDialog):
    def build_settings(self):
        return AppSettings(
            feishu_webhook="https://example.test/hook",
            browser_profile_dir="C:/shared/profile",
            startup_enabled=False,
        )


class SettingsDialogTestCase(UiTestBase):
    def test_dialog_builds_settings_with_startup_switch_state(self):
        dialog = SettingsDialog(
            AppSettings(feishu_webhook="old", browser_profile_dir="C:/old"),
            startup_enabled=True,
            validate_shared_browser_profile_dir_fn=lambda value: value.strip(),
        )
        self.addCleanup(dialog.close)

        dialog.webhook_edit.setText(" https://example.test/hook ")
        dialog.profile_dir_edit.setText(" C:/shared/profile ")
        dialog.startup_switch.setChecked(False)
        settings = dialog.build_settings()

        self.assertEqual(settings.feishu_webhook, "https://example.test/hook")
        self.assertEqual(settings.browser_profile_dir, "C:/shared/profile")
        self.assertFalse(settings.startup_enabled)

    def test_main_window_exposes_settings_button_and_saves_dialog_result(self):
        window = MainWindow()
        self.addCleanup(window.close)

        self.assertIsNotNone(window.settings_button)
        self.assertEqual(window.settings_button.text(), "设置")

        with (
            patch("desktop_py.ui.main_window.get_startup_enabled", return_value=False),
            patch("desktop_py.ui.main_window.SettingsDialog", FakeSettingsDialog),
            patch("desktop_py.ui.main_window.set_startup_enabled") as mock_set_startup_enabled,
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
        ):
            window.open_settings_dialog()

        self.assertEqual(window.settings.feishu_webhook, "https://example.test/hook")
        self.assertEqual(window.settings.browser_profile_dir, "C:/shared/profile")
        self.assertTrue(window.settings.startup_enabled)
        mock_set_startup_enabled.assert_called_once_with(True)
        self.assertGreaterEqual(mock_save_settings.call_count, 1)
        mock_save_settings.assert_any_call(window.settings)

    def test_main_window_does_not_rewrite_startup_when_option_is_unchanged(self):
        window = MainWindow()
        self.addCleanup(window.close)

        with (
            patch("desktop_py.ui.main_window.get_startup_enabled", return_value=False),
            patch("desktop_py.ui.main_window.SettingsDialog", FakeUnchangedSettingsDialog),
            patch("desktop_py.ui.main_window.set_startup_enabled") as mock_set_startup_enabled,
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
        ):
            window.open_settings_dialog()

        mock_set_startup_enabled.assert_not_called()
        self.assertGreaterEqual(mock_save_settings.call_count, 1)
        self.assertFalse(window.settings.startup_enabled)

    def test_main_window_keeps_current_settings_when_startup_write_fails(self):
        window = MainWindow()
        self.addCleanup(window.close)
        original_settings = window.settings

        with (
            patch("desktop_py.ui.main_window.get_startup_enabled", return_value=False),
            patch("desktop_py.ui.main_window.SettingsDialog", FakeSettingsDialog),
            patch("desktop_py.ui.main_window.set_startup_enabled", side_effect=OSError("写入失败")),
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            patch.object(window, "_show_warning") as mock_show_warning,
        ):
            window.open_settings_dialog()

        mock_save_settings.assert_not_called()
        mock_show_warning.assert_called_once()
        self.assertIs(window.settings, original_settings)


if __name__ == "__main__":
    unittest.main()
