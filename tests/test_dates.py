"""날짜 계산과 검사 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import briefing as B  # noqa: E402
from lib import dates as D  # noqa: E402
from tests.test_briefing import SAMPLE  # noqa: E402

MON = date(2026, 10, 5)
CUT = time(8, 30)


class WindowTest(unittest.TestCase):
    def test_window_is_the_target_morning_in_utc(self):
        start, end = D.window(MON, CUT)
        self.assertEqual(f"{start:%Y-%m-%dT%H:%MZ}", "2026-10-04T15:00Z")
        self.assertEqual(f"{end:%Y-%m-%dT%H:%MZ}", "2026-10-04T23:30Z")

    def test_only_mail_that_arrived_today_counts(self):
        self.assertTrue(D.in_window("2026-10-04T16:13:15Z", MON, CUT))     # 월 01:13
        self.assertTrue(D.in_window("2026-10-04T21:42:16Z", MON, CUT))     # 월 06:42
        self.assertFalse(D.in_window("2026-10-04T23:40:00Z", MON, CUT))    # 월 08:40, 기준 시각 뒤
        self.assertFalse(D.in_window("2026-10-02T21:46:44Z", MON, CUT))    # 토 06:46
        self.assertFalse(D.in_window("2026-10-02T02:52:16Z", MON, CUT))    # 금 11:52


class EasternTest(unittest.TestCase):
    def test_summer_and_winter(self):
        self.assertEqual(D.et_to_kst(datetime(2026, 10, 7, 14, 0)), datetime(2026, 10, 8, 3, 0))
        self.assertEqual(D.et_to_kst(datetime(2026, 11, 4, 14, 0)), datetime(2026, 11, 5, 4, 0))
        self.assertTrue(D.us_dst(datetime(2026, 3, 8, 2, 0)))
        self.assertFalse(D.us_dst(datetime(2026, 11, 1, 2, 0)))


class WeekdayTest(unittest.TestCase):
    def test_right_weekdays_pass(self):
        text = "10.05(월) 23:00 발표. 지난 거래일인 10월 2일(금) 종가. 6일(화)에 열리고 9일(금)에 쉰다."
        self.assertEqual(D.weekday_errors(text, MON), [])

    def test_wrong_weekdays_are_caught(self):
        errors = D.weekday_errors("10.05(화) 발표, 10월 8일(수) 새벽, 6일(수) 개장", MON)
        self.assertEqual(len(errors), 3)
        self.assertIn("2026-10-08은 목요일이다", errors[1])

    def test_day_only_reads_the_nearest_month(self):
        self.assertEqual(D.weekday_errors("2일(월)에 발표한다", date(2026, 10, 30)), [])   # 11월 2일
        self.assertEqual(D.weekday_errors("12.31(목) 휴장", date(2027, 1, 4)), [])          # 지난해 연말


class EventTest(unittest.TestCase):
    def test_range_is_today_until_next_morning(self):
        ok = ["10.05(월) 23:00 ISM", "10.06(화) 03:00 의사록", "10.06(화) 새벽 연설", "21:30 날짜 없는 줄"]
        self.assertEqual(D.event_errors(ok, MON), [])
        bad = ["10.06(화) 09:00 개장", "10.06(화) 오전 발표", "10.08(목) 03:00 의사록", "10.02(금) 21:30 고용"]
        self.assertEqual(len(D.event_errors(bad, MON)), 4)


class GateTest(unittest.TestCase):
    def test_wrong_weekday_stops_the_note(self):
        with self.assertRaises(ValueError) as e:
            B.to_note(SAMPLE.replace("한국 10.02(금) 종가", "한국 10.02(목) 종가"))
        self.assertIn("금요일", str(e.exception))

    def test_event_outside_the_day_stops_the_note(self):
        with self.assertRaises(ValueError):
            B.to_note(SAMPLE.replace("- 21:30 미국 실업수당 청구\n어제", "- 10.07(수) 21:30 미국 실업수당 청구\n어제"))

    def test_missing_basis_line_stops_the_note(self):
        with self.assertRaises(ValueError):
            B.to_note(SAMPLE.replace("지표 기준: 한국 10.02(금) 종가 · 미국 10.02(금) 종가\n", ""))


if __name__ == "__main__":
    unittest.main()
