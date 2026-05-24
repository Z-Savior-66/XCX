import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from desktop_py.core.models import AccountConfig, ScheduleState
from desktop_py.core.schedule_state_service import (
    auto_renew_schedule_interval,
    format_next_schedule_time,
    next_auto_fetch_push_interval_ms,
    persist_schedule_state,
)


class ScheduleStateServiceTestCase(unittest.TestCase):
    def test_next_auto_fetch_push_interval_ms_matches_daily_schedule(self):
        self.assertEqual(next_auto_fetch_push_interval_ms(datetime(2026, 4, 18, 8, 30, 0)), 30 * 60 * 1000)
        self.assertEqual(next_auto_fetch_push_interval_ms(datetime(2026, 4, 18, 9, 30, 0)), int(23.5 * 60 * 60 * 1000))

    def test_auto_renew_schedule_interval_uses_expiring_cookie_priority(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True)
        report = SimpleNamespace(min_cookie_seconds_remaining=1800, reason="微信后台 Cookie 最短剩余 1800 秒")

        with patch("desktop_py.core.schedule_state_service.analyze_storage_state", return_value=report):
            interval, reason = auto_renew_schedule_interval(
                account,
                min_auto_renew_interval_ms=2 * 60 * 60 * 1000,
                max_auto_renew_interval_ms=4 * 60 * 60 * 1000,
            )

        self.assertEqual(interval, 15 * 60 * 1000)
        self.assertIn("提前续期", reason)

    def test_persist_schedule_state_updates_state_object(self):
        schedule_state = ScheduleState()
        saved_states = []

        persist_schedule_state(
            schedule_state,
            save_schedule_state_fn=lambda current: saved_states.append(current.to_dict()),
            next_auto_renew_at="2026-05-18 12:00:00",
            next_auto_fetch_push_at="2026-05-19 09:00:00",
            auto_renew_schedule_reason="失败退避",
            auto_fetch_push_schedule_reason="每天 09:00 自动执行",
            schedule_reason="失败退避",
        )

        self.assertEqual(schedule_state.next_auto_renew_at, "2026-05-18 12:00:00")
        self.assertEqual(schedule_state.next_auto_fetch_push_at, "2026-05-19 09:00:00")
        self.assertEqual(saved_states[-1]["schedule_reason"], "失败退避")

    def test_format_next_schedule_time_uses_interval(self):
        self.assertEqual(
            format_next_schedule_time(30 * 60 * 1000, now_fn=lambda: datetime(2026, 5, 18, 8, 30, 0)),
            "2026-05-18 09:00:00",
        )


if __name__ == "__main__":
    unittest.main()
