"""17번 성장 회고: 비교 사실·변화 판단은 코드, AI 문장은 숫자 검사."""

import pandas as pd
import pytest

from conftest import open_app
from engine import growth, mission, replay, store
from llm import client

pytestmark = pytest.mark.usefixtures("legacy_mission_tab")  # 예전 미션 탭 (config.MISSION_TAB_V2 = False)

MISSION = "pages/4_이번_주_미션.py"


def metrics(buys=2, no_reason=1, weight=30.0, save=5000):
    return {"buy_count": buys, "no_reason_count": no_reason,
            "no_reason_buy_pct": None if buys == 0 else no_reason / buys * 100,
            "max_weight_pct": weight, "save_net": save}


def test_changes_are_decided_by_code():
    trend = growth.changes(metrics(2, 2, 83, 1000), metrics(2, 0, 70, 3000), 1, 0)
    assert trend == {"나아짐": ["매수 근거 적기", "나눠 담기", "급등 따라 사지 않기", "모으기"],
                     "잘 유지": [], "더 연습": []}


def test_same_ratio_is_not_improvement():
    trend = growth.changes(metrics(2, 2), metrics(1, 1), 0, 0)  # 2번 중 2번 → 1번 중 1번
    assert "매수 근거 적기" in trend["더 연습"]  # 그대로지만 아직 근거가 부족 → 잘 유지가 아님
    assert "매수 근거 적기" in growth.changes(metrics(2, 0), metrics(1, 0), 0, 0)["잘 유지"]


def test_low_weights_count_as_kept_and_no_buy_week_is_skipped():
    trend = growth.changes(metrics(3, 0, 18), metrics(0, 0, 23), 0, 0)
    assert "나눠 담기" in trend["잘 유지"]
    assert "매수 근거 적기" not in sum(trend.values(), [])


def test_minji_facts_have_no_returns():
    students = {s["student_id"]: s for s in store.load_students()}
    trades, allowance, prices = store.load_trades(), store.load_allowance(), store.load_prices()
    weeks = replay.week_starts(allowance)
    facts, trend = growth.behavior_facts(students["S01"], trades, allowance, prices, weeks[0], weeks[-1],
                                         weeks, with_changes=True)
    text = " ".join(facts)
    assert "1주차" in text and "4주차" in text and "수익" not in text
    assert "나눠 담기" in trend["더 연습"]  # 민지: 54% → 83%


def test_numbers_check_blocks_new_numbers():
    check = growth.numbers_check(["1주차 54%, 4주차 83%였어요.", "모으기 1주차 12,000원이었어요."])
    check({"story": "4주차에 83%였어요. 12,000원을 모았어요.", "next": "이어 가 봐요."})
    with pytest.raises(ValueError):
        check({"story": "비중이 29%p 늘었어요.", "next": "이어 가 봐요."})  # 차이를 AI가 계산
    with pytest.raises(ValueError):
        check({"story": "1만 원을 모았어요.", "next": "이어 가 봐요."})


def test_reached_weeks_follow_finished_replays():
    weeks = ["2026-09-07", "2026-09-14", "2026-09-21"]
    coaching = pd.DataFrame({"student_id": ["S01", "S01"], "week_start": ["2026-09-14", "2026-09-21"],
                             "replay_comment": ["잘했어요.", ""]})
    assert growth.reached_weeks(coaching, weeks, "S01") == ["2026-09-07", "2026-09-14"]


@pytest.fixture
def played(tmp_path, monkeypatch):
    """민지가 2주차 Replay까지 마친 상태."""
    coaching = pd.DataFrame([{c: "" for c in store.COACHING_COLUMNS}])
    coaching.loc[0, ["student_id", "week_start", "diag_week_start", "good", "practice", "summary", "plan",
                     "plan_weekly_save", "replay_comment"]] = [
        "S01", "2026-09-14", "2026-09-07", "근거 적기", "한 종목 쏠림", "요약이에요.", "A", "10000", "잘했어요."]
    missions = pd.DataFrame([{c: "" for c in store.MISSION_COLUMNS}])
    missions.loc[0, ["mission_id", "student_id", "week_start", "skill", "text", "target_metric", "target_value",
                     "done", "level"]] = ["M0001", "S01", "2026-09-14", "분산", "미션이에요.", "max_weight_pct",
                                          "70", "TRUE", mission.START_LEVEL]
    for name, table, cols in [("coaching_weeks.csv", coaching, store.COACHING_COLUMNS),
                              ("missions.csv", missions, store.MISSION_COLUMNS)]:
        store._save_table(table, tmp_path / name, cols)
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    monkeypatch.setattr(store, "MISSIONS_PATH", tmp_path / "missions.csv")
    monkeypatch.setattr(store, "LESSONS_PATH", tmp_path / "lessons.csv")
    monkeypatch.setattr(store, "RULES_PATH", tmp_path / "rules.csv")
    calls = []

    def ask(name, payload, default=None, check=None, **kw):
        calls.append(payload)
        result = {"story": "1주차보다 2주차에 꾸준히 연습했어요.", "next": "다음 주에도 나눠 담아 봐요."}
        check(result)
        return result

    monkeypatch.setattr(client, "ask", ask)
    return calls


def test_growth_section_on_mission_page(played):
    at = open_app(MISSION)
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "나의 성장 회고" in text and "미션 1개 중 1개를 해냈어요" in text
    next(b for b in at.button if b.label == "AI 코치와 돌아보기").click()
    at = at.run()
    assert any("꾸준히 연습했어요" in i.value for i in at.info)
    assert any("다음에 이어 갈 것" in s.value for s in at.success)
    assert played[-1]["changes"] and played[-1]["practice_now"] == ["한 종목 쏠림"]


def test_growth_needs_one_finished_week(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    monkeypatch.setattr(store, "MISSIONS_PATH", tmp_path / "missions.csv")
    at = open_app(MISSION)
    assert not at.exception
    assert any("주말 Replay까지 마치면" in m.value for m in at.markdown)
