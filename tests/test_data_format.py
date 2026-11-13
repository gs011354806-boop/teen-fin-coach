"""data/ 아래 파일이 docs/DATA.md 형식을 지키는지 검증한다."""

import importlib.util
import json
import re
from pathlib import Path

import pandas as pd
import pytest

from engine import portfolio, store

ROOT = Path(__file__).resolve().parent.parent
STUDENTS_DIR = ROOT / "data" / "students"
PRICES_DIR = ROOT / "data" / "prices"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PERIOD_START, PERIOD_END = "2026-09-07", "2026-10-04"
TYPES = {"몰빵형", "저축 실패형", "균형형"}
SIDES = {"BUY", "SELL"}
ENVELOPES = {"SPEND", "SAVE", "INVEST"}
CATEGORIES = {"CONVENIENCE", "CAFE_DESSERT", "MEAL", "MART", "SHOPPING", "TRANSPORT", "OTHER"}
CONCENTRATION_PCT = 60


def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def is_int(text):
    return re.fullmatch(r"-?\d+", text) is not None


@pytest.fixture(scope="module")
def students():
    return json.loads((STUDENTS_DIR / "students.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def trades():
    return read_csv(STUDENTS_DIR / "trades.csv")


@pytest.fixture(scope="module")
def allowance():
    return read_csv(STUDENTS_DIR / "allowance.csv")


@pytest.fixture(scope="module")
def prices():
    return {p.stem: read_csv(p) for p in sorted(PRICES_DIR.glob("*.csv"))}


def assert_dates_in_period(dates):
    assert all(DATE_RE.match(d) for d in dates)
    assert dates.min() >= PERIOD_START and dates.max() <= PERIOD_END


def test_students_format(students):
    assert len(students) == 3
    assert {s["type"] for s in students} == TYPES
    assert len({s["student_id"] for s in students}) == 3
    for s in students:
        assert set(s) == {"student_id", "name", "grade", "type", "gender", "weekly_allowance",
                          "virtual_cash", "envelope_ratio", "saving_goal"}
        assert s["gender"] in (1, 2)  # BC 통계 성별 코드 (1 남, 2 여)
        assert set(s["envelope_ratio"]) == ENVELOPES
        assert all(isinstance(v, int) and v >= 0 for v in s["envelope_ratio"].values())
        assert sum(s["envelope_ratio"].values()) == 100
        assert isinstance(s["weekly_allowance"], int) and s["weekly_allowance"] > 0
        assert isinstance(s["virtual_cash"], int) and s["virtual_cash"] > 0
        assert set(s["saving_goal"]) == {"item", "amount", "months"}  # months: 목표 기한(개월, 미션 탭 시뮬레이션)
        assert isinstance(s["saving_goal"]["months"], int) and s["saving_goal"]["months"] > 0
        assert isinstance(s["saving_goal"]["amount"], int) and s["saving_goal"]["amount"] > 0


def test_prices_format(prices):
    assert len(prices) >= 3
    for ticker, df in prices.items():
        assert re.fullmatch(r"\d{6}", ticker)
        assert list(df.columns) == ["date", "close"]
        assert_dates_in_period(df["date"])
        assert df["date"].is_monotonic_increasing and df["date"].is_unique
        assert df["date"].nunique() == 20  # 4주 × 평일 5일
        assert all(is_int(c) and int(c) > 0 for c in df["close"])


def test_trades_format(trades, students, prices):
    assert list(trades.columns) == ["trade_id", "student_id", "date", "ticker", "side",
                                    "qty", "price", "journal"]
    assert trades["trade_id"].is_unique
    assert all(re.fullmatch(r"T\d{4}", t) for t in trades["trade_id"])
    assert set(trades["student_id"]) == {s["student_id"] for s in students}
    assert_dates_in_period(trades["date"])
    assert set(trades["ticker"]) <= set(prices)
    assert set(trades["side"]) <= SIDES
    assert all(is_int(q) and int(q) > 0 for q in trades["qty"])
    assert all(is_int(p) and int(p) > 0 for p in trades["price"])


def test_trade_price_matches_close(trades, prices):
    for t in trades.itertuples():
        df = prices[t.ticker]
        close = df.loc[df["date"] == t.date, "close"]
        assert len(close) == 1, f"{t.trade_id}: {t.date}는 거래일이 아님"
        assert int(close.iloc[0]) == int(t.price)


def test_no_oversell_and_no_negative_cash(trades, students):
    for s in students:
        cash = s["virtual_cash"]
        holdings = {}
        for t in trades[trades["student_id"] == s["student_id"]].itertuples():
            sign = 1 if t.side == "BUY" else -1
            holdings[t.ticker] = holdings.get(t.ticker, 0) + sign * int(t.qty)
            cash -= sign * int(t.qty) * int(t.price)
            assert holdings[t.ticker] >= 0, f"{t.trade_id}: 보유 수량보다 많이 팖"
            assert cash >= 0, f"{t.trade_id}: 가상 투자금 부족"


def test_sample_data_only_concentrated_student_exceeds_threshold(tmp_path):
    """새로 만든 샘플 데이터에서는 4주차 마지막 거래일 기준 몰빵형만 비중 기준을 넘는다.

    화면에서 거래를 추가해도 깨지지 않도록 data/가 아니라 새로 생성한 사본으로 본다.
    """
    spec = importlib.util.spec_from_file_location("make_sample_data",
                                                  ROOT / "data" / "make_sample_data.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.main(tmp_path)

    students = store.load_students(tmp_path / "students" / "students.json")
    trades = store.load_trades(tmp_path / "students" / "trades.csv")
    prices = store.load_prices(tmp_path / "prices")
    closes = portfolio.close_on(prices, portfolio.latest_date(prices))
    for s in students:
        held = portfolio.holdings(trades, s["student_id"])
        cash = portfolio.cash_balance(s["virtual_cash"], trades, s["student_id"])
        values = [r["value"] for r in portfolio.position_rows(held, cash, closes)]
        of_holdings = max(values) / sum(values) * 100
        of_total = max(values) / (sum(values) + cash) * 100
        if s["type"] == "몰빵형":
            assert min(of_holdings, of_total) >= CONCENTRATION_PCT
        else:
            assert max(of_holdings, of_total) < CONCENTRATION_PCT


def test_tickers_format(prices):
    tickers = json.loads((PRICES_DIR / "tickers.json").read_text(encoding="utf-8"))
    assert all(set(t) == {"ticker", "name"} and t["name"] for t in tickers)
    assert {t["ticker"] for t in tickers} == set(prices)


def test_allowance_format(allowance, students):
    assert list(allowance.columns) == ["tx_id", "student_id", "date", "envelope",
                                       "amount", "category", "memo"]
    assert allowance["tx_id"].is_unique
    assert all(re.fullmatch(r"A\d{4}", t) for t in allowance["tx_id"])
    assert set(allowance["student_id"]) == {s["student_id"] for s in students}
    assert_dates_in_period(allowance["date"])
    assert set(allowance["envelope"]) <= ENVELOPES
    assert set(allowance["category"]) <= CATEGORIES
    assert all(is_int(a) and int(a) != 0 for a in allowance["amount"])
    assert all(m != "" for m in allowance["memo"])


def test_allowance_covers_four_weeks(allowance, students):
    deposits = allowance[allowance["memo"] == "용돈 입금"]
    for s in students:
        mine = deposits[deposits["student_id"] == s["student_id"]]
        assert mine["date"].nunique() >= 4
        # 화면에서 같은 날 여러 번 입금할 수 있으므로 주간 용돈의 배수인지 본다.
        weekly = mine.groupby("date")["amount"].apply(lambda a: sum(int(x) for x in a))
        assert all(total % s["weekly_allowance"] == 0 for total in weekly)


def test_envelope_balance_never_negative(allowance):
    balance = {}
    for tx in allowance.itertuples():
        key = (tx.student_id, tx.envelope)
        balance[key] = balance.get(key, 0) + int(tx.amount)
        assert balance[key] >= 0, f"{tx.tx_id}: {key} 봉투 잔액이 음수"


def test_lessons_format(students, trades):
    lessons = read_csv(STUDENTS_DIR / "lessons.csv")
    assert list(lessons.columns) == store.LESSON_COLUMNS
    assert lessons["lesson_id"].is_unique
    assert set(lessons["student_id"]) <= {s["student_id"] for s in students}
    assert set(lessons["trade_id"]) <= set(trades["trade_id"])
    assert set(lessons["error_type"]) <= {"FOMO", "과신", "근거 부족", "해당 없음"}
    assert set(lessons["concept"]) <= set(store.load_concepts())


def test_real_trades_format(students):
    """실제 시세 모드의 가상 거래: 시나리오 거래와 같은 컬럼, trade_id는 R로 시작."""
    real = read_csv(STUDENTS_DIR / "real_trades.csv")
    assert list(real.columns) == store.TRADE_COLUMNS
    assert all(re.fullmatch(r"R\d{4}", t) for t in real["trade_id"])
    assert set(real["student_id"]) <= {s["student_id"] for s in students}
    assert set(real["side"]) <= SIDES


def test_point_spend_format(students):
    spends = store.load_spends()
    assert list(spends.columns) == store.SPEND_COLUMNS
    assert spends["spend_id"].is_unique
    assert set(spends["student_id"]) <= {s["student_id"] for s in students}
    assert set(spends["kind"]) <= {"FEED", "COUPON"}
    assert all(is_int(p) and int(p) > 0 for p in spends["points"])


def test_missions_format(students):
    missions = store.load_missions()
    assert list(missions.columns) == store.MISSION_COLUMNS
    assert missions["mission_id"].is_unique
    assert set(missions["skill"]) <= {"위험분산", "근거 적기", "목표저축"}
    assert set(missions["target_metric"]) <= {"max_weight_pct", "no_reason_buy_pct", "save_net"}
    assert set(missions["level"]) <= {"쉬움", "보통", "어려움", ""}
    assert set(missions["student_id"]) <= {s["student_id"] for s in students}
    assert set(missions["done"]) <= {"TRUE", "FALSE", ""}
