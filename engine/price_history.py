"""3년치 일봉 저장 · 백필 · 그릴 때 액면분할 보정 (2026-11-17, 시뮬레이션 · CHART_SPEC.md 1장). LLM 호출 금지.

- 저장은 일봉 한 가지 (주·월봉은 그릴 때 계산): data/real/price_history/<종목코드>.json (DB 대신 파일, CLAUDE.md)
  {"code", "name", "rows": [{d, o, h, l, c, v, s(상장주식수)}], "oldest", "done", "updated_at"}
- 받는 곳은 기존 시세와 같은 공공데이터포털 주식시세정보 V2 (quotes.API_URL, DATA_GO_KR_KEY).
  구간 조회 beginBasDt~endBasDt, numOfRows=1000, totalCount를 보고 pageNo를 넘긴다 (종목 하나 3년 ≈ 740줄 → 보통 1번).
- 백필: 최근 3년(+1주)이 안 찼으면 모자란 앞부분만 받는다. 앱을 연 사람이 기다리지 않게 뒤에서(스레드) 돌리고,
  한 번에 config.CHART_BACKFILL_PER_RUN 종목까지만. 실패하면 다음에 다시 (이미 받은 것은 그대로).
- 매일 13:30 자동 업데이트(quotes.refresh)가 받은 최근 시세도 여기에 합친다 (merge_daily).
- 원본은 그대로 두고 그릴 때만 분할 보정한다 (chart_bars).
"""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import config
from engine import chart_series as cs, quotes

ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = ROOT / "data" / "real" / "price_history"
PAGE_SIZE = 1000
MAX_PAGES = 5
HOLIDAY_GRACE_DAYS = 10  # 요청 시작일이 연휴면 첫 거래일이 며칠 늦을 수 있다
BACKGROUND = True        # 테스트에서는 False (스레드 없이 바로)
RETRY_MINUTES = 60       # 백필이 실패하면 이만큼 뒤에 다시


def _int(v):
    return int(str(v or 0).replace(",", "").strip() or 0)


# ---------- 받기 ----------

def parse_bars(payload, code):
    """API JSON → ([일봉 dict], totalCount). 상장주식수(lstgStCnt)도 함께."""
    try:
        response = payload["response"]
        rc = str(response["header"]["resultCode"])
        if rc != "00":
            raise quotes.QuoteError(f"API 오류 {rc}: {response['header'].get('resultMsg', '')}")
        body = response["body"]
    except (KeyError, TypeError) as e:
        raise quotes.QuoteError(f"응답 형식이 달라요: {e!r}") from e
    total = _int(body.get("totalCount"))
    items = (body.get("items") or {})
    items = items.get("item", []) if isinstance(items, dict) else []
    if isinstance(items, dict):
        items = [items]
    want = str(code).zfill(6)
    rows = []
    for it in items:
        if str(it.get("srtnCd", "")).lstrip("A").zfill(6) != want:
            continue
        d = str(it["basDt"])
        c = _int(it.get("clpr"))
        if c <= 0:
            continue
        rows.append({"d": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "o": _int(it.get("mkp")) or c, "h": _int(it.get("hipr")) or c,
                     "l": _int(it.get("lopr")) or c, "c": c, "v": _int(it.get("trqu")), "s": _int(it.get("lstgStCnt"))})
    return rows, total


def http_json(params):
    url = f"{quotes.API_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=config.QUOTE_HTTP_TIMEOUT_SECONDS + 10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise quotes.QuoteError(quotes.gateway_error(e.code, e.read().decode("utf-8", errors="replace"))) from e
    except (OSError, ValueError) as e:
        raise quotes.QuoteError(f"시세 요청 실패: {e!r}") from e


def fetch_range(code, begin, end, key=None, get=http_json):
    """begin~end 일봉 (날짜 오름차순). 페이지를 넘겨 가며 다 받는다."""
    key = key or quotes.get_api_key()
    got = {}
    for page in range(1, MAX_PAGES + 1):
        rows, total = parse_bars(get({"serviceKey": key, "resultType": "json", "numOfRows": PAGE_SIZE, "pageNo": page,
                                      "likeSrtnCd": code, "beginBasDt": begin.strftime("%Y%m%d"),
                                      "endBasDt": end.strftime("%Y%m%d")}), code)
        for r in rows:
            got[r["d"]] = r
        if page * PAGE_SIZE >= total or not rows:
            break
    return [got[d] for d in sorted(got)]


# ---------- 저장 ----------

def path_for(code, history_dir=None):
    return Path(history_dir or HISTORY_DIR) / f"{code}.json"


def load(code, history_dir=None):
    p = path_for(code, history_dir)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"code": code, "name": "", "rows": [], "oldest": None, "done": False}


def save(doc, history_dir=None):
    p = path_for(doc["code"], history_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def merge(doc, rows):
    """같은 날은 새 값으로, 날짜순. 상장주식수가 없는 새 줄은 이전 값을 지키지 않는다(0이면 감지에서 빠진다)."""
    by_day = {r["d"]: r for r in doc["rows"]}
    for r in rows:
        old = by_day.get(r["d"], {})
        by_day[r["d"]] = {**old, **{k: v for k, v in r.items() if v or k not in old}}
    doc["rows"] = [by_day[d] for d in sorted(by_day)]
    if doc["rows"]:
        doc["oldest"] = min(doc.get("oldest") or doc["rows"][0]["d"], doc["rows"][0]["d"])
    return doc


def merge_daily(series, names=None, history_dir=None):
    """자동 업데이트(quotes.refresh)가 받은 최근 시세 {코드: [{date, close, open, high, low, volume, ...}]}를 합친다."""
    for code, rows in series.items():
        doc = load(code, history_dir)
        if names and not doc.get("name"):
            doc["name"] = names.get(code, "")
        merge(doc, [{"d": r["date"], "o": r.get("open") or r["close"], "h": r.get("high") or r["close"],
                     "l": r.get("low") or r["close"], "c": r["close"], "v": r.get("volume", 0),
                     "s": r.get("listed_shares", 0)} for r in rows])
        save(doc, history_dir)


def backfill(code, name, today, fetch=None, history_dir=None):
    """3년이 안 찼으면 모자란 앞부분을 받는다. 반환: done / filled / listed_recently / empty. API 오류는 그대로 올린다."""
    doc = load(code, history_dir)
    doc["name"] = doc.get("name") or name
    oldest = date.fromisoformat(doc["oldest"]) if doc.get("oldest") else None
    rng = cs.backfill_range(oldest, today, doc.get("done", False))
    if rng is None:
        return "done"
    begin, end = rng
    rows = (fetch or fetch_range)(code, begin, end)
    if rows:
        merge(doc, rows)
        oldest = date.fromisoformat(doc["oldest"])
    if oldest is None:
        return "empty"
    doc["done"] = True  # 요청 구간에서 받은 것이 그 종목의 전부 → 다시 받지 않는다
    save(doc, history_dir)
    return "filled" if oldest <= begin + timedelta(days=HOLIDAY_GRACE_DAYS) else "listed_recently"


def state(code, today, history_dir=None):
    """(받은 비율 0~1, 다 받았는지)."""
    doc = load(code, history_dir)
    if doc.get("done"):
        return 1.0, True
    oldest = date.fromisoformat(doc["oldest"]) if doc.get("oldest") else None
    return cs.backfill_progress(oldest, today), False


_lock = threading.Lock()
_last_try = {}


def backfill_some(codes, names, today, fetch=None, history_dir=None, limit=None):
    """아직 3년을 다 받지 않은 종목을 limit개까지 받는다. {코드: 결과}. 하나가 실패하면 거기서 멈춘다 (다음에 다시)."""
    limit = limit or config.CHART_BACKFILL_PER_RUN
    out = {}
    for code in codes:
        if len(out) >= limit:
            break
        if load(code, history_dir).get("done"):
            continue
        try:
            out[code] = backfill(code, names.get(code, ""), today, fetch, history_dir)
        except quotes.QuoteError as e:
            out[code] = f"error: {e}"
            break
    return out


def start_backfill(codes, names, today, history_dir=None):
    """화면을 그리는 사람이 기다리지 않게 뒤에서 백필. 이미 도는 중이거나 최근에 실패했으면 아무것도 안 한다."""
    if not config.CHART_V2 or all(load(c, history_dir).get("done") for c in codes):
        return False
    now = datetime.now()
    if _last_try.get("at") and now - _last_try["at"] < timedelta(minutes=RETRY_MINUTES) and _last_try.get("failed"):
        return False
    if not _lock.acquire(blocking=False):
        return False

    def run():
        try:
            result = backfill_some(codes, names, today, history_dir=history_dir)
            _last_try.update(at=datetime.now(), failed=any(str(v).startswith("error") for v in result.values()))
        finally:
            _lock.release()

    if BACKGROUND:
        threading.Thread(target=run, daemon=True, name="price-backfill").start()
    else:
        run()
    return True


# ---------- 그릴 때 ----------

def to_bars(rows):
    return [cs.Bar(date.fromisoformat(r["d"]), r["o"], r["h"], r["l"], r["c"], r.get("v", 0), shares=r.get("s", 0))
            for r in rows]


def chart_bars(code, today, history_dir=None):
    """화면용: 최근 3년 일봉을 분할 보정까지 마친 것 + 분할 이벤트(깃발용)."""
    start = cs.history_start(today).isoformat()
    raw = to_bars([r for r in load(code, history_dir)["rows"] if r["d"] >= start])
    events = cs.detect_splits(raw)
    return cs.adjust(raw, events), events


def close_only_bars(rows):
    """시나리오(연습용 가상 시세)처럼 종가만 있을 때: 시=고=저=종, 거래량 0 → 선 그래프로만."""
    return [cs.Bar(date.fromisoformat(d), c, c, c, c, 0) for d, c in rows]


def demo_bars(symbol, last_price, end, years=3, seed=None):
    """시안(?mock)용 가상 3년 일봉: 종목마다 같은 모양이 나오는 무작위 걸음, 마지막 종가 = 시안 가격. 실제 시세가 아니다."""
    import random
    rng = random.Random(seed if seed is not None else sum(map(ord, symbol)))
    start = cs.history_start(end, years)
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    price, rows = 100.0, []
    for d in days:
        o = price * (1 + rng.gauss(0, 0.006))
        c = o * (1 + rng.gauss(0.0004, 0.016))
        h, l = max(o, c) * (1 + abs(rng.gauss(0, 0.006))), min(o, c) * (1 - abs(rng.gauss(0, 0.006)))
        rows.append((d, o, h, l, c, int(abs(rng.gauss(1, 0.35)) * 1_200_000)))
        price = c
    k = last_price / rows[-1][4]
    rnd = (lambda x: round(x * k / 50) * 50) if last_price > 10_000 else (lambda x: round(x * k))
    out = []
    for d, o, h, l, c, v in rows:
        o2, c2 = rnd(o), rnd(c)
        out.append(cs.Bar(d, o2, max(rnd(h), o2, c2), min(rnd(l), o2, c2), c2, v))
    last = out[-1]
    out[-1] = cs.Bar(last.d, last.o, max(last.h, last_price), min(last.l, last_price), last_price, last.v)
    return out
