from desktop_py.core.models import PendingNotification
from py_tests.ui_test_support import (
    AccountConfig,
    FetchResult,
    MainWindow,
    UiTestBase,
    patch,
)


class UiNotificationTestCase(UiTestBase):
    def test_send_summary_uses_current_webhook_without_saving_settings(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
            ),
        ]
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with (
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.send_summary()

        mock_save_settings.assert_not_called()
        self.assertEqual(window.settings.feishu_webhook, "https://open.feishu.cn/open-apis/bot/v2/hook/demo")
        mock_run_thread.assert_called_once()

    def test_send_summary_preserves_actual_account_name_in_summary(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="已完成详情页抓取。；当前实际账号：实际账号A",
            ),
        ]
        captured_results = []

        def fake_build_summary(results):
            captured_results.extend(results)
            return "summary"

        with patch.object(window, "_run_thread") as mock_run_thread:
            window._send_summary_with_webhook("https://example.com/hook")

        job = mock_run_thread.call_args.args[0]
        with (
            patch("desktop_py.ui.main_window.build_summary", side_effect=fake_build_summary),
            patch("desktop_py.ui.main_window.send_feishu_text"),
        ):
            job(lambda _message: None)
        self.assertEqual(captured_results[0].actual_account_name, "实际账号A")

    def test_send_summary_clears_pushed_fetch_state_after_success(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="主账号",
                state_path="storage/shared.json",
                is_entry_account=True,
                enabled=True,
                last_status="登录有效",
                last_deadline="",
                last_note="可直接抓取",
            ),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="已完成详情页抓取。",
            ),
            AccountConfig(
                name="导入账号B",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=False,
                last_status="抓取成功",
                last_deadline="2026-04-21 11:42:31",
                last_note="已完成详情页抓取。",
            ),
            AccountConfig(
                name="导入账号C",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取失败",
                last_deadline="",
                last_note="页面未出现业务 iframe",
            ),
            AccountConfig(
                name="导入账号D",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="",
                last_note="通知中心未读消息 1 条：小程序微信认证年审通知",
            ),
        ]

        with (
            patch.object(window, "_run_thread") as mock_run_thread,
            patch("desktop_py.ui.main_window.save_accounts") as mock_save_accounts,
        ):
            window._send_summary_with_webhook("https://example.com/hook")
            on_success = mock_run_thread.call_args.kwargs["on_success"]
            on_success(None)

        accounts_by_name = {account.name: account for account in window.accounts}
        self.assertEqual(accounts_by_name["主账号"].last_status, "登录有效")
        self.assertEqual(accounts_by_name["导入账号A"].last_deadline, "")
        self.assertEqual(accounts_by_name["导入账号A"].last_status, "")
        self.assertEqual(accounts_by_name["导入账号A"].last_note, "")
        self.assertEqual(accounts_by_name["导入账号B"].last_deadline, "2026-04-21 11:42:31")
        self.assertEqual(accounts_by_name["导入账号C"].last_status, "抓取失败")
        self.assertEqual(accounts_by_name["导入账号C"].last_note, "页面未出现业务 iframe")
        self.assertEqual(accounts_by_name["导入账号D"].last_deadline, "")
        self.assertEqual(accounts_by_name["导入账号D"].last_status, "")
        self.assertEqual(accounts_by_name["导入账号D"].last_note, "")
        mock_save_accounts.assert_called_once_with(window.accounts)
        self.assertIn("已清理推送后的抓取状态", window.log_edit.toPlainText())

    def test_send_summary_does_not_clear_before_send_success(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="已完成详情页抓取。",
            ),
        ]

        with patch.object(window, "_run_thread"):
            window._send_summary_with_webhook("https://example.com/hook")

        self.assertEqual(window.accounts[0].last_deadline, "2026-04-20 11:42:31")
        self.assertEqual(window.accounts[0].last_status, "抓取成功")
        self.assertEqual(window.accounts[0].last_note, "已完成详情页抓取。")

    def test_send_summary_saves_pending_notification_when_send_fails(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="已完成详情页抓取。",
            ),
        ]

        with (
            patch.object(window, "_run_thread") as mock_run_thread,
            patch("desktop_py.ui.main_window.append_pending_notification") as mock_append,
        ):
            window._send_summary_with_webhook("https://example.com/hook")
            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.send_feishu_text", side_effect=RuntimeError("网络失败")):
                with self.assertRaisesRegex(RuntimeError, "网络失败"):
                    job(lambda _message: None)

        mock_append.assert_called_once()
        self.assertIn("导入账号A", mock_append.call_args.args[0].content)

    def test_resend_pending_notifications_sends_and_removes_queue_items(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")
        notification = PendingNotification(
            id="abc123",
            content="待补发内容",
            created_at="2026-05-15 22:00:00",
        )

        with (
            patch.object(window, "_run_thread") as mock_run_thread,
            patch("desktop_py.ui.main_window.load_pending_notifications", return_value=[notification]),
            patch("desktop_py.ui.main_window.remove_pending_notifications") as mock_remove,
            patch("desktop_py.ui.main_window.send_feishu_text") as mock_send,
        ):
            window.resend_pending_notifications()
            job = mock_run_thread.call_args.args[0]
            sent_count = job(window.append_log)

        self.assertEqual(sent_count, 1)
        mock_send.assert_called_once_with("https://open.feishu.cn/open-apis/bot/v2/hook/demo", "待补发内容")
        mock_remove.assert_called_once_with(["abc123"])
        self.assertIn("已补发飞书消息：abc123", window.log_edit.toPlainText())

    def test_resend_pending_notifications_reports_empty_queue(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with (
            patch.object(window, "_run_thread") as mock_run_thread,
            patch("desktop_py.ui.main_window.load_pending_notifications", return_value=[]),
        ):
            window.resend_pending_notifications()

        mock_run_thread.assert_not_called()
        self.assertIn("当前没有待补发飞书消息", window.log_edit.toPlainText())

    def test_auto_fetch_and_send_uses_fetch_job_and_progress_callback(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.auto_fetch_and_send()

        mock_run_thread.assert_called_once()
        self.assertEqual(mock_run_thread.call_args.kwargs["on_progress"], window._mark_fetch_progress)

    def test_auto_fetch_and_send_success_callback_only_sends_when_called(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.auto_fetch_and_send()

        on_success = mock_run_thread.call_args.kwargs["on_success"]
        with patch.object(window, "_send_summary_with_webhook") as mock_send:
            on_success([])
        mock_send.assert_called_once()

    def test_auto_fetch_and_send_skips_summary_when_all_results_match_backend_entry_failure(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.auto_fetch_and_send()

        on_success = mock_run_thread.call_args.kwargs["on_success"]
        results = [
            FetchResult(
                account_name="导入账号A",
                ok=False,
                note="当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。",
            ),
            FetchResult(
                account_name="导入账号B",
                ok=False,
                note="当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。",
            ),
        ]
        with patch.object(window, "_send_summary_with_webhook") as mock_send:
            on_success(results)
        mock_send.assert_not_called()
        self.assertIn("自动抓取推送已跳过", window.log_edit.toPlainText())

    def test_auto_fetch_and_send_still_sends_summary_when_results_are_mixed(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.webhook_edit.setText("https://open.feishu.cn/open-apis/bot/v2/hook/demo")

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.auto_fetch_and_send()

        on_success = mock_run_thread.call_args.kwargs["on_success"]
        results = [
            FetchResult(
                account_name="导入账号A",
                ok=False,
                note="当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。",
            ),
            FetchResult(account_name="导入账号B", ok=True, note="已完成详情页抓取。"),
        ]
        with patch.object(window, "_send_summary_with_webhook") as mock_send:
            on_success(results)
        mock_send.assert_called_once()

    def test_actions_include_single_run_fetch_and_push_button(self):
        window = MainWindow()
        self.addCleanup(window.close)

        buttons = [button.text() for button in window.findChildren(type(window.login_button)) if button.text()]

        self.assertIn("抓取并推送", buttons)
        self.assertIn("停止抓取", buttons)
        self.assertIn("登录续期", buttons)
        self.assertIn("补发飞书", buttons)
        self.assertNotIn("抓取全部", buttons)

    def test_send_summary_button_moves_to_fetch_all_slot(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        self.assertIsNotNone(window.send_summary_button)
        self.assertIsNotNone(window.fetch_selected_button)
        self.assertIsNotNone(window.auto_fetch_push_switch)
        self.assertGreater(window.send_summary_button.x(), window.fetch_selected_button.x())
        self.assertLess(window.send_summary_button.x(), window.auto_fetch_push_switch.x())

    def test_auto_fetch_and_send_button_moves_to_previous_send_summary_slot(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        auto_fetch_button = next(
            button for button in window.findChildren(type(window.login_button)) if button.text() == "抓取并推送"
        )
        self.assertIsNotNone(window.send_summary_button)
        self.assertIsNotNone(window.auto_fetch_push_switch)
        self.assertGreater(auto_fetch_button.x(), window.send_summary_button.x())
        self.assertLess(auto_fetch_button.x(), window.auto_fetch_push_switch.x())
