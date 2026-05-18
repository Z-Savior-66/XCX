from py_tests.ui_test_support import (
    AUTO_RENEW_INTERVAL_MAX_MS,
    AUTO_RENEW_INTERVAL_MIN_MS,
    AccountConfig,
    AppSettings,
    MainWindow,
    UiTestBase,
    datetime,
    os,
    patch,
)


class UiSchedulingTestCase(UiTestBase):
    def test_auto_fetch_push_switch_uses_saved_setting(self):
        with (
            patch("desktop_py.ui.main_window.load_settings", return_value=AppSettings(auto_fetch_push_enabled=True)),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window = MainWindow()
            self.addCleanup(window.close)

        self.assertIsNotNone(window.auto_fetch_push_switch)
        self.assertTrue(window.auto_fetch_push_switch.isChecked())

    def test_toggle_auto_fetch_push_saves_setting_and_reschedules(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.auto_fetch_push_switch.setChecked(False)

        with (
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            patch.object(window, "_apply_auto_fetch_push_schedule") as mock_schedule,
        ):
            window.auto_fetch_push_switch.setChecked(True)

        self.assertTrue(window.settings.auto_fetch_push_enabled)
        mock_save_settings.assert_called_once()
        mock_schedule.assert_called_once()

    def test_save_current_settings_preserves_schedule_state(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.settings.next_auto_renew_at = "2026-05-18 12:00:00"
        window.settings.next_auto_fetch_push_at = "2026-05-19 09:00:00"
        window.settings.auto_renew_schedule_reason = "失败退避"
        window.settings.auto_fetch_push_schedule_reason = "每天 09:00 自动执行"
        window.settings.schedule_reason = "失败退避"

        with (
            patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            patch.object(window, "_apply_auto_fetch_push_schedule"),
        ):
            window.save_current_settings()

        saved_settings = mock_save_settings.call_args.args[0]
        self.assertEqual(saved_settings.next_auto_renew_at, "2026-05-18 12:00:00")
        self.assertEqual(saved_settings.next_auto_fetch_push_at, "2026-05-19 09:00:00")
        self.assertEqual(saved_settings.auto_renew_schedule_reason, "失败退避")
        self.assertEqual(saved_settings.auto_fetch_push_schedule_reason, "每天 09:00 自动执行")
        self.assertEqual(saved_settings.schedule_reason, "失败退避")

    def test_milliseconds_until_next_auto_fetch_push_before_nine(self):
        window = MainWindow()
        self.addCleanup(window.close)

        milliseconds = window._milliseconds_until_next_auto_fetch_push(datetime(2026, 4, 18, 8, 30, 0))

        self.assertEqual(milliseconds, 30 * 60 * 1000)

    def test_milliseconds_until_next_auto_fetch_push_after_nine(self):
        window = MainWindow()
        self.addCleanup(window.close)

        milliseconds = window._milliseconds_until_next_auto_fetch_push(datetime(2026, 4, 18, 9, 30, 0))

        self.assertEqual(milliseconds, int(23.5 * 60 * 60 * 1000))

    def test_apply_auto_fetch_push_schedule_persists_next_run_state(self):
        from desktop_py.ui.schedule_actions import apply_auto_fetch_push_schedule

        window = MainWindow()
        self.addCleanup(window.close)
        window.settings.auto_fetch_push_enabled = True
        saved_settings = []

        with patch.object(window, "_milliseconds_until_next_auto_fetch_push", return_value=30 * 60 * 1000):
            apply_auto_fetch_push_schedule(
                window,
                save_settings_fn=lambda settings: saved_settings.append(settings.to_dict()),
                now_fn=lambda: datetime(2026, 5, 18, 8, 30, 0),
            )

        self.assertEqual(window.settings.next_auto_fetch_push_at, "2026-05-18 09:00:00")
        self.assertEqual(window.settings.auto_fetch_push_schedule_reason, "每天 09:00 自动执行")
        self.assertEqual(saved_settings[-1]["next_auto_fetch_push_at"], "2026-05-18 09:00:00")

    def test_apply_auto_fetch_push_schedule_clears_state_when_disabled(self):
        from desktop_py.ui.schedule_actions import apply_auto_fetch_push_schedule

        window = MainWindow()
        self.addCleanup(window.close)
        window.settings.auto_fetch_push_enabled = False
        window.settings.next_auto_fetch_push_at = "2026-05-18 09:00:00"
        window.settings.auto_fetch_push_schedule_reason = "每天 09:00 自动执行"
        saved_settings = []

        apply_auto_fetch_push_schedule(
            window, save_settings_fn=lambda settings: saved_settings.append(settings.to_dict())
        )

        self.assertEqual(window.settings.next_auto_fetch_push_at, "")
        self.assertEqual(window.settings.auto_fetch_push_schedule_reason, "自动抓取推送未开启")
        self.assertEqual(saved_settings[-1]["next_auto_fetch_push_at"], "")

    def test_handle_auto_fetch_push_timeout_reschedules_and_runs_job(self):
        window = MainWindow()
        self.addCleanup(window.close)

        with (
            patch.object(window, "_apply_auto_fetch_push_schedule") as mock_schedule,
            patch.object(window, "_run_auto_fetch_push") as mock_run,
        ):
            window._handle_auto_fetch_push_timeout()

        mock_schedule.assert_called_once()
        mock_run.assert_called_once()

    def test_auto_renew_interval_uses_two_to_four_hours_range(self):
        self.assertEqual(AUTO_RENEW_INTERVAL_MIN_MS, 2 * 60 * 60 * 1000)
        self.assertEqual(AUTO_RENEW_INTERVAL_MAX_MS, 4 * 60 * 60 * 1000)

    def test_startup_jobs_trigger_auto_renew_by_default(self):
        from desktop_py.ui.main_window_actions_impl import schedule_startup_jobs

        calls = []

        class FakeTimer:
            @staticmethod
            def singleShot(_delay, callback):
                calls.append(callback)

        window = type(
            "FakeWindow",
            (),
            {
                "_run_auto_renew": object(),
                "_auto_validate_entry_account": object(),
                "_apply_auto_fetch_push_schedule": object(),
                "_apply_auto_renew_schedule": object(),
            },
        )()

        schedule_startup_jobs(window, timer_cls=FakeTimer)

        self.assertEqual(
            calls,
            [
                window._run_auto_renew,
                window._auto_validate_entry_account,
                window._apply_auto_fetch_push_schedule,
                window._apply_auto_renew_schedule,
            ],
        )

    def test_handle_auto_renew_timeout_reschedules_and_runs_job(self):
        window = MainWindow()
        self.addCleanup(window.close)

        with (
            patch.object(window, "_apply_auto_renew_schedule") as mock_schedule,
            patch.object(window, "_run_auto_renew") as mock_run,
        ):
            window._handle_auto_renew_timeout()

        mock_schedule.assert_called_once()
        mock_run.assert_called_once()

    def test_apply_auto_renew_schedule_uses_random_interval_in_range(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = []

        with (
            patch("desktop_py.ui.main_window_actions_impl.random.randint", return_value=12345678) as mock_randint,
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._apply_auto_renew_schedule()

        mock_randint.assert_called_once_with(AUTO_RENEW_INTERVAL_MIN_MS, AUTO_RENEW_INTERVAL_MAX_MS)
        self.assertEqual(window._auto_renew_timer.interval(), 12345678)

    def test_apply_auto_renew_schedule_persists_next_run_state(self):
        from desktop_py.ui.schedule_actions import apply_auto_renew_schedule

        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = []
        saved_settings = []

        with patch("desktop_py.ui.schedule_actions.random.randint", return_value=2 * 60 * 60 * 1000):
            apply_auto_renew_schedule(
                window,
                min_auto_renew_interval_ms=AUTO_RENEW_INTERVAL_MIN_MS,
                max_auto_renew_interval_ms=AUTO_RENEW_INTERVAL_MAX_MS,
                save_settings_fn=lambda settings: saved_settings.append(settings.to_dict()),
                now_fn=lambda: datetime(2026, 5, 18, 10, 0, 0),
            )

        self.assertEqual(window.settings.next_auto_renew_at, "2026-05-18 12:00:00")
        self.assertEqual(window.settings.auto_renew_schedule_reason, "未配置主账号，使用常规巡检间隔")
        self.assertEqual(saved_settings[-1]["next_auto_renew_at"], "2026-05-18 12:00:00")

    def test_apply_auto_renew_schedule_prioritizes_expiring_cookie(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True)]

        report = type(
            "Report",
            (),
            {
                "min_cookie_seconds_remaining": 1800,
                "reason": "微信后台 Cookie 最短剩余 1800 秒",
            },
        )()
        with (
            patch("desktop_py.ui.schedule_actions.analyze_storage_state", return_value=report),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._apply_auto_renew_schedule()

        self.assertEqual(window._auto_renew_timer.interval(), 15 * 60 * 1000)
        self.assertIn("提前续期", window.log_edit.toPlainText())

    def test_apply_auto_renew_schedule_uses_failure_backoff(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="主账号",
                state_path="storage/shared.json",
                is_entry_account=True,
                session_renewal_failures=3,
            )
        ]

        with patch("desktop_py.ui.main_window.save_settings"):
            window._apply_auto_renew_schedule()

        self.assertEqual(window._auto_renew_timer.interval(), AUTO_RENEW_INTERVAL_MAX_MS * 3)
        self.assertIn("失败退避", window.settings.auto_renew_schedule_reason)
        self.assertIn("失败退避", window.log_edit.toPlainText())

    def test_run_auto_renew_uses_entry_account(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.accounts = [
                AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
                AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._run_auto_renew()

            mock_run_thread.assert_called_once()
            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew:
                self.assertTrue(job(lambda _message: None))
                self.assertEqual(mock_renew.call_args.args[0].name, "主账号")

    def test_run_auto_renew_closes_group_runtime_before_renew(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.accounts = [
                AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            ]
            calls: list[str] = []

            with (
                patch("desktop_py.ui.main_window.close_all_group_runtimes", side_effect=lambda: calls.append("close")),
                patch(
                    "desktop_py.ui.main_window.renew_account_state",
                    side_effect=lambda *_args: calls.append("renew") or True,
                ),
                patch.object(window, "_run_thread") as mock_run_thread,
            ):
                window._run_auto_renew()

                job = mock_run_thread.call_args.args[0]
                self.assertTrue(job(lambda _message: None))

            self.assertEqual(calls, ["close", "renew"])

    def test_renew_selected_uses_selected_entry_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()

        with (
            patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.renew_selected()

        mock_run_thread.assert_called_once()
        job = mock_run_thread.call_args.args[0]
        self.assertTrue(job(lambda _message: None))
        self.assertEqual(mock_renew.call_args.args[0].name, "主账号")

    def test_renew_selected_closes_group_runtime_before_renew(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
        ]
        window.refresh_table()
        calls: list[str] = []

        with (
            patch("desktop_py.ui.main_window.close_all_group_runtimes", side_effect=lambda: calls.append("close")),
            patch(
                "desktop_py.ui.main_window.renew_account_state",
                side_effect=lambda *_args: calls.append("renew") or True,
            ),
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.renew_selected()

            job = mock_run_thread.call_args.args[0]
            self.assertTrue(job(lambda _message: None))

        self.assertEqual(calls, ["close", "renew"])

    def test_run_auto_renew_passes_headless_fetch_setting(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.settings.headless_fetch = False
            window.accounts = [
                AccountConfig(name="entry", state_path="storage/shared.json", is_entry_account=True),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._run_auto_renew()

            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew:
                self.assertTrue(job(lambda _message: None))

            self.assertEqual(mock_renew.call_args.args[0].name, "entry")
            self.assertFalse(mock_renew.call_args.args[3])

    def test_run_auto_renew_passes_switch_account_candidates(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.settings.browser_profile_dir = ""
            window.accounts = [
                AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
                AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
                AccountConfig(
                    name="导入账号B", state_path="storage/shared.json", is_entry_account=False, enabled=False
                ),
                AccountConfig(name="其他登录态", state_path="storage/other.json", is_entry_account=False),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._run_auto_renew()

            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew:
                self.assertTrue(job(lambda _message: None))

            self.assertEqual(
                mock_renew.call_args.args[4],
                ["导入账号A"],
            )

    def test_run_auto_renew_uses_shared_profile_candidates_across_state_paths(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window.settings.browser_profile_dir = "C:/profile"
            window.accounts = [
                AccountConfig(name="主账号", state_path="storage/main.json", is_entry_account=True),
                AccountConfig(name="导入账号A", state_path="storage/shared-a.json", is_entry_account=False),
                AccountConfig(name="导入账号B", state_path="", is_entry_account=False),
                AccountConfig(
                    name="禁用账号", state_path="storage/shared-b.json", is_entry_account=False, enabled=False
                ),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._run_auto_renew()

            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew:
                self.assertTrue(job(lambda _message: None))

            self.assertEqual(
                mock_renew.call_args.args[4],
                ["导入账号A", "导入账号B"],
            )

    def test_run_auto_renew_does_not_inherit_feedback_url_from_shared_account(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            shared_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=shared"
            window.accounts = [
                AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, feedback_url=""),
                AccountConfig(
                    name="导入账号A",
                    state_path="storage/shared.json",
                    is_entry_account=False,
                    feedback_url=shared_feedback_url,
                ),
            ]

            with patch.object(window, "_run_thread") as mock_run_thread:
                window._run_auto_renew()

            job = mock_run_thread.call_args.args[0]
            with patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew:
                self.assertTrue(job(lambda _message: None))

            self.assertEqual(mock_renew.call_args.args[0].feedback_url, "")

    def test_renew_selected_passes_headless_fetch_setting(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.settings.headless_fetch = False
        window.accounts = [
            AccountConfig(name="entry", state_path="storage/shared.json", is_entry_account=True),
        ]
        window.refresh_table()

        with (
            patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.renew_selected()

        job = mock_run_thread.call_args.args[0]
        self.assertTrue(job(lambda _message: None))
        self.assertEqual(mock_renew.call_args.args[0].name, "entry")
        self.assertFalse(mock_renew.call_args.args[3])

    def test_renew_selected_does_not_inherit_feedback_url_from_shared_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        shared_feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=shared"
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, feedback_url=""),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                feedback_url=shared_feedback_url,
            ),
        ]
        window.refresh_table()

        with (
            patch("desktop_py.ui.main_window.renew_account_state", return_value=True) as mock_renew,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.renew_selected()

        job = mock_run_thread.call_args.args[0]
        self.assertTrue(job(lambda _message: None))
        self.assertEqual(mock_renew.call_args.args[0].feedback_url, "")

    def test_login_renew_and_validate_buttons_keep_left_to_right_order(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        self.assertLess(window.login_button.x(), window.validate_button.x())
        self.assertLess(window.validate_button.x(), window.renew_button.x())

    def test_run_auto_renew_skips_when_background_task_exists(self):
        with patch.dict(os.environ, {"QT_QPA_PLATFORM": "windows"}):
            window = MainWindow()
            self.addCleanup(window.close)
            window._threads.append(object())
            window._update_action_buttons()

            with (
                patch.object(window, "_run_thread") as mock_run_thread,
                patch("desktop_py.ui.main_window.save_settings") as mock_save_settings,
            ):
                window._run_auto_renew()

            mock_run_thread.assert_not_called()
            mock_save_settings.assert_called_once()
            self.assertIn("当前存在后台任务", window.log_edit.toPlainText())
            self.assertEqual(window._auto_renew_timer.interval(), 10 * 60 * 1000)
            self.assertIn("延后重试", window.settings.auto_renew_schedule_reason)

    def test_mark_auto_renew_result_counts_failures_and_resets_on_success(self):
        window = MainWindow()
        self.addCleanup(window.close)
        account = AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True)
        window.accounts = [account]

        with patch("desktop_py.ui.main_window.save_accounts"):
            window._mark_auto_renew_result(account, False)
            window._mark_auto_renew_result(account, False)
            window._mark_auto_renew_result(account, True)

        self.assertEqual(account.session_renewal_failures, 0)
        self.assertEqual(account.last_note, "自动续期成功，保存后复验通过，可直接抓取")
        log_text = window.log_edit.toPlainText()
        self.assertIn("连续失败 2 次", log_text)
        self.assertIn("保存后复验", log_text)

    def test_run_auto_fetch_push_requires_webhook(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.webhook_edit.setText("")
        window.settings.feishu_webhook = ""

        with patch.object(window, "_run_thread") as mock_run_thread:
            window._run_auto_fetch_push()

        mock_run_thread.assert_not_called()
        self.assertIn("未配置飞书 Webhook", window.log_edit.toPlainText())

    def test_run_auto_fetch_push_uses_saved_webhook_and_progress_callback(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        window.settings.feishu_webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/demo"
        window.webhook_edit.setText("")

        with patch.object(window, "_run_thread") as mock_run_thread:
            window._run_auto_fetch_push()

        mock_run_thread.assert_called_once()
        self.assertEqual(mock_run_thread.call_args.kwargs["on_progress"], window._mark_fetch_progress)
