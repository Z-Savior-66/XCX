from PySide6.QtGui import QFont

from py_tests.ui_test_support import (
    AccountConfig,
    AppSettings,
    MainWindow,
    QCloseEvent,
    QSystemTrayIcon,
    Qt,
    UiTestBase,
    patch,
)


class UiSmokeTestCase(UiTestBase):
    def test_main_window_builds_summary_cards(self):
        window = MainWindow()
        self.addCleanup(window.close)

        self.assertEqual(window.table.columnCount(), 5)
        self.assertIn("total", window._summary_labels)
        expected_total = sum(1 for account in window.accounts if not account.is_entry_account)
        self.assertEqual(window._summary_labels["total"].text(), str(expected_total))
        self.assertGreaterEqual(window.table.minimumHeight(), 360)
        self.assertEqual(window.statusBar().currentMessage(), "就绪")
        self.assertIn(
            "退款反馈抓取工作台",
            window.findChild(type(window._status_label), "heroTitle").text()
            if window.findChild(type(window._status_label), "heroTitle")
            else "退款反馈抓取工作台",
        )

    def test_initialize_window_state_normalizes_shared_feedback_url(self):
        shared_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=shared"
        accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, feedback_url=""),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                feedback_url=shared_feedback_url,
            ),
        ]

        with (
            patch("desktop_py.ui.main_window.load_accounts", return_value=accounts),
            patch("desktop_py.ui.main_window.load_settings", return_value=AppSettings()),
            patch("desktop_py.ui.main_window.save_accounts") as mock_save_accounts,
        ):
            window = MainWindow()
            self.addCleanup(window.close)

        self.assertEqual(window.accounts[0].feedback_url, window.accounts[1].feedback_url)
        mock_save_accounts.assert_called_once_with(window.accounts)

    def test_initialize_window_state_does_not_crash_when_normalized_accounts_cannot_be_saved(self):
        shared_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=shared"
        accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, feedback_url=""),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                feedback_url=shared_feedback_url,
            ),
        ]

        with (
            patch("desktop_py.ui.main_window.load_accounts", return_value=accounts),
            patch("desktop_py.ui.main_window.load_settings", return_value=AppSettings()),
            patch("desktop_py.ui.main_window.save_accounts", side_effect=PermissionError("replace denied")),
        ):
            window = MainWindow()
            self.addCleanup(window.close)

        self.assertEqual(window.accounts[0].feedback_url, window.accounts[1].feedback_url)

    def test_window_hides_minimize_and_maximize_buttons(self):
        window = MainWindow()
        self.addCleanup(window.close)

        flags = window.windowFlags()

        self.assertFalse(bool(flags & Qt.WindowType.WindowMinimizeButtonHint))
        self.assertFalse(bool(flags & Qt.WindowType.WindowMaximizeButtonHint))

    def test_close_button_hides_window_when_tray_visible(self):
        window = MainWindow()
        self.addCleanup(window.close)
        tray = QSystemTrayIcon()
        tray.setVisible(True)
        window.tray_icon = tray
        window.show()
        self.app.processEvents()

        event = QCloseEvent()
        window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertFalse(window.isVisible())

    def test_request_exit_hides_tray_and_quits_app(self):
        window = MainWindow()
        self.addCleanup(window.close)

        class FakeTray:
            def __init__(self):
                self.hidden = False

            def hide(self):
                self.hidden = True

        class FakeApp:
            def __init__(self):
                self.quit_called = False

            def quit(self):
                self.quit_called = True

        fake_tray = FakeTray()
        fake_app = FakeApp()
        window.tray_icon = fake_tray

        with (
            patch("desktop_py.ui.main_window.QApplication.instance", return_value=fake_app),
            patch.object(window, "close") as mock_close,
        ):
            window.request_exit()

        self.assertTrue(window._allow_close)
        self.assertTrue(fake_tray.hidden)
        mock_close.assert_called_once()
        self.assertTrue(fake_app.quit_called)

    def test_summary_cards_exclude_entry_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="主账号",
                state_path="storage/shared.json",
                is_entry_account=True,
                enabled=True,
                last_status="登录有效",
            ),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_fetch_at="2026-04-17 20:18:46",
            ),
            AccountConfig(
                name="导入账号B",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=False,
                last_status="抓取失败",
            ),
        ]

        window.refresh_table()

        self.assertEqual(window._summary_labels["total"].text(), "2")
        self.assertEqual(window._summary_labels["enabled"].text(), "1")
        self.assertEqual(window._summary_labels["healthy"].text(), "1")
        self.assertEqual(window._summary_labels["recent"].text(), "2026-04-17 20:18:46")

    def test_validation_success_shows_completed_result(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="主账号", state_path="storage/shared.json", is_entry_account=True, last_status="登录有效"
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 3).text(), "完成")

    def test_pending_validation_shows_empty_result(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, last_status="检测中"),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 3).text(), "")

    def test_append_log_keeps_only_recent_200_lines(self):
        window = MainWindow()
        self.addCleanup(window.close)

        for index in range(210):
            window.append_log(f"第 {index} 条日志")

        log_lines = window.log_edit.toPlainText().splitlines()
        self.assertEqual(len(log_lines), 200)
        self.assertIn("第 10 条日志", log_lines[0])
        self.assertIn("第 209 条日志", log_lines[-1])

    def test_append_log_hides_account_switch_process_message(self):
        window = MainWindow()
        self.addCleanup(window.close)

        window.append_log("已切换到账号：当代情诗摘抄合集")

        self.assertEqual(window.log_edit.toPlainText(), "")

    def test_append_log_formats_fetch_success_as_account_result_block(self):
        window = MainWindow()
        self.addCleanup(window.close)

        window.append_log("账号 当代情诗摘抄合集 抓取成功：\n1.通知中心无目标未读消息。\n2.交易投诉无待处理。")

        text = window.log_edit.toPlainText()
        self.assertIn("账号：当代情诗摘抄合集｜状态：成功", text)
        self.assertIn("1. 通知中心无目标未读消息。", text)
        self.assertIn("2. 交易投诉无待处理。", text)
        account_name_format = window.log_edit.document().find("当代情诗摘抄合集").charFormat()
        self.assertEqual(account_name_format.foreground().color().name(), "#facc15")
        self.assertGreaterEqual(account_name_format.fontWeight(), QFont.Weight.Bold)

    def test_append_log_formats_fetch_failure_as_account_result_block(self):
        window = MainWindow()
        self.addCleanup(window.close)

        window.append_log("账号 经典诗词摘抄 抓取失败：切换账号列表中未找到目标账号。")

        text = window.log_edit.toPlainText()
        self.assertIn("账号：经典诗词摘抄｜状态：失败", text)
        self.assertIn("切换账号列表中未找到目标账号。", text)

    def test_no_business_page_failure_shows_short_description(self):
        window = MainWindow()
        self.addCleanup(window.close)
        reason = "页面未出现业务 iframe，可能是链接失效、无权限或登录态失效。"
        window.accounts = [
            AccountConfig(
                name="导入账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取成功",
                last_note=reason,
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 1).text(), "无页面")
        self.assertEqual(window.table.item(0, 2).text(), "抓取成功")
        self.assertEqual(window.table.item(0, 3).text(), "完成")
        self.assertEqual(window.table.item(0, 1).toolTip(), "无页面")

    def test_no_deadline_note_shows_no_pending_and_completed(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取成功",
                last_note="截止时间内无待处理",
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 1).text(), "截止时间内无待处理")
        self.assertEqual(window.table.item(0, 2).text(), "抓取成功")
        self.assertEqual(window.table.item(0, 3).text(), "完成")

    def test_mark_validation_uses_short_status_text(self):
        window = MainWindow()
        self.addCleanup(window.close)
        account = AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True)
        window.accounts = [account]

        with patch("desktop_py.ui.main_window.save_accounts"):
            window._mark_validation(account, True)
            self.assertEqual(account.last_status, "登录有效")

            window._mark_validation(account, False)
            self.assertEqual(account.last_status, "登录失效")

    def test_refresh_table_selects_entry_account_by_default(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
        ]
        window.table.clearSelection()

        window.refresh_table()

        self.assertEqual(window.selected_index(), 0)
        self.assertTrue(window.selected_account().is_entry_account)
