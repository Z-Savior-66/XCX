from py_tests.ui_test_support import (
    AccountConfig,
    MainWindow,
    UiTestBase,
    os,
    patch,
)


class UiSessionTestCase(UiTestBase):
    def test_auto_validate_entry_account_skips_in_offscreen(self):
        window = MainWindow()
        self.addCleanup(window.close)

        with patch.object(window, "_run_thread") as mock_run_thread:
            window._auto_validate_entry_account()

        mock_run_thread.assert_not_called()

    def test_auto_validate_entry_account_marks_pending_before_thread(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.accounts = [
                AccountConfig(
                    name="主账号", state_path="storage/shared.json", is_entry_account=True, last_status="登录有效"
                ),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._auto_validate_entry_account()

            self.assertEqual(window.accounts[0].last_status, "检测中")
            mock_run_thread.assert_called_once()

    def test_login_selected_logs_clear_start_message_for_independent_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="入口账号", state_path="storage/shared.json", is_entry_account=True),
        ]
        window.settings.browser_profile_dir = ""
        window.refresh_table()

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.login_selected()

        self.assertIn("正在为账号 入口账号 打开独立登录窗口", window.log_edit.toPlainText())
        mock_run_thread.assert_called_once()

    def test_login_selected_logs_clear_start_message_for_shared_profile(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="入口账号", state_path="storage/shared.json", is_entry_account=True),
        ]
        window.settings.browser_profile_dir = "C:/browser_profile"
        window.refresh_table()

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.login_selected()

        self.assertIn("正在打开共享浏览器资料目录", window.log_edit.toPlainText())
        mock_run_thread.assert_called_once()

    def test_mark_login_updates_note_and_log(self):
        window = MainWindow()
        self.addCleanup(window.close)
        account = AccountConfig(name="入口账号", state_path="storage/shared.json", is_entry_account=True)
        window.accounts = [account]

        with (
            patch("desktop_py.ui.main_window.save_accounts"),
            patch("desktop_py.ui.main_window.close_all_group_runtimes") as mock_close_runtimes,
        ):
            window._mark_login(account)

        self.assertEqual(account.last_status, "已保存登录态")
        self.assertEqual(account.last_note, "可继续导入账号或直接抓取")
        self.assertIn("登录态已保存完成", window.log_edit.toPlainText())
        mock_close_runtimes.assert_called_once_with()

    def test_mark_login_propagates_feedback_url_to_shared_accounts(self):
        window = MainWindow()
        self.addCleanup(window.close)
        account = AccountConfig(
            name="入口账号",
            state_path="storage/shared.json",
            is_entry_account=True,
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
        )
        imported = AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False)
        window.accounts = [account, imported]

        with patch("desktop_py.ui.main_window.save_accounts"):
            window._mark_login(account)

        self.assertEqual(imported.feedback_url, account.feedback_url)

    def test_login_button_enabled_only_for_entry_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="入口账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()

        self.assertTrue(window.login_button.isEnabled())
        self.assertTrue(window.renew_button.isEnabled())
        self.assertTrue(window.edit_button.isEnabled())
        self.assertTrue(window.import_button.isEnabled())
        self.assertTrue(window.validate_button.isEnabled())
        self.assertFalse(window.fetch_selected_button.isEnabled())
        self.assertFalse(window.stop_fetch_button.isEnabled())
        self.assertTrue(window.delete_button.isEnabled())

        window.table.selectRow(1)
        self.assertFalse(window.login_button.isEnabled())
        self.assertFalse(window.renew_button.isEnabled())
        self.assertFalse(window.edit_button.isEnabled())
        self.assertFalse(window.import_button.isEnabled())
        self.assertFalse(window.validate_button.isEnabled())
        self.assertTrue(window.fetch_selected_button.isEnabled())
        self.assertFalse(window.stop_fetch_button.isEnabled())
        self.assertTrue(window.delete_button.isEnabled())

    def test_mark_validation_propagates_feedback_url_to_shared_accounts(self):
        window = MainWindow()
        self.addCleanup(window.close)
        account = AccountConfig(
            name="主账号",
            state_path="storage/shared.json",
            is_entry_account=True,
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=validated",
        )
        imported = AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False)
        window.accounts = [account, imported]

        with patch("desktop_py.ui.main_window.save_accounts"):
            window._mark_validation(account, True)

        self.assertEqual(imported.feedback_url, account.feedback_url)
