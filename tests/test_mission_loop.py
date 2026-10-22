"""6번 AI 행동 미션 루프: 엔진 단위 검증 + 화면에서 한 사이클 (LLM은 가짜)."""

from pathlib import Path

import pandas as pd
import pytest
from conftest import open_app

from engine import mission, replay, simulate, store
from llm import client

ROOT = Path(__file__).resolve().parent.parent
PAGE = "pages/4_이번_주_미션.py"


def metrics(**overrides):
    base = {"week_start": "2026-09-07", "buy_count": 2, "no_reason_count": 0,
            "no_reason_buy_pct": 0.0, "max_weight_pct": 20.0, "save_deposit": 6000,
            "save_withdraw": 0, "withdraw_count": 0, "save_net": 6000, "save_balance": 6000}
    return {**base, **overrides}


# --- engine/replay.py ---

def test_week_starts_are_mondays():
    allowance = pd.DataFrame({"date": ["2026-09-08", "2026-09-20", "2026-09-21"]})
    assert replay.week_starts(allowance) == ["2026-09-07", "2026-09-14", "2026-09-21"]
    assert replay.week_end("2026-09-07") == "2026-09-13"
    assert replay.week_label("2026-09-14", ["2026-09-07", "2026-09-14"]) == "2주차 (9/14~9/20)"


def test_week_metrics_on_sample_week():
    students = {s["student_id"]: s for s in store.load_students()}
    m = replay.week_metrics(students["S01"], store.load_trades(), store.load_allowance(),
                            store.load_prices(), "2026-09-07")
    assert (m["buy_count"], m["no_reason_count"]) == (2, 2)  # 빈 일지, 8자 일지
    assert m["no_reason_buy_pct"] == 100
    assert 50 < m["max_weight_pct"] < 60
    assert (m["save_deposit"], m["save_withdraw"], m["save_net"]) == (12000, 0, 12000)


@pytest.mark.parametrize("metric, target, value, done", [
    ("max_weight_pct", 50.0, 45.0, True), ("max_weight_pct", 50.0, 51.0, False),
    ("no_reason_buy_pct", 25.0, 0.0, True), ("no_reason_buy_pct", 25.0, 50.0, False),
    ("save_net", 6000.0, 6000.0, True), ("save_net", 6000.0, 5000.0, False),
])
def test_is_done(metric, target, value, done):
    assert replay.is_done(metric, target, value) is done


def test_no_buys_counts_as_no_unreasoned_buys():
    m = metrics(buy_count=0, no_reason_buy_pct=None)
    assert replay.mission_result("no_reason_buy_pct", m) == 0.0
    assert "매수가 없었어요" in replay.result_sentence("no_reason_buy_pct", m)


# --- engine/simulate.py ---

def test_weeks_needed_and_finish_date():
    assert simulate.weeks_needed(25000, 6000) == 5
    assert simulate.weeks_needed(0, 6000) == 0
    assert simulate.weeks_needed(25000, 0) is None
    assert simulate.finish_date("2026-09-14", 2) == "2026-09-27"
    assert simulate.finish_date("2026-09-14", None) is None


def test_alternatives():
    student = {"weekly_allowance": 20000, "saving_goal": {"amount": 250000},
               "envelope_ratio": {"SPEND": 50, "SAVE": 30, "INVEST": 20}}
    options = {o["key"]: o for o in simulate.alternatives(student, 10000, [6000, 3000],
                                                          "2026-09-14")}
    assert [options[k]["weekly"] for k in "ABC"] == [4500, 6000, 8000]
    assert options["B"]["remaining"] == 240000
    assert options["B"]["weeks"] == 40
    assert options["C"]["weeks"] == 30


def test_alternative_c_never_takes_more_than_spend():
    student = {"weekly_allowance": 10000, "saving_goal": {"amount": 50000},
               "envelope_ratio": {"SPEND": 5, "SAVE": 90, "INVEST": 5}}
    c = simulate.alternatives(student, 0, [], "2026-09-14")[2]
    assert c["weekly"] == 9500 and "5%p" in c["label"]


# --- engine/mission.py ---

def test_candidates_practice_and_good():
    c = mission.candidates(metrics(no_reason_buy_pct=100.0, max_weight_pct=72.0))
    assert c["good"] == ["꾸준히 모으기"]
    assert c["practice"] == ["근거 없는 매수", "한 종목 쏠림"]  # 더 필요한 것이 앞


def test_candidates_when_everything_is_good_do_not_invent_problems():
    c = mission.candidates(metrics())
    assert "모으기 봉투 꺼내 쓰기" not in c["practice"]
    assert len(c["practice"]) == 1 and c["practice"][0].endswith(("이어가기", "늘리기", "적기"))
    assert c["good"]


def test_candidates_always_have_good():
    c = mission.candidates(metrics(no_reason_buy_pct=100.0, max_weight_pct=80.0,
                                   save_net=0, save_withdraw=6000))
    assert c["good"] == [mission.FALLBACK_GOOD]


def test_skill_of_every_keyword():
    for skill, d in mission.SKILLS.items():
        for key in ("good", "practice", "stretch"):
            assert mission.skill_of(d[key]) == skill


@pytest.mark.parametrize("level, target", [("쉬움", 65), ("보통", 60), ("어려움", 50)])
def test_weight_goal_by_level(level, target):
    goal = mission.behavior_goal("위험분산", level, metrics(max_weight_pct=72.0))
    assert goal["target_value"] == target and f"{target}%" in goal["phrase"]


def test_weight_goal_has_floor():
    assert mission.behavior_goal("위험분산", "어려움", metrics(max_weight_pct=45.0))[
        "target_value"] == mission.WEIGHT_FLOOR


def test_saving_goal_phrase():
    goal = mission.saving_goal(6000)
    assert goal["must_include"] == ["6,000원"] and "6,000원" in goal["phrase"]


def test_next_level():
    assert mission.next_level("보통", True) == "어려움"
    assert mission.next_level("어려움", True) == "어려움"
    assert mission.next_level("보통", False) == "쉬움"
    assert mission.next_level("쉬움", False) == "쉬움"


def test_recommended_plan():
    options = [{"key": "A", "weekly": 500}, {"key": "B", "weekly": 4500},
               {"key": "C", "weekly": 6000}]
    assert mission.recommended_plan(options, None) == "B"
    assert mission.recommended_plan(options, True) == "C"
    assert mission.recommended_plan(options, False) == "A"
    assert mission.recommended_plan([{"key": "A", "weekly": 0}], None) is None


# --- llm/client.py 목록 키와 check ---

def test_list_keys_and_check():
    import json
    calls = []

    def gen(prompt):
        calls.append(prompt)
        return json.dumps([
            {"good": ["없는 키워드"], "practice": ["근거 없는 매수"], "summary": "s"},
            {"good": ["꾸준히 모으기"], "practice": ["근거 없는 매수"], "summary": "잘했어요."},
        ][len(calls) - 1])

    def check(result):
        if not set(result["good"]) <= {"꾸준히 모으기"}:
            raise ValueError("후보 밖")

    result = client.ask("diagnose_week", {}, check=check, generate=gen)
    assert result == {"summary": "잘했어요.", "good": ["꾸준히 모으기"],
                      "practice": ["근거 없는 매수"]}
    assert len(calls) == 2


# --- 화면 한 사이클 ---

@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MISSIONS_PATH", tmp_path / "missions.csv")
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    monkeypatch.setattr(client, "ask",
                        lambda name, payload, default=None, check=None: dict(default))
    return open_app(PAGE)


def click(at, prefix):
    next(b for b in at.button if b.label.startswith(prefix)).click()
    at = at.run()
    assert not at.exception, at.exception
    return at


def reopen():
    """앱을 새로 연 것처럼 빈 세션으로 다시 연다. 진행 상태는 파일에서만 이어진다.
    (streamlit 1.32 AppTest는 st.rerun으로 화면 단계가 바뀐 뒤 사라진 위젯 상태를 찾다가 실패한다)"""
    at = open_app(PAGE)
    assert not at.exception, at.exception
    return at


def test_one_full_cycle_for_concentrated_student(page):
    at = page
    assert not at.exception
    at = click(at, "1주차 (9/7~9/13) 기록으로 진단 받기")
    at = click(at, "미션 받기")
    at = click(at, "이 계획으로 이번 주 시작")

    missions = store.load_missions()
    assert list(missions["week_start"]) == ["2026-09-14", "2026-09-14"]
    assert list(missions["skill"]) == ["근거 적기", "목표저축"]
    assert list(missions["level"]) == ["보통", ""]
    assert store.load_coaching().iloc[0]["diag_week_start"] == "2026-09-07"

    at = click(reopen(), "2주차 (9/14~9/20) 주말 Replay")
    missions = store.load_missions()
    assert list(missions["done"]) == ["FALSE", "TRUE"]  # 2주차도 근거 없는 매수, 모으기는 6,000원
    coaching = store.load_coaching()
    assert coaching.iloc[0]["replay_comment"]
    assert any("미션 2개 중" in m.value for m in at.markdown)

    # 재조정: 3주차 미션은 2주차 기록으로 진단하고, 못 한 미션은 한 단계 쉽게
    at = click(reopen(), "2주차 (9/14~9/20) 기록으로 진단 받기")
    at = click(at, "미션 받기")
    at = click(at, "이 계획으로 이번 주 시작")
    third = store.load_missions().query("week_start == '2026-09-21'")
    assert third.iloc[0]["level"] == "쉬움"
    assert len(store.load_coaching()) == 2


def test_reset_clears_only_this_student(page):
    at = click(page, "1주차 (9/7~9/13) 기록으로 진단 받기")
    at = click(at, "미션 받기")
    at = click(at, "이 계획으로 이번 주 시작")
    at = click(reopen(), "미션 기록 처음부터 다시")
    assert len(store.load_missions()) == 0 and len(store.load_coaching()) == 0
    assert any(b.label.startswith("1주차") for b in reopen().button)


# --- 19번 지출 코칭 (원함 지출) ---

def spend_metrics(total, impulse, count=3):
    return metrics(spend_total=total, impulse_spend=impulse, impulse_count=count,
                   impulse_share_pct=None if total == 0 else impulse / total * 100)


def test_spending_practice_when_most_spending_is_wants():
    c = mission.candidates(spend_metrics(28600, 25100))  # 준호 3주차: 88%
    assert c["practice"][0] == "편의점·카페 지출"
    assert mission.skill_of("편의점·카페 지출") == mission.SPENDING
    assert mission.concept_for("편의점·카페 지출") == "NEEDS_VS_WANTS"


def test_spending_is_not_judged_on_small_weeks():
    c = mission.candidates(spend_metrics(2000, 0))
    assert "필요한 곳에 쓰기" not in c["good"]


@pytest.mark.parametrize("level, target", [("쉬움", 22000), ("보통", 20000), ("어려움", 17000)])
def test_spending_goal_by_level(level, target):
    goal = mission.behavior_goal(mission.SPENDING, level, spend_metrics(28600, 25100))
    assert goal["target_value"] == target and goal["must_include"] == [f"{target:,}원"]
    assert goal["target_metric"] == "impulse_spend"


def test_spending_result_and_done():
    m = spend_metrics(20000, 9600, count=2)
    assert replay.is_done("impulse_spend", 14000.0, replay.mission_result("impulse_spend", m))
    assert replay.result_sentence("impulse_spend", m) == "편의점·카페·디저트에 2번, 9,600원을 썼어요."
    assert "편의점·카페·디저트가 2번, 9,600원(48%)" in mission.fact_sentences(m)[-1]


def test_week_metrics_have_spending():
    students = {s["student_id"]: s for s in store.load_students()}
    m = replay.week_metrics(students["S02"], store.load_trades(), store.load_allowance(),
                            store.load_prices(), "2026-09-21")
    assert m["impulse_spend"] <= m["spend_total"] and m["impulse_count"] >= 1


def test_week3_diagnosis_leads_to_spending_mission(page):
    """민지 3주차: 편의점·카페·디저트가 지출의 90% → 4주차 행동 미션은 원함 지출 줄이기."""
    at = page
    for diag in ["1주차", "2주차", "3주차"]:
        at = click(reopen(), f"{diag} (")  # 진단 받기
        at = click(at, "미션 받기")
        at = click(at, "이 계획으로 이번 주 시작")
        if diag != "3주차":
            at = click(reopen(), f"{int(diag[0]) + 1}주차 (")  # 주말 Replay
    fourth = store.load_missions().query("week_start == '2026-09-28'")
    behavior = fourth.iloc[0]
    assert behavior["skill"] == mission.SPENDING and behavior["target_metric"] == "impulse_spend"
    assert f"{int(float(behavior['target_value'])):,}원" in behavior["text"]  # 목표 숫자는 코드가 정한 그대로

    at = click(reopen(), "4주차 (")  # 4주차 Replay: 편의점·카페 5,800원
    done = store.load_missions().query("week_start == '2026-09-28'").iloc[0]["done"]
    assert done == "TRUE"
    assert any("편의점·카페·디저트에 1번, 5,800원을 썼어요." in m.value for m in at.markdown)
