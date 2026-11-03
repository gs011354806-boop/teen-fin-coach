"""13. 실제 시세 연동 검증 (가짜 API로. 실제 네트워크는 쓰지 않는다)."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from conftest import open_app
from engine import detect, quotes, store

ROOT = Path(__file__).resolve().parent.parent
MARKET = "pages/1_가상_주식시장.py"
LESSON = "pages/3_실수에서_배우기.py"
WEEKDAY_10AM = datetime(2026, 10, 15, 10, 0, tzinfo=quotes.KST)  # 목요일


def daily(closes, start="2026-10-01"):
    day = datetime.fromisoformat(start)
    rows = []
    for close in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        rows.append({"date": day.strftime("%Y-%m-%d"), "close": close})
        day += timedelta(days=1)
    return rows


def api_body(ticker, rows, code="00"):
    items = [{"basDt": r["date"].replace("-", ""), "srtnCd": ticker, "itmsNm": "이름",
              "clpr": str(r["close"])} for r in rows]
    return {"response": {"header": {"resultCode": code, "resultMsg": "OK"},
                         "body": {"items": {"item": items}}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """가짜 키, 임시 캐시. fetch 호출 수를 센다."""
    monkeypatch.setenv("DATA_GO_KR_KEY", "test-key")
    calls = []

    def fetch(ticker, begin, key):
        calls.append(ticker)
        return daily([10000, 10100, 11300, 11200])  # 3일째 +11.9% 급등

    return {"cache": tmp_path / "cache.json", "calls": calls, "fetch": fetch}


def load(env, now=WEEKDAY_10AM, fetch=None):
    return quotes.load_quotes(now=now, fetch=fetch or env["fetch"], cache_path=env["cache"])


# --- 응답 읽기 ---

def test_parse_items_sorted_and_filtered():
    body = api_body("005930", [{"date": "2026-10-02", "close": 61000},
                               {"date": "2026-10-01", "close": 60000}])
    body["response"]["body"]["items"]["item"].append(
        {"basDt": "20261002", "srtnCd": "999999", "clpr": "1"})  # 다른 종목은 뺀다
    assert quotes.parse_items(body, "005930") == [{"date": "2026-10-01", "close": 60000},
                                                   {"date": "2026-10-02", "close": 61000}]


def test_parse_items_single_item_as_dict():
    body = api_body("005930", [{"date": "2026-10-01", "close": 60000}])
    body["response"]["body"]["items"]["item"] = body["response"]["body"]["items"]["item"][0]
    assert quotes.parse_items(body, "005930")[0]["close"] == 60000


@pytest.mark.parametrize("body", [
    {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED"}}},
    {"response": {"header": {"resultCode": "00"}, "body": {"items": ""}}},
    {"unexpected": True},
])
def test_parse_items_errors(body):
    with pytest.raises(quotes.QuoteError):
        quotes.parse_items(body, "005930")


# --- 저장·재사용·실패 ---

def test_fresh_then_reused_within_5_minutes(env):
    first = load(env)
    assert first["status"] == quotes.FRESH and len(env["calls"]) == 15
    assert set(first["prices"]) == set(quotes.load_watchlist())

    again = load(env, now=WEEKDAY_10AM + timedelta(minutes=4))
    assert again["status"] == quotes.CACHED and len(env["calls"]) == 15  # 다시 부르지 않음

    later = load(env, now=WEEKDAY_10AM + timedelta(minutes=6))
    assert later["status"] == quotes.FRESH and len(env["calls"]) == 30


def test_failure_uses_last_saved(env):
    load(env)

    def broken(ticker, begin, key):
        raise quotes.QuoteError("서버 응답 없음")

    result = load(env, now=WEEKDAY_10AM + timedelta(minutes=10), fetch=broken)
    assert result["status"] == quotes.STALE
    assert result["message"].startswith("시세를 불러오지 못했어요")
    assert result["fetched_at"] == WEEKDAY_10AM  # 마지막으로 받은 시각
    assert result["prices"]["005930"]["close"].iloc[-1] == 11200


def test_failure_without_saved_falls_back_to_scenario(env, monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY")
    monkeypatch.setattr(quotes, "ENV_PATH", env["cache"].parent / "no.env")
    result = load(env)
    assert result["status"] == quotes.SCENARIO and result["prices"] is None
    assert "시세를 불러오지 못했어요" in result["message"] and "키" in result["message"]


@pytest.mark.parametrize("now, is_open", [
    (datetime(2026, 10, 15, 10, 0, tzinfo=quotes.KST), True),    # 목 장중
    (datetime(2026, 10, 15, 8, 59, tzinfo=quotes.KST), False),   # 장 시작 전
    (datetime(2026, 10, 15, 15, 31, tzinfo=quotes.KST), False),  # 장 마감 후
    (datetime(2026, 10, 17, 11, 0, tzinfo=quotes.KST), False),   # 토요일
])
def test_market_is_open(now, is_open):
    assert quotes.market_is_open(now) is is_open


# --- 5번 감지가 실제 시세에서도 같은 기준으로 ---

def test_detection_works_on_real_quotes(env):
    prices = load(env)["prices"]
    surge_day = prices["005930"]["date"].iloc[2]
    trades = pd.DataFrame([
        ("R0001", "S01", surge_day, "005930", "BUY", 70, 11300, "올라서"),
    ], columns=store.TRADE_COLUMNS)
    found = detect.detect(trades, prices, {"student_id": "S01", "virtual_cash": 1000000})
    assert set(found[0]["patterns"]) == {detect.SURGE, detect.CONCENTRATION, detect.NO_REASON}


# --- 화면 ---

@pytest.fixture
def real_page(env, tmp_path, monkeypatch):
    monkeypatch.setattr(quotes, "CACHE_PATH", env["cache"])
    monkeypatch.setattr(quotes, "fetch_daily", env["fetch"])
    original = quotes.load_quotes
    monkeypatch.setattr(quotes, "load_quotes",
                        lambda **kw: original(now=WEEKDAY_10AM, fetch=env["fetch"], cache_path=env["cache"]))
    path = tmp_path / "real_trades.csv"
    path.write_text(",".join(store.TRADE_COLUMNS) + "\n", encoding="utf-8")
    monkeypatch.setattr(store, "REAL_TRADES_PATH", path)
    unlocks = tmp_path / "unlocks.csv"  # 9번: 실제 시세는 2단계를 연 학생만
    unlocks.write_text("student_id,stage,date\nS01,2,2026-10-02\n", encoding="utf-8")
    monkeypatch.setattr(store, "UNLOCKS_PATH", unlocks)
    return path


def open_real(page):
    at = open_app(page)
    at.session_state["price_mode"] = "real"
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_real_mode_shows_15_stocks_and_time(real_page):
    at = open_real(MARKET)
    assert len(at.main.selectbox[0].options) == 15
    text = " ".join(m.value for m in at.markdown)
    assert "종가 기준 (마지막 가격)" in text and "시세 확인 10/15 10:00" in text
    assert quotes.SOURCE in text


def test_real_mode_trade_goes_to_real_file_with_r_ids(real_page):
    at = open_real(MARKET)
    at.text_area[0].set_value("반도체 수요가 늘었다는 기사를 읽고 한 주만 사요")  # 1분 점검에 안 걸리게
    next(b for b in at.button if b.label == "주문 넣기").click()
    at = at.run()
    trades = store.load_trades(real_page)
    assert list(trades["trade_id"]) == ["R0001"] and trades.iloc[0]["ticker"] == "005930"
    assert "R0001" not in set(store.load_trades(store.TRADES_PATH)["trade_id"])  # 시나리오 거래와 분리


def test_real_mode_api_failure_shows_notice_and_scenario(real_page, monkeypatch):
    def broken(**kw):
        return {"status": quotes.SCENARIO, "prices": None, "names": {}, "fetched_at": None,
                "market_open": False, "message": "시세를 불러오지 못했어요. 시나리오 데이터로 보여 줘요."}

    monkeypatch.setattr(quotes, "load_quotes", broken)
    at = open_real(MARKET)
    assert any("시세를 불러오지 못했어요" in w.value for w in at.warning)
    assert at.main.selectbox[0].options[0] == "삼성전자 (005930)"  # 시나리오 종목으로 계속 연습


def test_lesson_page_follows_real_mode(real_page):
    real_page.write_text(",".join(store.TRADE_COLUMNS) + "\n"
                         "R0001,S01,2026-10-05,005930,BUY,70,11300,\n", encoding="utf-8")
    at = open_real(LESSON)
    assert at.main.selectbox[0].options[0].startswith("2026-10-05 삼성전자 70주 매수")


def test_real_mode_starts_with_2_million_scenario_keeps_1_million(real_page):
    from config import REAL_VIRTUAL_CASH
    assert REAL_VIRTUAL_CASH == 2_000_000
    cash = next(m for m in open_real(MARKET).metric if m.label == "가상 현금")
    assert cash.value == "2,000,000원"
    assert all(s["virtual_cash"] == 1_000_000 for s in store.load_students())  # 시나리오 기록 기준 그대로


def test_scenario_mode_is_default():
    at = open_app(MARKET)
    assert at.radio[0].value == "시나리오"  # 2단계 전이라 잠긴 스위치도 시나리오
    assert at.main.selectbox[0].options[0] == "삼성전자 (005930)"


# --- 키·목록 ---

def test_watchlist_has_at_most_15_documented_stocks():
    watchlist = quotes.load_watchlist()
    assert 0 < len(watchlist) <= 15
    doc = (ROOT / "docs" / "STOCKS.md").read_text(encoding="utf-8")
    assert all(code in doc and name in doc for code, name in watchlist.items())


def test_keys_and_cache_are_not_committed():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignored and "data/real/quote_cache.json" in ignored
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout
    assert ".env" not in tracked.splitlines()  # .env.example만 올라간다


def test_gateway_error_messages():
    body = '{"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"returnReasonCode": "30"}}}'
    assert "활용신청" in quotes.gateway_error(403, body)
    assert quotes.gateway_error(500, "알 수 없음") == "시세 요청 실패 (HTTP 500)"
