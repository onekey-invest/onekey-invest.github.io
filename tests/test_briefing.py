"""브리핑 → 마켓노트 변환 검증. 실행: python -m unittest discover tests"""
import sys
import unittest
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import briefing as B  # noqa: E402

SAMPLE = """아침 경제·기업 브리핑 — 2026.10.05

[0. 오늘의 한 줄]
금리 하락과 반도체 강세가 겹친 하루.

**[1. 통합 브리핑]**
A. 경제·정책
1. 고용 지표가 예상보다 약했다. [출처: 미 노동부]

C. 주식시장·수급·섹터
# 반도체
장비주가 올랐다. [출처: 한국거래소]

[2. 오늘의 시장 지도]
- US 10Y 4.12% (-3bp) [출처: 미 재무부]

[3. 기업·산업 Watch]
- 예시전자: 투자 계획 상향 [CAPEX]

[4. 오늘 예정 이벤트]
- 21:30 미국 실업수당 청구

[5. 최종 요약]
- 오늘 반드시 알아야 할 것: 고용 둔화
- 오늘 가장 중요한 리스크: 금리 변동
- 오늘 확인할 포인트: 장비 수주

[7. 짧은 노트]
날짜: 2026-10-05
오늘의 한 줄: 금리 하락과 반도체 강세
지표:
- KOSPI | 3,814.80 | +0.4%
- 미 10년물 | 4.12% | -3bp
핵심 3가지:
1. 고용 둔화로 금리 하락
2. 장비주 강세
3. 환율 안정
내 종목·산업: 해당 없음
오늘 일정:
- 21:30 미국 실업수당 청구
어제 확인한 것: 수출 잠정치 → 전년 대비 증가
확인할 것: 장비 수주
내 코멘트: (작성 필요)
(제안) 장비주 수주 가정 점검
태그: 반도체, 금리

[7. 검증 기록]
- 원/달러: 뉴스레터 값이 달라 보도로 확인
"""


class SplitTest(unittest.TestCase):
    def test_numbered_list_is_not_a_section(self):
        sec = B.split_sections(SAMPLE)
        self.assertEqual(sorted(sec), [0, 1, 2, 3, 4, 5, 7, 8])
        self.assertIn("1. 고용 지표", sec[1])
        self.assertIn("1. 고용 둔화", sec[7])


class NoteTest(unittest.TestCase):
    def setUp(self):
        self.day, self.note = B.to_note(SAMPLE)
        _, front, self.body = self.note.split("---", 2)
        self.front = yaml.safe_load(front)

    def test_front(self):
        f = self.front
        self.assertEqual(self.day, date(2026, 10, 5))
        self.assertEqual(f["date"], date(2026, 10, 5))
        self.assertEqual(f["headline"], "금리 하락과 반도체 강세")
        self.assertEqual(f["indicators"][1], {"name": "미 10년물", "value": "4.12%", "change": "-3bp"})
        self.assertEqual(len(f["points"]), 3)
        self.assertEqual(f["points"][0], "고용 둔화로 금리 하락")
        self.assertEqual(f["watch"], [])
        self.assertEqual(f["week"], ["21:30 미국 실업수당 청구"])
        self.assertEqual(f["review"], "수출 잠정치 → 전년 대비 증가")
        self.assertEqual(len(f["summary"]), 3)
        self.assertEqual(f["tags"], ["반도체", "금리"])

    def test_comment_is_left_for_the_author(self):
        self.assertTrue(self.front["draft"])
        self.assertEqual(self.front["comment"], "")
        self.assertEqual(self.front["comment_suggestion"], "장비주 수주 가정 점검")

    def test_body_sections(self):
        heads = [x for x in self.body.splitlines() if x.startswith("## ")]
        self.assertEqual(heads, ["## 통합 브리핑", "## 오늘의 시장 지도", "## 기업·산업 Watch", "## 오늘 예정 이벤트"])
        self.assertIn("### A. 경제·정책", self.body)
        self.assertIn("#### 반도체", self.body)      # 본문 속 큰 제목은 구획을 깨지 않게 낮춘다
        self.assertNotIn("짧은 노트", self.body)

    def test_sources_and_check_log_stay_private(self):
        self.assertNotIn("출처", self.note)
        self.assertNotIn("검증 기록", self.note)
        self.assertEqual(self.front["tags"], ["반도체", "금리"])

    def test_short_note_may_be_section_six(self):
        day, _ = B.to_note(SAMPLE.replace("[7. 짧은 노트]", "[6. 짧은 노트]"))
        self.assertEqual(day, date(2026, 10, 5))

    def test_summary_heading_then_paragraph(self):
        text = SAMPLE.replace("- 오늘 반드시 알아야 할 것: 고용 둔화", "오늘 반드시 알아야 할 것\n\n고용이 둔화됐다.")
        _, note = B.to_note(text)
        front = yaml.safe_load(note.split("---", 2)[1])
        self.assertEqual(front["summary"][0], "오늘 반드시 알아야 할 것: 고용이 둔화됐다.")
        self.assertEqual(len(front["summary"]), 3)

    def test_date_argument_wins(self):
        day, _ = B.to_note(SAMPLE, date(2026, 10, 6))
        self.assertEqual(day, date(2026, 10, 6))


class ErrorTest(unittest.TestCase):
    def test_needs_short_note(self):
        with self.assertRaises(ValueError):
            B.to_note(SAMPLE.split("[7.")[0])

    def test_bad_indicator(self):
        with self.assertRaises(ValueError):
            B.to_note(SAMPLE.replace("KOSPI | 3,814.80 | +0.4%", "KOSPI 3,814.80"))


if __name__ == "__main__":
    unittest.main()
