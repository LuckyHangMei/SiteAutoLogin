"""工作日判断（法定节假日 / 调休补班 / 周末）的离线测试。"""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from autologin import holiday


class WorkdayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "holidays.json"
        patcher = patch.object(holiday, "HOLIDAYS_FILE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, holidays=(), workdays=()):
        self.path.write_text(
            json.dumps({"holidays": list(holidays), "workdays": list(workdays)}),
            encoding="utf-8",
        )

    def test_missing_file_falls_back_to_weekends(self):
        # 2026-10-19 是周一，2026-10-17 是周六
        self.assertTrue(holiday.is_workday(date(2026, 10, 19)))
        self.assertFalse(holiday.is_workday(date(2026, 10, 17)))

    def test_holiday_and_makeup_workday_override_weekday_rule(self):
        self.write(holidays=["2026-10-19"], workdays=["2026-10-17"])
        self.assertFalse(holiday.is_workday(date(2026, 10, 19)))
        self.assertTrue(holiday.is_workday(date(2026, 10, 17)))

    def test_next_workday_skips_holidays(self):
        self.write(holidays=["2026-10-19", "2026-10-20"])
        # 从周日 10-18 往后找：19、20 放假，21 才是工作日
        self.assertEqual(holiday.next_workday(date(2026, 10, 18)), date(2026, 10, 21))

    def test_broken_file_is_treated_as_empty(self):
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertLogs("auto_login", level="WARNING"):
            self.assertTrue(holiday.is_workday(date(2026, 10, 19)))

    def test_describe_today_mentions_status(self):
        self.write(holidays=[date.today().strftime("%Y-%m-%d")])
        self.assertIn("法定节假日", holiday.describe_today())
        self.assertFalse(holiday.is_workday_now())


if __name__ == "__main__":
    unittest.main()
