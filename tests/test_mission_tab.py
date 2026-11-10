"""28번 미션 탭 (소비/투자 미션). 명세 6-2 · 6-4 · 6-5 계산 + 학생별 데이터 + 화면 흐름.
화면 흐름 테스트는 임시 파일(용돈·미션 기록)을 써서 data/를 바꾸지 않는다."""

import shutil

import pandas as pd
import pytest

from conftest import ROOT
from engine import envelope, invest_mission as im, rewards, spend_mission as sm, store

PAGE = "pages/4_이번_주_미션.py"
STUDENTS = {s["student_id"]: s for s in store.load_students()}
ALLOWANCE = store.load_allowance()


# ---------- 6-5 검증 · 포인트 ----------

@pytest.mark.parametrize("direction, baseline, target, current, rate", [
    ("decrease", 4, 3, 2, 1.0),      # 목표보다 더 줄임 → 1
    ("decrease", 3, 1, 2, 0.5),
    ("decrease", 3, 2, 5, 0.0),      # 더 늘어도 0 (벌점 없음)
    ("increase", 1000, 4000, 3250, 0.75),
    ("increase", 0, 1000, 1000, 1.0),
    ("increase", 1000, 1000, 500, 0.0),  # 목표 변화 0: 채웠는지로
])
def test_completion_rate(direction, baseline, target, current, rate):
    assert sm.completion_rate(direction, baseline, target, current) == pytest.approx(rate)


def test_points_rounded_to_10():
    assert sm.points_for(200, 0.76) == 150
    assert sm.points_for(150, 1.0) == 150
    assert sm.points_for(150, 0.0) == 0


# ---------- 6-2 시뮬레이션 · 학생별 데이터 ----------

def test_eta_months():
    assert sm.eta_months(202000, 12000, 0.85) == pytest.approx(0.85 + 202000 / 12000 / 4.345, abs=0.05)
    assert sm.eta_months(1000, 0, 0.5) is None
    assert sm.eta_months(0, 1000, 0.5) == 0.5


def test_junho_saving_streak_is_top_trigger():
    trig = sm.triggers(STUDENTS["S02"], ALLOWANCE)
    assert [t["code"] for t in trig] == ["SAVING_MISS_STREAK", "SPEND_FREQ_HIGH"]
    assert trig[0]["evidence"] == {"weeks": 3, "plan": 9000}
    freq = trig[1]["evidence"]
    assert (freq["category"], freq["count"], freq["amount"]) == ("CONVENIENCE", 4, 17200)


@pytest.mark.parametrize("sid", ["S01", "S03"])
def test_no_trigger_shows_strengths(sid):
    assert sm.triggers(STUDENTS[sid], ALLOWANCE) == []
    assert sm.strengths(STUDENTS[sid], ALLOWANCE)


@pytest.mark.parametrize("sid, recommended", [("S01", "B"), ("S02", "A"), ("S03", "B")])
def test_recommendation_per_student(sid, recommended):
    sim = sm.simulation(STUDENTS[sid], ALLOWANCE)
    assert [o["label"] for o in sim["options"] if o["recommended"]] == [recommended]
    assert sim["deadline"] == STUDENTS[sid]["saving_goal"]["months"]
    assert sim["saved"] == envelope.balances(ALLOWANCE, sid)["SAVE"]


def test_options_follow_formulas():
    sim = sm.simulation(STUDENTS["S02"], ALLOWANCE)
    by = {o["label"]: o for o in sim["options"]}
    net = sim["weekly_net"]
    assert by["B"]["weekly"] == net + sm.EXTRA_SAVE
    assert by["C"]["weekly"] == round(net * 1.2) and by["C"]["parent"]
    assert by["A"]["mission"]["baseline"] == 4  # 지난주 편의점 4번 → 3번 이하
    assert by["A"]["mission"]["target"] == 3


def test_recommend_rule():
    opts = [{"label": "A", "eta": 7.0, "change": 4000, "parent": False},
            {"label": "B", "eta": 5.5, "change": 3000, "parent": False},
            {"label": "C", "eta": 5.0, "change": 1000, "parent": True}]
    assert sm._recommend(opts, 6) == "B"          # 기한 안 + 행동 변화가 가장 작은 안 (부모 도움은 뒤로)
    assert sm._recommend(opts, 4) == "C"          # 기한 안에 드는 안이 없으면 가장 빠른 안


def test_transfer_is_not_spending():
    extra = pd.DataFrame([{"tx_id": "X1", "student_id": "S01", "date": "2026-10-03", "envelope": e,
                           "amount": a, "category": c, "memo": m}
                          for e, a, c, m in envelope.transfer_entries(3000)])
    both = pd.concat([ALLOWANCE, extra], ignore_index=True)
    assert len(envelope.spending(both, "S01")) == len(envelope.spending(ALLOWANCE, "S01"))
    assert envelope.balances(both, "S01")["SAVE"] == envelope.balances(ALLOWANCE, "S01")["SAVE"] + 3000


# ---------- 6-4 투자 (만들어만 둠) ----------

def test_invest_replay_spec_mock():
    days = [f"2026-09-{d:02d}" for d in range(1, 10)]
    prices = {"BIO": list(zip(days, [100, 101, 99, 100.5, 115, 110, 106, 102.3, 102]))}
    orders = pd.DataFrame([{"order_id": "O1", "user_id": "U", "datetime": "2026-09-05 10:00", "symbol": "BIO",
                            "side": "BUY", "qty": 78, "price": 11500, "viewed_info": False, "memo": ""}])
    assert im.fomo_buys(orders, prices)[0]["jump_pct"] == 14
    assert "FOMO_BUY" in im.triggers(orders, prices, cash=1_150_000)
    mine = im.replay_compare(prices, "BIO", "2026-09-05")[0]
    assert mine["mine"] and mine["return_pct"] == -11  # 시안: 급등 직후 전액 매수 -11%


def test_skill_unlock_lv3():
    tiles = {t["key"]: t["met"] for t in im.skill_unlock(5, 6, 78, 2)}
    assert tiles == {"weeks": False, "journal": True, "maxWeight": False, "impulse": False}


# ---------- 화면 흐름 ----------

@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    shutil.copy(store.ALLOWANCE_PATH, tmp_path / "allowance.csv")
    monkeypatch.setattr(store, "ALLOWANCE_PATH", tmp_path / "allowance.csv")
    monkeypatch.setattr(store, "MISSION_RUNS_PATH", tmp_path / "mission_runs.csv")
    monkeypatch.setattr(store, "SPEND_QUIZ_PATH", tmp_path / "spend_quiz.csv")
    return tmp_path


def open_as(student_id, query=None):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15)
    at.session_state["student_id"] = student_id
    at.switch_page(PAGE)
    for k, v in (query or {}).items():
        at.query_params[k] = v
    return at.run()


def text(at):
    return " ".join(m.value for m in at.markdown)


def test_junho_full_spend_cycle(temp_data):
    at = open_as("S02")
    assert not at.exception
    assert "AI Replay" in text(at) and "3주째" in text(at)
    at.button(key="m-to-sim").click().run()
    assert at.title[0].value == "소비 시뮬레이션"
    assert at.button(key="m-start").label == "A안으로 이번 주 미션 시작"   # 추천안이 기본
    at.button(key="m-pick-B").click().run()
    assert at.button(key="m-start").label == "B안으로 이번 주 미션 시작"   # 단일 선택 → CTA 문구가 바뀜
    at.button(key="m-pick-A").click().run()
    at.button(key="m-start").click().run()
    assert not at.exception and at.title[0].value == "미션"
    assert "편의점 주 4회 → 3회로 줄이기" in text(at)
    at.button(key="m-finish").click().run()
    assert not at.exception and at.title[0].value == "미션 결과"
    run = store.load_mission_runs().iloc[0]
    assert run["status"] == "completed" and float(run["completion_rate"]) == 1.0  # 이번 주 편의점 2번
    assert "미션 보상 +150P 적립" in text(at)
    events = rewards.earn_events(STUDENTS["S02"], store.load_trades().iloc[0:0], store.load_missions().iloc[0:0],
                                 store.load_allowance(), mission_runs=store.load_mission_runs())
    assert [e["points"] for e in events if e["kind"] == "미션 결과"] == [150]


def test_minji_save_mission_with_transfer(temp_data):
    at = open_as("S01")
    assert "눈에 띄는 소비 패턴이 없어요" in text(at)
    at.button(key="m-to-sim").click().run()
    at.button(key="m-start").click().run()            # 추천 B: 주당 저축 +3,000원
    assert "주당 저축 +3,000원" in text(at)
    at.number_input(key="m-move").set_value(3000)
    at.button(key="m-move-go").click().run()
    at.button(key="m-finish").click().run()
    run = store.load_mission_runs().iloc[0]
    assert float(run["completion_rate"]) == 1.0 and int(run["points"]) == 200
    assert len(envelope.spending(store.load_allowance(), "S01")) == len(envelope.spending(ALLOWANCE, "S01"))


def test_one_active_mission_per_track(temp_data):
    at = open_as("S03", {"view": "spend_sim"})
    at.button(key="m-start").click().run()
    at.button(key="m-to-sim").click().run()
    assert at.button(key="m-start").disabled


def test_invest_track_is_locked(temp_data):
    at = open_as("S01")
    at.segmented_control(key="mission-track").set_value("invest").run()
    assert not at.exception
    assert any("준비 중" in i.value for i in at.info)
    assert at.button(key="m-to-invest-replay").disabled
    at = open_as("S01", {"view": "invest_replay"})   # 주소로 들어와도 잠김 → 미션 홈
    assert not at.exception and at.title[0].value == "미션"
