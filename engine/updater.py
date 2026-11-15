"""자동 업데이트: '지금 다시 받아야 하나?' 판단(순수 함수) + 실행기 (NEWS_MARKET_SPEC.md 3장). LLM 호출 금지.

- 일정은 config.UPDATE_JOBS (KST). news = 매일 07:00, stock_eod = 영업일 13:30 (전 영업일 종가가 그 뒤에 올라온다).
- 실행 방식 두 가지가 같은 ensure_fresh()를 부른다: A. 앱을 열 때 화면 맨 위에서 (기본)  B. python -m engine.update_all (예약 실행)
- 같은 재시도 칸 안에서 이미 실패했으면 다음 칸까지 기다린다 (API 과호출 방지). 실패해도 이전 데이터는 그대로 둔다.
- 작업 상태는 data/real/job_state.json (DB 대신 파일, CLAUDE.md).
- 영업일: 주말 · data/real/market_holidays.json · 12월 31일을 뺀다 (새 패키지를 쓰지 않으려고 휴장일 표를 둔다).
"""

import json
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "real" / "job_state.json"
HOLIDAYS_PATH = ROOT / "data" / "real" / "market_holidays.json"
KST = ZoneInfo("Asia/Seoul")
MARKET_OPEN, MARKET_CLOSE = time(9, 0), time(15, 30)

FRESH, UPDATED, FAILED, BUSY, WAITING = "fresh", "updated", "failed", "busy", "waiting"


def now_kst():
    return datetime.now(KST).replace(tzinfo=None)  # 판단은 KST 벽시계 시각으로 (저장도 같은 기준)


def _holidays():
    try:
        return {date.fromisoformat(d) for d in json.loads(HOLIDAYS_PATH.read_text(encoding="utf-8"))["dates"]}
    except (OSError, ValueError, KeyError):
        return set()


def is_business_day(d):
    if d.weekday() >= 5 or (d.month == 12 and d.day == 31):
        return False
    return d not in _holidays()


def slots(job):
    return [time.fromisoformat(s) for s in config.UPDATE_JOBS[job]["slots"]]


def due_slot(job, now):
    """now 기준 가장 최근에 지나간 정시. 오늘 정시 전이면 이전 (영업)일의 정시."""
    spec = config.UPDATE_JOBS[job]
    first = slots(job)[0]
    d = now.date()
    for _ in range(15):
        ok = not spec["business_days_only"] or is_business_day(d)
        cand = datetime.combine(d, first)
        if ok and cand <= now:
            return cand
        d -= timedelta(days=1)
    return None


def previous_business_day(d):
    d -= timedelta(days=1)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def expected_eod_date(now):
    """지금 화면에 있어야 할 최신 종가의 기준일: 13:30 수집이 지난 영업일이면 그 전 영업일, 그 전이면 하루 더 앞.
    예) 월 10:00 → 지난 목요일 / 월 14:00 → 지난 금요일 / 일요일 → 지난 목요일."""
    slot = due_slot("stock_eod", now)
    return None if slot is None else previous_business_day(slot.date())


def is_stale(job, last_success, now):
    slot = due_slot(job, now)
    return slot is not None and (last_success is None or last_success < slot)


def should_attempt(job, last_success, last_attempt, now):
    """오래됐더라도 같은 재시도 칸 안에서 이미 시도했다면 다음 칸까지 기다린다."""
    if not is_stale(job, last_success, now):
        return False
    if last_attempt is None:
        return True
    today_slots = [datetime.combine(now.date(), t) for t in slots(job)]
    passed = [s for s in today_slots if s <= now]
    current = max(passed) if passed else due_slot(job, now)
    if passed and current == today_slots[-1]:  # 마지막 재시도 칸이 지나면 일정 간격마다 한 번 더
        step = timedelta(minutes=config.RETRY_AFTER_LAST_MIN)
        current += step * int((now - current) / step)
    return last_attempt < current


# ---------- 상태 저장 (파일) ----------

def _parse(value):
    return datetime.fromisoformat(value) if value else None


def load_state(job, path=None):
    path = Path(path or STATE_PATH)
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get(job, {})
    except (OSError, ValueError):
        raw = {}
    return {"last_success": _parse(raw.get("last_success")), "last_attempt": _parse(raw.get("last_attempt")),
            "last_error": raw.get("last_error")}


def save_state(job, state, path=None):
    path = Path(path or STATE_PATH)
    try:
        allstates = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        allstates = {}
    allstates[job] = {k: (v.isoformat(timespec="seconds") if isinstance(v, datetime) else v) for k, v in state.items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(allstates, ensure_ascii=False, indent=1), encoding="utf-8")


_locks = {}


def ensure_fresh(job, run_job, now=None, path=None):
    """필요할 때만 run_job()을 한 번 실행한다. 반환: fresh | updated | failed | busy | waiting.
    run_job은 실패하면 예외를 낸다 (그러면 이전 데이터를 그대로 둔다)."""
    now = now or now_kst()
    state = load_state(job, path)
    if not is_stale(job, state["last_success"], now):
        return FRESH
    if not should_attempt(job, state["last_success"], state["last_attempt"], now):
        return WAITING
    lock = _locks.setdefault(job, threading.Lock())
    if not lock.acquire(blocking=False):
        return BUSY  # 다른 사람이 이미 받는 중
    try:
        state["last_attempt"] = now
        try:
            run_job()
            state["last_success"], state["last_error"] = now, None
            return UPDATED
        except Exception as e:  # 실패해도 앱은 이전 데이터로 계속 동작한다
            state["last_error"] = f"{type(e).__name__}: {e}"
            return FAILED
    finally:
        save_state(job, state, path)
        lock.release()


def when_text(t, now):
    day = "오늘" if t.date() == now.date() else "어제" if t.date() == now.date() - timedelta(days=1) else f"{t.month}월 {t.day}일"
    return f"{day} {'오전' if t.hour < 12 else '오후'} {t.hour % 12 or 12}:{t.minute:02d}"


def next_slot_text(job, now):
    """다음 정시 안내 ('내일 오전 7:00')."""
    first = slots(job)[0]
    d = now.date()
    for _ in range(15):
        cand = datetime.combine(d, first)
        if cand > now and (not config.UPDATE_JOBS[job]["business_days_only"] or is_business_day(d)):
            day = ("오늘" if d == now.date() else "내일" if d == now.date() + timedelta(days=1)
                   else f"{d.month}월 {d.day}일")
            return f"{day} {'오전' if first.hour < 12 else '오후'} {first.hour % 12 or 12}:{first.minute:02d}"
        d += timedelta(days=1)
    return ""


def status_label(job, state, now):
    """상단 상태 줄: (ok | busy | fail, 문구)."""
    if state["last_success"] and not is_stale(job, state["last_success"], now):
        return "ok", f"{when_text(state['last_success'], now)} 업데이트됨"
    if state["last_error"]:
        return "fail", "업데이트 실패 · 이전 데이터를 보는 중"
    return "busy", "업데이트하는 중…"


def market_open(now):
    return is_business_day(now.date()) and MARKET_OPEN <= now.time() < MARKET_CLOSE


def eod_caption(bas_dt):
    """'11월 13일(금) 종가 기준 · 영업일 오후 1시 30분 자동 업데이트' (bas_dt: date 또는 'YYYY-MM-DD')."""
    d = date.fromisoformat(bas_dt) if isinstance(bas_dt, str) else bas_dt
    first = slots("stock_eod")[0]
    at = f"오후 {first.hour % 12 or 12}시" + (f" {first.minute}분" if first.minute else "")
    return f"{d.month}월 {d.day}일({'월화수목금토일'[d.weekday()]}) 종가 기준 · 영업일 {at} 자동 업데이트"
