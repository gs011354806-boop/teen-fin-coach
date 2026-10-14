"""8번 부모 리포트 검증: 계산 + 보여 주지 말아야 할 것이 정말 안 보이는지."""

from pathlib import Path

import pandas as pd
import pytest
from conftest import open_app

from engine import parent, store
from llm import client

ROOT = Path(__file__).resolve().parent.parent
PAGE = "pages/6_부모_리포트.py"
WEEKS = ["2026-09-07", "2026-09-14"]


def allowance(rows):
    return pd.DataFrame(rows, columns=["student_id", "date", "envelope", "amount", "memo"])


def test_weekly_saving_rates():
    rows = [("S01", "2026-09-07", "SPEND", 10000, "용돈 입금"),
            ("S01", "2026-09-07", "SAVE", 6000, "용돈 입금"),
            ("S01", "2026-09-07", "INVEST", 4000, "용돈 입금"),
            ("S01", "2026-09-10", "SAVE", -3000, "모으기에서 꺼냄"),
            ("S01", "2026-09-10", "SPEND", 3000, "모으기에서 옮김"),
            ("S01", "2026-09-11", "SPEND", -2000, "편의점")]
    rates = parent.weekly_saving_rates("S01", allowance(rows), WEEKS)
    assert rates == [{"week_start": "2026-09-07", "rate": 15},  # (6000-3000)/20000
                     {"week_start": "2026-09-14", "rate": None}]


def test_weekly_mission_rates_ignore_unfinished():
    missions = pd.DataFrame([("S01", "2026-09-07", "TRUE"), ("S01", "2026-09-07", "FALSE"),
                             ("S01", "2026-09-14", ""), ("S02", "2026-09-14", "TRUE")],
                            columns=["student_id", "week_start", "done"])
    rates = parent.weekly_mission_rates("S01", missions, WEEKS)
    assert [r["rate"] for r in rates] == [50, None]


def test_change():
    rates = [{"week_start": "a", "rate": None}, {"week_start": "b", "rate": 10},
             {"week_start": "c", "rate": 40}]
    assert parent.change(rates) == {"first_week": "b", "first": 10, "last_week": "c",
                                    "last": 40, "diff": 30}
    assert parent.change([{"week_start": "a", "rate": None}]) is None


def coaching(*practices):
    return pd.DataFrame([("S01", f"2026-09-{14 + 7 * i}", p) for i, p in enumerate(practices)],
                        columns=["student_id", "week_start", "practice"])


def lessons(*error_types):
    return pd.DataFrame([("S01", "2026-10-02", e) for e in error_types],
                        columns=["student_id", "date", "error_type"])


def test_parent_focus_counts_both_sources():
    focus = parent.parent_focus("S01", coaching("근거 없는 매수|한 종목 쏠림", "한 종목 쏠림"),
                                lessons("근거 부족", "근거 부족"))
    assert focus == "근거 부족"  # 근거 없는 매수(6번) + 근거 부족(5번) x2 = 3 > 쏠림 2


def test_parent_focus_tie_prefers_recent_and_ignores_unknown():
    assert parent.parent_focus("S01", coaching("한 종목 쏠림", "모으기 봉투 꺼내 쓰기"),
                               lessons("해당 없음")) == "모으기 봉투 꺼내 쓰기"
    assert parent.parent_focus("S01", coaching("나눠 담기 이어가기"), lessons()) is None
    assert parent.parent_mission(None) == parent.DEFAULT_PARENT_MISSION


def test_every_practice_keyword_has_a_parent_mission_or_default():
    from engine import mission
    for d in mission.SKILLS.values():
        keyword = parent.FOCUS_ALIASES.get(d["practice"], d["practice"])
        assert keyword in parent.PARENT_MISSIONS


def test_payload_has_no_raw_text():
    payload = parent.mission_payload({"name": "민지", "grade": "중2", "type": "몰빵형"},
                                     "미션", None, None)
    assert set(payload) == {"child", "base_mission", "saving_rate_change", "mission_rate_change"}
    assert set(payload["child"]) == {"name", "grade"}  # 성향 유형도 넘기지 않는다


# --- 화면: 원문과 내부 점수가 보이지 않는지 ---

SECRET_ANSWER = "비밀답변문장_부모에게보이면안됨"


@pytest.fixture
def page(tmp_path, monkeypatch):
    path = tmp_path / "lessons.csv"
    store.append_lesson({"student_id": "S01", "trade_id": "T0014", "date": "2026-10-02",
                         "patterns": ["몰빵"], "question": "q", "answer": SECRET_ANSWER,
                         "error_type": "과신", "reason": "r", "concept": "OVERCONFIDENCE",
                         "explanation": "e", "next_try": "n"}, path=path)
    monkeypatch.setattr(store, "LESSONS_PATH", path)
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    monkeypatch.setattr(client, "ask", lambda name, payload, default=None, check=None: dict(default))
    at = open_app(PAGE)
    assert not at.exception, at.exception
    return at


def page_text(at):
    parts = [m.value for m in at.markdown] + [m.value for m in at.success]
    parts += [str(m.value) for m in at.metric] + [m.label for m in at.metric]
    parts += [c.value for c in at.caption] + [t.value for t in at.title]
    return " ".join(parts)


def test_page_hides_journals_answers_and_scores(page):
    text = page_text(page)
    assert SECRET_ANSWER not in text
    journals = [j for j in store.load_trades()["journal"] if len(j) >= 5]
    assert journals and not any(j in text for j in journals)
    assert "몰빵형" not in text and "난이도" not in text and "포인트" not in text
    assert "저축률" in text and "미션 수행률" in text


def test_page_parent_mission_from_lesson_focus(page):
    assert parent.PARENT_MISSIONS["과신"] in page_text(page)
    page.button[0].click().run()
    assert not page.exception
    assert any(parent.PARENT_MISSIONS["과신"] in s.value for s in page.success)
