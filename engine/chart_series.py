"""주식 차트 데이터 — 저장은 일봉만, 그릴 때 주·월로 묶는다 (2026-11-17, 시뮬레이션 ·
invest & card_new/teengrow_chart/CHART_SPEC.md 2장, 참고 코드 series.py를 그대로 옮김). 순수 함수. LLM 호출 금지.

  일봉 (최근 3년, 액면분할 보정 후)
     └─ window(period)  → 기간 안의 막대 + 비교 기준 가격 (기간 시작일까지의 마지막 종가)
          └─ resample(interval) → 일/주/월봉 (시가=첫날, 고가=최고, 저가=최저, 종가=마지막날, 거래량=합)
- 기간 × 봉 규칙(ALLOWED): 막대가 4개 미만이면 뜻이 없고 300개를 넘으면 폰에서 너무 빽빽하다.
- 상장 3년 미만이면 긴 기간을 '전체' 버튼 하나로 합친다.
- 공공데이터 시세는 수정주가가 아니라서 액면분할·병합을 상장주식수로 감지해 그릴 때만 보정한다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta

# ── 기간·봉 규칙 (시안 Chart-Rules 표와 같다) ─────────────────────
PERIODS = ["1W", "1M", "3M", "1Y", "3Y"]
PERIOD_LABEL = {"1W": "1주", "1M": "1달", "3M": "3달", "1Y": "1년", "3Y": "3년", "ALL": "전체"}
INTERVAL_LABEL = {"D": "일봉", "W": "주봉", "M": "월봉"}
ALLOWED = {"1W": ["D"], "1M": ["D", "W"], "3M": ["D", "W"], "1Y": ["D", "W", "M"], "3Y": ["W", "M"], "ALL": ["D", "W", "M"]}
DEFAULT_INTERVAL = {"1W": "D", "1M": "D", "3M": "D", "1Y": "W", "3Y": "W", "ALL": "W"}
BLOCK_REASON = {
    "1W": "1주는 일봉만 봐요",
    "1M": "1달은 월봉이 1~2개라 뜻이 없어요",
    "3M": "3달은 월봉이 3~4개라 뜻이 없어요",
    "3Y": "3년은 일봉 대신 주·월봉으로 봐요 (막대 740개는 너무 많아요)",
}
MIN_BARS, MAX_BARS = 4, 300          # 'ALL'(상장 3년 미만)에서 봉을 고를 때 쓰는 기준
HISTORY_YEARS = 3


@dataclass(frozen=True)
class Bar:
    d: date              # 막대 시작일 (일봉은 그날, 주봉은 첫 거래일, 월봉은 첫 거래일)
    o: float
    h: float
    l: float
    c: float
    v: int
    e: date | None = None          # 막대 마지막 거래일 (일봉은 d와 같음)
    shares: int = 0                # 상장주식수 (액면분할 감지용, 일봉만)
    n: int = 1                     # 묶인 거래일 수
    partial: bool = False          # 진행 중인 주·월


# ── 기간 ─────────────────────────────────────────────────────
def _months_back(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def period_start(period: str, end: date) -> date:
    """이 날짜 '이후'의 거래일이 기간에 들어간다. 비교 기준 = 이 날짜까지의 마지막 종가."""
    if period == "1W":
        return end - timedelta(days=7)
    return _months_back(end, {"1M": 1, "3M": 3, "1Y": 12, "3Y": 36}[period])


def period_buttons(first_day: date, end: date) -> list[str]:
    """상장 기간이 짧으면 담을 수 없는 긴 기간을 '전체(ALL)' 하나로 합친다."""
    out = []
    for p in PERIODS:
        if period_start(p, end) >= first_day:
            out.append(p)
        else:
            out.append("ALL")
            break
    return out


def normalize(period: str, interval: str | None) -> str:
    """기간에서 못 쓰는 봉이면 그 기간의 기본 봉으로."""
    return interval if interval in ALLOWED[period] else DEFAULT_INTERVAL[period]


def blocked_note(period: str) -> str:
    return BLOCK_REASON.get(period, "")


# ── 묶기 ─────────────────────────────────────────────────────
def _key(d: date, interval: str):
    if interval == "D":
        return d
    if interval == "W":
        return d - timedelta(days=d.weekday())        # 그 주 월요일
    return (d.year, d.month)


def resample(daily: list[Bar], interval: str, today: date | None = None) -> list[Bar]:
    """일봉 → 일/주/월봉. 시가=첫날, 고가=최고, 저가=최저, 종가=마지막날, 거래량=합."""
    if interval == "D":
        return [replace(b, e=b.d) for b in daily]
    out: list[Bar] = []
    cur, k = None, None
    for b in daily:
        kk = _key(b.d, interval)
        if kk != k:
            if cur:
                out.append(cur)
            k = kk
            cur = Bar(b.d, b.o, b.h, b.l, b.c, b.v, e=b.d, n=1)
        else:
            cur = Bar(cur.d, cur.o, max(cur.h, b.h), min(cur.l, b.l), b.c, cur.v + b.v, e=b.d, n=cur.n + 1)
    if cur:
        if today is not None and _key(today, interval) == k:
            cur = replace(cur, partial=True)          # 이번 주·이번 달은 아직 끝나지 않음
        out.append(cur)
    return out


@dataclass(frozen=True)
class View:
    period: str
    interval: str
    bars: list[Bar]
    base: float               # 비교 기준 가격
    base_date: date | None    # None이면 상장 첫날 시가 기준
    last: float
    note: str                 # 막아 둔 봉 안내

    @property
    def change(self) -> float:
        return self.last - self.base

    @property
    def pct(self) -> float:
        return (self.last / self.base - 1) * 100 if self.base else 0.0


def window(daily: list[Bar], period: str, interval: str | None = None, today: date | None = None) -> View:
    """기간 하나를 화면용으로. 경계에 걸친 주·월은 통째로 넣는다."""
    if not daily:
        raise ValueError("시세가 없어요")
    end = daily[-1].d
    interval = normalize(period, interval)
    if period == "ALL":
        start = daily[0].d - timedelta(days=1)
    else:
        start = period_start(period, end)
    before = [b for b in daily if b.d <= start]
    inside = [b for b in daily if b.d > start]
    base, base_date = (before[-1].c, before[-1].d) if before else (inside[0].o, None)
    bars = [b for b in resample(daily, interval, today) if (b.e or b.d) > start]
    note = blocked_note(period) if len(ALLOWED[period]) < 3 else ""
    return View(period, interval, bars, base, base_date, daily[-1].c, note)


def summary(daily: list[Bar], view: View) -> dict:
    """'한눈에 보기' 카드 값."""
    start = view.bars[0].d
    inside = [b for b in daily if b.d >= start]
    hi = max(inside, key=lambda b: b.h)
    lo = min(inside, key=lambda b: b.l)
    return {
        "pct": round(view.pct, 2), "change": view.change, "base": view.base, "base_date": view.base_date,
        "high": hi.h, "high_date": hi.d, "low": lo.l, "low_date": lo.d,
        "avg_volume": round(sum(b.v for b in inside) / len(inside)),
        "bars": len(view.bars),
    }


# ── 액면분할·병합 보정 ────────────────────────────────────────
@dataclass(frozen=True)
class SplitEvent:
    d: date
    ratio: float          # 주식 수 배율 (5 = 1주가 5주로)


def detect_splits(daily: list[Bar], tol: float = 0.3) -> list[SplitEvent]:
    """상장주식수가 갑자기 몇 배가 되고 가격이 그 반대로 움직이면 분할(또는 병합)로 본다."""
    out = []
    for a, b in zip(daily, daily[1:]):
        if not (a.shares and b.shares):
            continue
        r = b.shares / a.shares
        if 0.55 < r < 1.9:
            continue                                  # 유상증자 등 작은 변화는 보정하지 않음
        price_r = a.c / b.o if b.o else 0
        if price_r and abs(price_r / r - 1) <= tol:
            out.append(SplitEvent(b.d, round(r, 4)))
    return out


def adjust(daily: list[Bar], events: list[SplitEvent]) -> list[Bar]:
    """분할 전 가격을 배율로 나누고 거래량은 곱해 하나로 이어지게 한다."""
    out = []
    for b in daily:
        f = 1.0
        for ev in events:
            if b.d < ev.d:
                f *= ev.ratio
        if f == 1.0:
            out.append(b)
        else:
            out.append(replace(b, o=b.o / f, h=b.h / f, l=b.l / f, c=b.c / f, v=round(b.v * f)))
    return out


# ── 백필 계획 ────────────────────────────────────────────────
def history_start(today: date, years: int = HISTORY_YEARS) -> date:
    return _months_back(today, 12 * years) - timedelta(days=7)     # 기준 종가용 여유 1주


def backfill_range(oldest_stored: date | None, today: date, done: bool = False) -> tuple[date, date] | None:
    """더 받아야 할 구간 (begin, end). 이미 3년을 채웠거나 상장일까지 받았으면 None."""
    want = history_start(today)
    if done or (oldest_stored is not None and oldest_stored <= want):
        return None
    end = (oldest_stored - timedelta(days=1)) if oldest_stored else today
    return want, end


def backfill_progress(oldest_stored: date | None, today: date) -> float:
    """3년 중 몇 %를 받았는지 (화면의 '36개월 중 14개월')."""
    if oldest_stored is None:
        return 0.0
    want = history_start(today)
    total = (today - want).days
    got = (today - max(oldest_stored, want)).days
    return max(0.0, min(1.0, got / total))
