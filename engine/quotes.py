"""실제 시세 조회 (공공데이터포털 금융위원회_주식시세정보). 시세 조회만 한다. LLM 호출 금지.

- 공식 API만 쓴다 (웹사이트 크롤링 금지). 주문 기능은 없다.
- 하루 늦은 종가 데이터다: 기준일 다음 영업일 오후 1시 이후 갱신.
- 같은 시세는 QUOTE_CACHE_SECONDS(5분) 동안 저장해 두고 다시 부르지 않는다.
- 실패하면 마지막 저장값, 그것도 없으면 시나리오 데이터 (status로 구분).
- 출처 표시 (공공누리 4유형): "금융위원회, 공공데이터포털"
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from config import QUOTE_CACHE_SECONDS, QUOTE_HISTORY_DAYS, QUOTE_HTTP_TIMEOUT_SECONDS

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = ROOT / "data" / "real" / "watchlist.json"
CACHE_PATH = ROOT / "data" / "real" / "quote_cache.json"
ENV_PATH = ROOT / ".env"
API_URL = ("https://apis.data.go.kr/1160100/service/"
           "GetStockSecuritiesInfoService/getStockPriceInfo")
SOURCE = "금융위원회, 공공데이터포털"
KST = ZoneInfo("Asia/Seoul")
MARKET_OPEN, MARKET_CLOSE = dtime(9, 0), dtime(15, 30)

FRESH, CACHED, STALE, SCENARIO = "fresh", "cached", "stale", "scenario"


class QuoteError(Exception):
    pass


def now_kst():
    return datetime.now(KST)


def load_watchlist(path=None):
    """{종목코드: 종목명} (고정 목록, docs/STOCKS.md)"""
    items = json.loads(Path(path or WATCHLIST_PATH).read_text(encoding="utf-8"))
    return {item["ticker"]: item["name"] for item in items}


def get_api_key():
    load_dotenv(ENV_PATH)
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise QuoteError("시세 API 키(DATA_GO_KR_KEY)가 없어요")
    return key


def market_is_open(now):
    """평일 9:00~15:30이면 장중. 공휴일은 알 수 없어 평일로 본다 (데이터는 어차피 하루 늦은 종가)."""
    return now.weekday() < 5 and MARKET_OPEN <= now.time() <= MARKET_CLOSE


def parse_items(body, ticker):
    """API 응답(dict)에서 그 종목의 [{date, close}]를 날짜순으로. 형식이 다르면 QuoteError."""
    try:
        response = body["response"]
        code = str(response["header"]["resultCode"])
        if code != "00":
            raise QuoteError(f"API 오류 {code}: {response['header'].get('resultMsg', '')}")
        items = response["body"]["items"]
        items = items.get("item", []) if isinstance(items, dict) else []
        if isinstance(items, dict):  # 한 건이면 목록이 아니라 dict로 올 수 있다
            items = [items]
        rows = [{"date": f"{i['basDt'][:4]}-{i['basDt'][4:6]}-{i['basDt'][6:8]}",
                 "close": int(str(i["clpr"]).replace(",", ""))}
                for i in items if str(i.get("srtnCd", "")).lstrip("A") == ticker]
    except (KeyError, TypeError, ValueError) as e:
        raise QuoteError(f"응답 형식이 달라요: {e!r}") from e
    if not rows:
        raise QuoteError(f"{ticker} 시세가 없어요")
    return sorted(rows, key=lambda r: r["date"])


# 공공데이터포털 게이트웨이 오류 코드 → 사람이 알아볼 말
GATEWAY_ERRORS = {
    "30": "API 키가 이 서비스에 등록되지 않았어요 (활용신청 확인, 승인 직후면 1~2시간 뒤 반영)",
    "22": "오늘 호출 한도를 넘었어요",
    "29": "이 서버 주소(IP)에서의 호출이 막혀 있어요",
    "20": "이 서비스에 접근 권한이 없어요",
}


def gateway_error(status, text):
    for code, message in GATEWAY_ERRORS.items():
        if f'"returnReasonCode": "{code}"' in text or f"<returnReasonCode>{code}<" in text:
            return f"{message} (코드 {code})"
    return f"시세 요청 실패 (HTTP {status})"


def fetch_daily(ticker, begin, api_key):
    """한 종목의 begin(YYYYMMDD)부터 최근까지 일별 종가. 실패하면 QuoteError."""
    query = urllib.parse.urlencode({
        "serviceKey": api_key, "resultType": "json", "numOfRows": 100, "pageNo": 1,
        "beginBasDt": begin, "likeSrtnCd": ticker,
    })
    try:
        with urllib.request.urlopen(f"{API_URL}?{query}",
                                    timeout=QUOTE_HTTP_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise QuoteError(gateway_error(e.code, e.read().decode("utf-8", errors="replace"))) from e
    except (OSError, ValueError) as e:  # 네트워크 오류, 시간 초과, JSON 아님
        raise QuoteError(f"시세 요청 실패: {e!r}") from e
    return parse_items(body, ticker)


def read_cache(path=None):
    path = Path(path or CACHE_PATH)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def write_cache(series, fetched_at, path=None):
    path = Path(path or CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fetched_at": fetched_at.isoformat(), "series": series},
                               ensure_ascii=False), encoding="utf-8")


def to_frames(series):
    return {ticker: pd.DataFrame(rows, columns=["date", "close"]).astype({"close": int})
            for ticker, rows in series.items()}


def load_quotes(now=None, fetch=fetch_daily, cache_path=None, watchlist_path=None):
    """실제 시세를 돌려준다.

    결과: {"status", "message", "prices": {코드: DataFrame}, "names", "fetched_at", "market_open"}
    - fresh: 방금 받음 / cached: 5분 안에 받은 것 재사용 / stale: 실패해서 마지막 저장값
    - scenario: 실패했고 저장값도 없음 → prices는 None (화면이 시나리오 데이터를 쓴다)
    """
    now = now or now_kst()
    names = load_watchlist(watchlist_path)
    cache = read_cache(cache_path)
    base = {"names": names, "market_open": market_is_open(now)}

    if cache:
        fetched_at = datetime.fromisoformat(cache["fetched_at"])
        if (now - fetched_at).total_seconds() < QUOTE_CACHE_SECONDS and set(cache["series"]) == set(names):
            return {**base, "status": CACHED, "message": None, "fetched_at": fetched_at,
                    "prices": to_frames(cache["series"])}
    try:
        key = get_api_key()
        begin = (now - timedelta(days=QUOTE_HISTORY_DAYS)).strftime("%Y%m%d")
        series = {ticker: fetch(ticker, begin, key) for ticker in names}
    except QuoteError as e:
        if cache and set(cache["series"]) == set(names):
            return {**base, "status": STALE, "fetched_at": datetime.fromisoformat(cache["fetched_at"]),
                    "message": f"시세를 불러오지 못했어요. 마지막으로 받은 시세를 보여 줘요. ({e})",
                    "prices": to_frames(cache["series"])}
        return {**base, "status": SCENARIO, "fetched_at": None, "prices": None,
                "message": f"시세를 불러오지 못했어요. 시나리오 데이터로 보여 줘요. ({e})"}
    write_cache(series, now, cache_path)
    return {**base, "status": FRESH, "message": None, "fetched_at": now,
            "prices": to_frames(series)}
