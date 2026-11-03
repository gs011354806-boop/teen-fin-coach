"""9번 Skill Unlock: 과정 기준 판정, 단계 기록, 실제 시세 잠금."""

import pandas as pd
import pytest

from conftest import open_app
from engine import store, unlock

MARKET = "pages/1_가상_주식시장.py"
UNLOCK = "pages/8_실전_준비_단계.py"


@pytest.fixture(scope="module")
def data():
    return dict(trades=store.load_trades(), prices=store.load_prices(),
                real_trades=pd.DataFrame(columns=store.TRADE_COLUMNS),
                lessons=pd.DataFrame(columns=store.LESSON_COLUMNS),
                rules=pd.DataFrame(columns=store.RULE_COLUMNS),
                missions=pd.DataFrame(columns=store.MISSION_COLUMNS))


def student(sid):
    return next(s for s in store.load_students() if s["student_id"] == sid)


def test_balanced_student_can_open_stage_2_but_concentrated_cannot(data):
    seoyeon = unlock.conditions(student("S03"), **data)
    minji = unlock.conditions(student("S01"), **data)
    assert all(c["met"] for c in seoyeon[2]) and unlock.can_open(1, 2, seoyeon)
    assert not any(c["met"] for c in minji[2])
    assert minji[2][1]["fact"] == "지금 가장 큰 종목 비중은 83%예요."


def test_review_needs_lesson_and_rule_when_there_are_mistakes(data):
    lessons = pd.DataFrame([{"student_id": "S01", "trade_id": "T0014"}])
    rules = pd.DataFrame([{"student_id": "S01", "rule": "한 종목은 절반까지만"}])
    conds = unlock.conditions(student("S01"), **{**data, "lessons": lessons, "rules": rules})
    assert conds[2][2]["met"] and conds[2][2]["fact"] == "돌아본 매수 1개, 나만의 규칙 1개예요."


def test_quick_sell_is_counted_by_last_buy_of_same_ticker():
    trades = pd.DataFrame([
        ["S01", "2026-09-01", "A", "BUY"], ["S01", "2026-09-03", "A", "SELL"],   # 2일 → 급하게 판 것
        ["S01", "2026-09-01", "B", "BUY"], ["S01", "2026-09-10", "B", "SELL"],   # 9일 → 괜찮음
        ["S02", "2026-09-02", "A", "SELL"]], columns=["student_id", "date", "ticker", "side"])
    assert unlock.quick_sells(trades, "S01") == (2, 1)
    cond = unlock.hold_condition([trades], "S01")
    assert not cond["met"] and cond["fact"] == "판 2번 중 5일 안에 판 건 1번이에요."


def test_stage_3_needs_missions_hold_and_real_practice(data):
    missions = pd.DataFrame([{"student_id": "S03", "week_start": w, "done": "TRUE"}
                             for w in ("2026-09-14", "2026-09-21")])
    real = pd.DataFrame([["R0001", "S03", "2026-10-05", "005930", "BUY", 1, 60000, "실적 발표 기사를 읽고 한 주"]],
                        columns=store.TRADE_COLUMNS)
    conds = unlock.conditions(student("S03"), **{**data, "missions": missions, "real_trades": real})
    assert all(c["met"] for c in conds[3])
    assert unlock.can_open(2, 3, conds) and not unlock.can_open(1, 3, conds)  # 단계는 차례대로


def test_conditions_never_use_returns(data):
    text = " ".join(c["title"] + c["fact"] for cs in unlock.conditions(student("S01"), **data).values() for c in cs)
    assert not any(word in text for word in ["수익", "이익", "손실", "점수"])


def test_stage_comes_from_records(tmp_path):
    path = tmp_path / "unlocks.csv"
    assert unlock.stage(store.load_unlocks(path), "S01") == 1
    store.append_unlock("S01", 2, "2026-10-02", path)
    store.append_unlock("S03", 3, "2026-10-02", path)
    assert unlock.stage(store.load_unlocks(path), "S01") == 2


# --- 화면 ---

@pytest.fixture
def unlocks(tmp_path, monkeypatch):
    path = tmp_path / "unlocks.csv"
    path.write_text("student_id,stage,date\n", encoding="utf-8")
    monkeypatch.setattr(store, "UNLOCKS_PATH", path)
    return path


def open_as(page, sid, demo=False, real=False):
    at = open_app(page)
    at.session_state["student_id"] = sid
    at.session_state["demo_mode"] = demo
    if real:
        at.session_state["price_mode"] = "real"
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_real_mode_is_locked_until_stage_2(unlocks):
    at = open_as(MARKET, "S01", real=True)
    assert at.radio[0].disabled  # 시세 종류 잠김
    assert "실제 시세는 2단계에서 열려요" in " ".join(m.value for m in at.markdown)
    assert at.main.selectbox[0].options[0] == "삼성전자 (005930)"  # 실제 시세를 골라 두었어도 시나리오


def test_demo_mode_opens_real_mode_without_unlock(unlocks):
    at = open_as(MARKET, "S01", demo=True)
    assert not at.radio[0].disabled


def test_open_stage_2_records_and_unlocks_market(unlocks):
    at = open_as(UNLOCK, "S03")
    next(b for b in at.button if b.label == "2단계 열기").click()
    at = at.run()
    assert any("2단계를 열었어요" in s.value for s in at.success)
    assert unlock.stage(store.load_unlocks(unlocks), "S03") == 2
    assert not open_as(MARKET, "S03").radio[0].disabled


def test_unlock_page_shows_no_button_when_conditions_missing(unlocks):
    at = open_as(UNLOCK, "S01")
    assert not [b for b in at.button if b.label == "2단계 열기"]
    text = " ".join(m.value for m in at.markdown)
    assert "⬜" in text and "2단계를 먼저 열면" in text


def test_parent_report_shows_stage(unlocks):
    unlocks.write_text("student_id,stage,date\nS01,3,2026-10-02\n", encoding="utf-8")
    at = open_as("pages/6_부모_리포트.py", "S01")
    assert any("실전 소수점 투자 신청을 보냈어요" in i.value for i in at.info)
