"""engine/portfolio.py, engine/store.py 검증."""

import shutil

import pandas as pd
import pytest

from engine import portfolio, store


def make_trades(rows):
    return pd.DataFrame(rows, columns=["student_id", "ticker", "side", "qty", "price"])


TRADES = make_trades([
    ("S01", "005930", "BUY", 5, 60000),
    ("S01", "035720", "BUY", 2, 40000),
    ("S01", "035720", "SELL", 2, 45000),
    ("S02", "005930", "BUY", 1, 60000),
])


def test_holdings_drops_sold_out_tickers():
    assert portfolio.holdings(TRADES, "S01") == {"005930": 5}
    assert portfolio.holdings(TRADES, "S02") == {"005930": 1}
    assert portfolio.holdings(TRADES, "S03") == {}


def test_cash_balance():
    # 1,000,000 - 300,000 - 80,000 + 90,000
    assert portfolio.cash_balance(1000000, TRADES, "S01") == 710000
    assert portfolio.cash_balance(1000000, TRADES, "S03") == 1000000


def test_position_rows_weight_uses_total_assets():
    rows = portfolio.position_rows({"005930": 5, "035720": 5}, 500000,
                                   {"005930": 60000, "035720": 40000})
    assert [r["ticker"] for r in rows] == ["005930", "035720"]
    assert rows[0]["value"] == 300000
    assert rows[0]["weight_pct"] == pytest.approx(30.0)
    assert rows[1]["weight_pct"] == pytest.approx(20.0)


def test_day_change_pct():
    df = pd.DataFrame({"date": ["2026-09-07", "2026-09-08", "2026-09-09"],
                       "close": [40000, 44000, 42000]})
    assert portfolio.day_change_pct(df, "2026-09-07") is None
    assert portfolio.day_change_pct(df, "2026-09-08") == pytest.approx(10.0)


def test_latest_date_and_close_on():
    prices = {
        "A": pd.DataFrame({"date": ["2026-09-07", "2026-09-08"], "close": [100, 110]}),
        "B": pd.DataFrame({"date": ["2026-09-07"], "close": [200]}),
    }
    assert portfolio.latest_date(prices) == "2026-09-07"
    assert portfolio.close_on(prices, "2026-09-07") == {"A": 100, "B": 200}


def test_check_order():
    assert portfolio.check_order("BUY", 2, 50000, 100000, 0) is None
    assert portfolio.check_order("BUY", 3, 50000, 100000, 0) is not None
    assert portfolio.check_order("SELL", 2, 50000, 0, 2) is None
    assert portfolio.check_order("SELL", 3, 50000, 0, 2) is not None
    assert portfolio.check_order("BUY", 0, 50000, 100000, 0) is not None


def test_append_trade_allows_empty_journal(tmp_path):
    path = tmp_path / "trades.csv"
    shutil.copy(store.TRADES_PATH, path)
    before = store.load_trades(path)

    first = store.append_trade("S01", "2026-10-02", "005930", "BUY", 1, 56000, "", path=path)
    second = store.append_trade("S01", "2026-10-02", "005930", "SELL", 1, 56000,
                                "쉼표, 줄바꿈\n있는 일지", path=path)

    after = store.load_trades(path)
    assert len(after) == len(before) + 2
    assert int(second[1:]) == int(first[1:]) + 1
    assert after["trade_id"].is_unique
    assert after.iloc[-2]["journal"] == ""
    assert after.iloc[-1]["journal"] == "쉼표, 줄바꿈 있는 일지"
    assert after.iloc[-1]["ticker"] == "005930"


def test_ticker_names_cover_all_price_files():
    assert set(store.load_ticker_names()) == set(store.load_prices())
