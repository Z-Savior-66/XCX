from py_tests.ui_test_support import (
    AccountConfig,
    FetchResult,
    MainWindow,
    UiTestBase,
    patch,
)


class UiFetchTestCase(UiTestBase):
    def test_fetch_success_without_deadline_shows_no_pending_and_completed(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取成功",
                last_deadline="",
                last_note="当前账号无待处理申请。",
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 1).text(), "无待处理")
        self.assertEqual(window.table.item(0, 3).text(), "完成")
        self.assertEqual(window.table.item(0, 1).toolTip(), "无待处理")

    def test_fetch_failure_shows_reason_in_deadline_column(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(
                name="导入账号",
                state_path="storage/shared.json",
                is_entry_account=False,
                last_status="抓取失败",
                last_note="切换账号列表中未找到目标账号",
            ),
        ]

        window.refresh_table()

        self.assertEqual(window.table.item(0, 1).text(), "切换账号列表中未找到目标账号")
        self.assertEqual(window.table.item(0, 3).text(), "失败")
        self.assertEqual(window.table.item(0, 1).toolTip(), "切换账号列表中未找到目标账号")

    def test_build_fetch_job_uses_batch_fetcher(self):
        window = MainWindow()
        self.addCleanup(window.close)
        accounts = [
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
        ]
        job = window._build_fetch_job(accounts)
        with patch("desktop_py.ui.main_window.fetch_accounts_batch", return_value=[]) as mock_batch:
            result = job(lambda _message: None, lambda _payload: None)

        self.assertEqual(result, [])
        mock_batch.assert_called_once()

    def test_stop_fetch_button_enabled_when_background_task_exists(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._threads.append(object())

        window._update_action_buttons()

        self.assertTrue(window.stop_fetch_button.isEnabled())

    def test_mark_fetch_result_does_not_propagate_feedback_url_to_shared_entry_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, feedback_url=""),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, feedback_url=""),
        ]
        result = FetchResult(
            account_name="导入账号A",
            ok=True,
            page_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
        )

        with patch("desktop_py.ui.main_window.save_accounts"), patch.object(window, "_update_current_main_account"):
            window._mark_fetch_result(window.accounts[1], result)

        self.assertEqual(window.accounts[0].feedback_url, "")
        self.assertEqual(window.accounts[1].feedback_url, result.page_url)

    def test_stop_fetching_keeps_button_enabled_until_worker_exits(self):
        window = MainWindow()
        self.addCleanup(window.close)
        calls: list[str] = []

        class FakeTaskRunner:
            def cancel_all(self):
                calls.append("cancel")

            def shutdown(self):
                return None

        window._task_runner = FakeTaskRunner()
        window._threads = [object()]
        window._update_action_buttons()

        window.stop_fetching()

        self.assertEqual(calls, ["cancel"])
        self.assertTrue(window.stop_fetch_button.isEnabled())
        self.assertIn("已请求停止当前后台抓取任务", window.log_edit.toPlainText())

    def test_entry_account_cannot_fetch_selected(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号", state_path="storage/shared.json", is_entry_account=False),
        ]
        window.refresh_table()
        window.table.selectRow(0)

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.fetch_selected()

        mock_information.assert_called_once()
        self.assertIn("主账号不参与抓取", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_fetch_all_skips_entry_account(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False, enabled=True),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False, enabled=False),
        ]

        with patch.object(window, "_run_thread") as mock_run_thread:
            window.fetch_all()

        mock_run_thread.assert_called_once()
        self.assertEqual(mock_run_thread.call_args.kwargs["on_progress"], window._mark_fetch_progress)

    def test_fetch_all_requires_imported_accounts(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True, enabled=True),
        ]

        with (
            patch.object(window, "_show_info") as mock_information,
            patch.object(window, "_run_thread") as mock_run_thread,
        ):
            window.fetch_all()

        mock_information.assert_called_once()
        self.assertIn("没有可抓取的导入账号", mock_information.call_args.args[1])
        mock_run_thread.assert_not_called()

    def test_mark_fetch_progress_updates_account_row_immediately(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with patch("desktop_py.ui.main_window.save_accounts"), patch("desktop_py.ui.main_window.save_settings"):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=True,
                    actual_account_name="萌萌连消",
                    deadline_text="2026-04-18 10:30:00",
                    note="已完成详情页抓取。",
                    page_url="https://example.com/detail",
                )
            )

        self.assertEqual(window.table.item(1, 1).text(), "2026-04-18 10:30:00")
        self.assertEqual(window.table.item(1, 2).text(), "抓取成功")
        self.assertEqual(window.table.item(1, 3).text(), "完成")

    def test_mark_fetch_progress_updates_ui_even_when_save_accounts_fails(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with (
            patch("desktop_py.ui.main_window.save_accounts", side_effect=RuntimeError("磁盘写入失败")),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=True,
                    actual_account_name="萌萌连消",
                    deadline_text="2026-04-18 10:30:00",
                    note="已完成详情页抓取。",
                    page_url="https://example.com/detail",
                )
            )

        self.assertEqual(window.table.item(1, 1).text(), "2026-04-18 10:30:00")
        self.assertEqual(window.table.item(1, 2).text(), "抓取成功")
        self.assertEqual(window.table.item(1, 3).text(), "完成")
        log_text = window.log_edit.toPlainText()
        self.assertIn("抓取已完成，但账号状态暂未写入 data/accounts.json：磁盘写入失败", log_text)
        self.assertNotIn("保存抓取结果失败", log_text)

    def test_mark_batch_results_reports_account_state_save_failure_without_fetch_failure(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with patch("desktop_py.ui.main_window.save_accounts", side_effect=PermissionError("拒绝访问")):
            window._mark_batch_results(
                [
                    FetchResult(
                        account_name="导入账号A",
                        ok=True,
                        deadline_text="",
                        note="当前账号无待处理申请。",
                    )
                ]
            )

        log_text = window.log_edit.toPlainText()
        self.assertEqual(window.table.item(1, 2).text(), "抓取成功")
        self.assertIn("抓取已完成，但账号状态暂未写入 data/accounts.json：拒绝访问", log_text)
        self.assertIn("批量抓取已完成。", log_text)
        self.assertNotIn("保存批量抓取结果失败", log_text)

    def test_mark_fetch_progress_hides_diagnostic_manifest_path(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with (
            patch("desktop_py.ui.main_window.save_accounts"),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=True,
                    actual_account_name="萌萌连消",
                    deadline_text="2026-04-18 10:30:00",
                    note="已完成详情页抓取。",
                    page_url="https://example.com/detail",
                )
            )

        log_text = window.log_edit.toPlainText()
        self.assertNotIn("诊断产物", log_text)
        self.assertNotIn("fetch_manifest.json", log_text)

    def test_mark_fetch_progress_cleans_diagnostic_artifacts_without_logging_path(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with (
            patch("desktop_py.ui.main_window.save_accounts"),
            patch("desktop_py.ui.main_window.save_settings"),
            patch("desktop_py.ui.main_window.cleanup_account_diagnostics", return_value=2) as mock_cleanup,
        ):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=True,
                    actual_account_name="萌萌连消",
                    deadline_text="",
                    note="当前账号无待处理申请。",
                    page_url="https://example.com/detail",
                )
            )

        mock_cleanup.assert_called_once_with("导入账号A", retention_days=14)
        self.assertNotIn("fetch_manifest.json", window.log_edit.toPlainText())

    def test_mark_fetch_progress_keeps_regular_failure_reason_in_result_log(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with (
            patch("desktop_py.ui.main_window.save_accounts"),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=False,
                    note="切换账号列表中未找到目标账号",
                )
            )

        self.assertEqual(window.table.item(1, 2).text(), "抓取失败")
        self.assertEqual(window.table.item(1, 3).text(), "失败")

    def test_append_log_keeps_fetch_summary_details_out_of_status_bar(self):
        window = MainWindow()
        self.addCleanup(window.close)

        window.append_log(
            "账号 梦幻光环 抓取成功：\n1.通知中心无目标未读消息。\n2.未成年退款申请处理截止时间：2026-05-18 10:00:00。"
        )

        self.assertIn("1.通知中心无目标未读消息。", window.log_edit.toPlainText())
        self.assertEqual(window._status_label.text(), "当前状态：就绪")

    def test_mark_fetch_progress_treats_no_deadline_note_as_success(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with (
            patch("desktop_py.ui.main_window.save_accounts"),
            patch("desktop_py.ui.main_window.save_settings"),
        ):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=False,
                    note="截止时间内无待处理",
                )
            )

        self.assertEqual(window.table.item(1, 2).text(), "抓取成功")
        self.assertEqual(window.table.item(1, 3).text(), "完成")

    def test_mark_fetch_progress_updates_main_account_name_immediately(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window.accounts = [
            AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True),
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
        ]

        with patch("desktop_py.ui.main_window.save_accounts"), patch("desktop_py.ui.main_window.save_settings"):
            window._mark_fetch_progress(
                FetchResult(
                    account_name="导入账号A",
                    ok=True,
                    actual_account_name="萌萌连消",
                    deadline_text="",
                    note="当前账号无待处理申请。",
                    page_url="https://example.com/detail",
                )
            )

        self.assertEqual(window.table.item(0, 0).text(), "主账号状态：萌萌连消")
