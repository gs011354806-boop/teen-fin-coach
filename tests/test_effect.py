"""11번 효과 측정 대시보드: 주차별 집계, 앱 활동, 콘텐츠 추가 후보, 화면."""

import pandas as pd
import pytest

from conftest import open_app
from engine import detect, effect, replay, store

DASHBOARD = "pages/9_효과_측정.py"


@pytest.fixture(scope="module")
def base():
    allowance = store.load_allowance()
    return dict(students=store.load_students(), trades=store.load_trades(), prices=store.load_prices(),
                allowance=allowance, weeks=replay.week_starts(allowance))


def test_weekly_patterns_match_detect(base):
    rows = effect.weekly_patterns(base["students"], base["trades"], base["prices"], base["weeks"])
    all_buys = [d for s in base["students"] for d in detect.detect(base["trades"], base["prices"], s)]
    assert sum(r["buys"] for r in rows) == len(all_buys)
    assert sum(r[detect.NO_REASON] for r in rows) == sum(detect.NO_REASON in d["patterns"] for d in all_buys)
    first = rows[0]
    assert first["mistake_pct"] == round(sum(bool(d["patterns"]) for d in all_buys
                                             if d["date"] <= replay.week_end(base["weeks"][0])) / first["buys"] * 100)


def test_weekly_missions_ignore_ungraded():
    missions = pd.DataFrame([{"week_start": "W1", "done": "TRUE"}, {"week_start": "W1", "done": "FALSE"},
                             {"week_start": "W1", "done": ""}, {"week_start": "W2", "done": ""}])
    rows = effect.weekly_missions(missions, ["W1", "W2"])
    assert rows[0] == {"week_start": "W1", "graded": 2, "done_pct": 50}
    assert rows[1]["done_pct"] is None


def test_first_last_needs_two_values():
    assert effect.first_last([{"week_start": "W1", "v": 10}, {"week_start": "W2", "v": None}], "v") is None
    result = effect.first_last([{"week_start": "W1", "v": 40}, {"week_start": "W2", "v": None},
                                {"week_start": "W3", "v": 20}], "v")
    assert (result["first"], result["last"], result["last_week"]) == (40, 20, "W3")


def test_activity_and_missing_concepts(base):
    lessons = pd.DataFrame([{"student_id": "S01"}, {"student_id": "S01"}])
    rules = pd.DataFrame([{"student_id": "S01"}])
    prechecks = pd.DataFrame([{"decision": "CANCEL", "added_reason": ""},
                              {"decision": "BUY", "added_reason": "기사를 읽고 샀어요"}])
    questions = pd.DataFrame([{"question": "세금은 뭐예요?", "concept": "NONE"},
                              {"question": "세금은 뭐예요?", "concept": "NONE"},
                              {"question": "삼성전자 사도 돼요?", "concept": "ADVICE"}])
    unlocks = pd.DataFrame([{"student_id": "S03", "stage": "2", "date": "2026-10-02"}])
    act = effect.activity(lessons, rules, prechecks, questions, unlocks, base["students"])
    assert (act["lessons"], act["lesson_students"], act["rules"]) == (2, 1, 1)
    assert (act["prechecks"], act["precheck_cancel"], act["precheck_added_pct"]) == (2, 1, 50)
    assert (act["questions_none"], act["questions_advice"]) == (2, 1)
    assert act["stages"] == {1: 2, 2: 1, 3: 0}
    assert effect.missing_concepts(questions) == ["세금은 뭐예요?"]


def test_dashboard_renders_without_returns_or_scores():
    at = open_app(DASHBOARD)
    assert not at.exception, at.exception
    labels = [m.label for m in at.metric]
    assert {"근거 없는 매수 비율", "실수 패턴 매수 비율", "미션 달성률", "저축률", "원함 지출 비율"} <= set(labels)
    text = " ".join(m.value for m in at.markdown) + " ".join(labels)
    assert "통계적 효과가 아니라" in text
    assert "수익률(%)" not in text and "점수" not in " ".join(labels)


def test_sidebar_links_to_dashboard():
    at = open_app()
    assert any(link.label.startswith("효과 측정 대시보드") for link in at.sidebar.get("page_link"))


def test_base_data_is_before_demo_today(base):
    from engine import portfolio
    today = portfolio.latest_date(base["prices"])
    assert (base["trades"]["date"] < today).all()  # 기본 4주 기록 = 코칭 전, 앱에서 한 매수만 '오늘'


def test_before_after_separates_app_buys(base):
    from engine import portfolio
    today = portfolio.latest_date(base["prices"])
    extra = pd.DataFrame([["T9001", "S01", today, "005930", "BUY", 1, 56800, "반도체 수요가 는다는 기사를 읽었어요"]],
                         columns=store.TRADE_COLUMNS)
    trades = pd.concat([base["trades"], extra], ignore_index=True)
    result = effect.before_after(base["students"], trades, base["prices"], today)
    assert result["after"]["buys"] == 1 and result["after"]["no_reason_pct"] == 0  # 이유를 적고 산 매수
    assert result["before"]["buys"] == len([d for s in base["students"]
                                            for d in detect.detect(base["trades"], base["prices"], s)])
    weekly = effect.weekly_patterns(base["students"], trades, base["prices"], base["weeks"], until=today)
    assert sum(r["buys"] for r in weekly) == result["before"]["buys"]  # 주차별에는 앱 매수가 섞이지 않는다


def test_latest_value_for_single_week():
    rows = [{"week_start": "W1", "v": None}, {"week_start": "W2", "v": 50}]
    assert effect.first_last(rows, "v") is None
    assert effect.latest_value(rows, "v") == {"week": "W2", "value": 50, "count": 1}
    assert effect.latest_value([{"week_start": "W1", "v": None}], "v") is None


def test_real_price_buys_count_as_app_buys(base):
    """투자 탭(실제 시세)에서 한 매수는 시나리오 날짜와 상관없이 '앱에서 한 매수'로 센다."""
    from engine import portfolio
    today = portfolio.latest_date(base["prices"])
    app_buy = {"trade_id": "R0001", "date": "2026-11-20", "ticker": "005930", "patterns": []}
    result = effect.before_after(base["students"], base["trades"], base["prices"], today, [app_buy])
    assert result["after"]["buys"] == 1 and result["after"]["no_reason_pct"] == 0
    assert result["before"]["buys"] > 0


def test_load_all_trades_keeps_both_records(tmp_path, monkeypatch):
    scen, real = tmp_path / "trades.csv", tmp_path / "real_trades.csv"
    header = ",".join(store.TRADE_COLUMNS) + "\n"
    scen.write_text(header + "T0001,S01,2026-09-08,005930,BUY,5,61500,계속 오를 것 같아서\n", encoding="utf-8")
    real.write_text(header + "R0001,S01,2026-11-20,005930,BUY,1,70000,실적 발표를 확인하고 나눠 사려고\n", encoding="utf-8")
    monkeypatch.setattr(store, "TRADES_PATH", scen)
    monkeypatch.setattr(store, "REAL_TRADES_PATH", real)
    assert list(store.load_all_trades()["trade_id"]) == ["T0001", "R0001"]
