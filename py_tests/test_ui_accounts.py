from py_tests.ui_test_support import (
    SHARED_BROWSER_PROFILE_DIR_NAME,
    AccountConfig,
    AccountDialog,
    AppSettings,
    MainWindow,
    Path,
    QKeyEvent,
    Qt,
    TemporaryDirectory,
    UiTestBase,
    patch,
)


class UiAccountTestCase(UiTestBase):
    def test_account_dialog_builds_account(self):
        dialog = AccountDialog(AccountConfig(name="演示账号", state_path="storage/demo.json"))
        account = dialog.build_account()

        self.assertEqual(account.name, "演示账号")
        self.assertEqual(account.state_path, "storage/demo.json")
        self.assertTrue(account.is_entry_account)

    def test_browse_button_enabled_only_when_profile_input_focused(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        self.assertFalse(window.browse_profile_button.isEnabled())

        window.profile_dir_edit.setFocus()
        self.app.processEvents()
        self.assertTrue(window.browse_profile_button.isEnabled())

        window.browse_profile_button.setFocus()
        self.app.processEvents()
        self.assertTrue(window.browse_profile_button.isEnabled())

        window.webhook_edit.setFocus()
        self.app.processEvents()
        self.assertFalse(window.browse_profile_button.isEnabled())

    def test_imported_account_cannot_save_login_state(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="入口账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.login_selected()

        mock_information.assert_called_once()
        self.assertIn("导入账号不能直接保存登录态", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_multi_selection_disables_single_account_actions(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()

        window.table.selectRow(1)
        window.table.selectionModel().select(
            window.table.model().index(2, 0),
            window.table.selectionModel().SelectionFlag.Select | window.table.selectionModel().SelectionFlag.Rows,
        )

        self.assertFalse(window.login_button.isEnabled())
        self.assertFalse(window.renew_button.isEnabled())
        self.assertFalse(window.edit_button.isEnabled())
        self.assertFalse(window.import_button.isEnabled())
        self.assertFalse(window.validate_button.isEnabled())
        self.assertFalse(window.fetch_selected_button.isEnabled())
        self.assertFalse(window.stop_fetch_button.isEnabled())
        self.assertTrue(window.delete_button.isEnabled())

    def test_imported_account_cannot_edit(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with patch.object(window, "_show_info") as mock_information:
            window.edit_account()

        mock_information.assert_called_once()
        self.assertIn("导入账号不允许编辑", mock_information.call_args.args[1])

    def test_edit_account_state_path_switches_to_new_group_feedback_url(self):
        window = MainWindow()
        self.addCleanup(window.close)
        old_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=old"
        new_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=new"
        window.accounts = [
            AccountConfig(
                name="主账号",
                state_path="storage/old.json",
                is_entry_account=True,
                feedback_url=old_feedback_url,
            ),
            AccountConfig(
                name="导入账号A",
                state_path="storage/new.json",
                is_entry_account=False,
                feedback_url=new_feedback_url,
            ),
        ]
        window.refresh_table()

        class FakeDialog:
            DialogCode = AccountDialog.DialogCode

            def __init__(self, account=None, parent=None):
                self._account = account

            def exec(self):
                return self.DialogCode.Accepted

            def build_account(self):
                return AccountConfig(
                    name="主账号",
                    state_path="storage/new.json",
                    is_entry_account=True,
                    home_url="https://mp.weixin.qq.com/",
                    enabled=True,
                )

        with (
            patch("desktop_py.ui.main_window.AccountDialog", FakeDialog),
            patch("desktop_py.ui.main_window.save_accounts"),
        ):
            window.edit_account()

        self.assertEqual(window.accounts[0].state_path, "storage/new.json")
        self.assertEqual(window.accounts[0].feedback_url, window.accounts[1].feedback_url)

    def test_imported_account_cannot_validate_login_state(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.validate_selected()

        mock_information.assert_called_once()
        self.assertIn("导入账号不能校验登录态", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_imported_account_cannot_renew_login_state(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.renew_selected()

        mock_information.assert_called_once()
        self.assertIn("导入账号不能登录续期", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_imported_account_cannot_import_accounts(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.import_accounts()

        mock_information.assert_called_once()
        self.assertIn("只有主账号可以导入账号列表", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_import_accounts_reuses_shared_feedback_url_from_fetched_imported_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(
                name="导入账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=321",
            ),
        ]
        window.refresh_table()
        window.table.selectRow(0)
        seen_feedback_urls: list[str] = []

        def fake_fetch_switchable_accounts(account, **_kwargs):
            seen_feedback_urls.append(account.feedback_url)
            return ["导入账号"]

        def run_immediately(job, on_success=None):
            result = job(lambda _message: None)
            if callable(on_success):
                on_success(result)

        with (
            patch.object(window, "_run_thread", side_effect=run_immediately),
            patch("desktop_py.ui.main_window.save_accounts") as mock_save_accounts,
            patch("desktop_py.ui.main_window.fetch_switchable_accounts", side_effect=fake_fetch_switchable_accounts),
        ):
            window.import_accounts()

        expected_url = (
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?"
            "action=plugin_redirect&plugin_uin=1010&selected=2&token=321&lang=zh_CN"
        )
        self.assertEqual(window.accounts[0].feedback_url, expected_url)
        self.assertEqual(seen_feedback_urls, [expected_url])
        mock_save_accounts.assert_called()

    def test_save_current_settings_rejects_invalid_shared_profile_dir(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.profile_dir_edit.setText("C:/Users/Tester/AppData/Local/Google/Chrome/User Data")

        with (
            patch(
                "desktop_py.ui.main_window.validate_shared_browser_profile_dir",
                side_effect=ValueError(
                    "共享浏览器资料目录不能直接指向 Chrome 或 Edge 的默认用户资料目录，请改用专用自动化目录。"
                ),
            ),
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            patch.object(window, "_show_warning") as mock_warning,
        ):
            window.save_current_settings()

        mock_save_settings.assert_not_called()
        mock_warning.assert_called_once()
        self.assertIn("默认用户资料目录", mock_warning.call_args.args[1])

    def test_save_current_settings_preserves_headless_fetch_value(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.settings.headless_fetch = False

        with (
            patch("desktop_py.ui.main_window.validate_shared_browser_profile_dir", return_value=""),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window.save_current_settings()

        self.assertFalse(window.settings.headless_fetch)

    def test_save_current_settings_preserves_login_wait_seconds_value(self):
        with patch("desktop_py.ui.main_window.load_settings", return_value=AppSettings(login_wait_seconds=45)):
            window = MainWindow()
        self.addCleanup(window.close)

        with (
            patch("desktop_py.ui.main_window.validate_shared_browser_profile_dir", return_value=""),
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
        ):
            window.save_current_settings()

        self.assertEqual(window.settings.login_wait_seconds, 45)
        self.assertEqual(mock_save_settings.call_args.args[0].login_wait_seconds, 45)

    def test_choose_profile_dir_creates_dedicated_child_dir(self):
        window = MainWindow()
        self.addCleanup(window.close)

        with (
            TemporaryDirectory() as temp_dir,
            patch(
                "desktop_py.ui.main_window.QFileDialog.getExistingDirectory",
                return_value=temp_dir,
            ),
        ):
            window.choose_profile_dir()

            expected = Path(temp_dir) / SHARED_BROWSER_PROFILE_DIR_NAME
            self.assertTrue(expected.is_dir())
            self.assertEqual(window.profile_dir_edit.text(), str(expected.resolve()))

    def test_choose_profile_dir_keeps_current_text_when_cancelled(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.profile_dir_edit.setText("原目录")

        with patch("desktop_py.ui.main_window.QFileDialog.getExistingDirectory", return_value=""):
            window.choose_profile_dir()

        self.assertEqual(window.profile_dir_edit.text(), "原目录")

    def test_select_imported_accounts_selects_all_imported_rows(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()

        window.select_imported_accounts()

        self.assertEqual(window.selected_indexes(), [1, 2])

    def test_ctrl_a_does_not_select_all_rows(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)

        window.table.keyPressEvent(event)

        self.assertEqual(window.selected_indexes(), [0])

    def test_delete_account_supports_batch_delete(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.select_imported_accounts()

        with (
            patch("desktop_py.ui.main_window.MessageDialog.ask_confirm", return_value=True) as mock_confirm,
            patch("desktop_py.ui.main_window.save_accounts") as mock_save,
        ):
            window.delete_account()

        self.assertEqual([account.name for account in window.accounts], ["主账号"])
        mock_confirm.assert_called_once()
        mock_save.assert_called_once()

    def test_delete_account_cancel_keeps_accounts(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(1)

        with (
            patch("desktop_py.ui.main_window.MessageDialog.ask_confirm", return_value=False) as mock_confirm,
            patch("desktop_py.ui.main_window.save_accounts") as mock_save,
        ):
            window.delete_account()

        self.assertEqual([account.name for account in window.accounts], ["主账号", "导入账号A"])
        mock_confirm.assert_called_once()
        mock_save.assert_not_called()

    def test_entry_account_row_shows_current_main_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        with patch("desktop_py.ui.main_window.save_settings"):
            window._update_current_main_account("七色花消消乐")
        window.refresh_table()

        self.assertEqual(window.table.item(0, 0).text(), "主账号状态：七色花消消乐")
        self.assertEqual(window.table.item(1, 0).text(), "导入账号")

    def test_deadline_accounts_are_pinned_and_sorted_by_nearest_time(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(
                name="无截止账号", state_path="storage/shared.json", is_entry_account=False, last_status="抓取成功"
            ),
            AccountConfig(
                name="较远截止账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取成功",
                last_deadline="2026-04-25 12:00:00",
            ),
            AccountConfig(
                name="较近截止账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取成功",
                last_deadline="2026-04-19 09:00:00",
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 0).text(), "主账号状态：未记录")
        self.assertEqual(window.table.item(1, 0).text(), "较近截止账号")
        self.assertEqual(window.table.item(2, 0).text(), "较远截止账号")
        self.assertEqual(window.table.item(3, 0).text(), "无截止账号")

    def test_entry_account_name_aligns_left_and_imported_account_stays_centered(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        with patch("desktop_py.ui.main_window.save_settings"):
            window._update_current_main_account("七色花消消乐")

        window.refresh_table()

        self.assertEqual(
            window.table.item(0, 0).textAlignment(),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
        )
        self.assertEqual(
            window.table.item(1, 0).textAlignment(),
            int(Qt.AlignmentFlag.AlignCenter),
        )

    def test_entry_account_deadline_shows_placeholder(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 1).text(), "--")

    def test_init_clears_persisted_current_main_account_name(self):
        with (
            patch(
                "desktop_py.ui.main_window.load_settings", return_value=AppSettings(current_main_account_name="强强")
            ),
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
        ):
            window = MainWindow()
            self.addCleanup(window.close)

        self.assertEqual(window.settings.current_main_account_name, "")
        mock_save_settings.assert_called_once()
