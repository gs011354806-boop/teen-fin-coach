"""주식 차트 (invest & card_new/teengrow_chart/CHART_SPEC.md 4장). 실제 API는 부르지 않는다."""
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from engine import chart_series as s  # noqa: E402
from engine.chart_series import Bar  # noqa: E402

TODAY = date(2026, 11, 16)
END = date(2026, 11, 13)          # 마지막 종가(금)


def days(start: date, end: date, skip=()):
    d, out = start, []
    while d <= end:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += timedelta(days=1)
    return out


def series_for(start=date(2023, 11, 6), end=END, skip=(), price=lambda i: 50000 + 10 * i, shares=1000):
    out = []
    for i, d in enumerate(days(start, end, skip)):
        c = price(i)
        out.append(Bar(d, c - 50, c + 200, c - 300, c, 1000 + i, shares=shares))
    return out


DAILY = series_for()


# ── 묶기 ─────────────────────────────────────────────────────
def test_weekly_ohlcv():
    week = [b for b in DAILY if date(2026, 11, 9) <= b.d <= END]          # 월~금 5일
    w = s.resample(week, "W")
    assert len(w) == 1
    b = w[0]
    assert (b.d, b.e, b.n) == (date(2026, 11, 9), END, 5)
    assert b.o == week[0].o and b.c == week[-1].c
    assert b.h == max(x.h for x in week) and b.l == min(x.l for x in week)
    assert b.v == sum(x.v for x in week)


def test_weekly_skips_holidays():
    d = series_for(date(2026, 9, 21), date(2026, 10, 2), skip={date(2026, 9, 24), date(2026, 9, 25)})
    w = s.resample(d, "W")
    assert [x.n for x in w] == [3, 5]                     # 추석 연휴 주는 3거래일


def test_monthly_and_partial():
    m = s.resample(DAILY, "M", today=TODAY)
    assert m[-1].d == date(2026, 11, 2) and m[-1].partial and not m[-2].partial
    assert len(m) == 37                                   # 2023.11 ~ 2026.11


# ── 기간·봉 규칙 ────────────────────────────────────────────
@pytest.mark.parametrize("period,interval,expect", [
    ("1W", "M", "D"), ("1M", "M", "D"), ("1M", "W", "W"), ("3Y", "D", "W"), ("3Y", "M", "M"), ("1Y", None, "W")])
def test_normalize(period, interval, expect):
    assert s.normalize(period, interval) == expect


@pytest.mark.parametrize("period,interval,lo,hi", [
    ("1W", "D", 5, 5), ("1M", "D", 20, 23), ("3M", "D", 60, 66), ("3M", "W", 13, 15),
    ("1Y", "D", 245, 262), ("1Y", "W", 52, 54), ("1Y", "M", 13, 13), ("3Y", "W", 156, 158), ("3Y", "M", 37, 37)])
def test_bar_counts_match_rules_table(period, interval, lo, hi):
    n = len(s.window(DAILY, period, interval).bars)
    assert lo <= n <= hi and s.MIN_BARS <= n <= s.MAX_BARS


def test_period_start_and_base():
    v = s.window(DAILY, "1Y", "W")
    assert s.period_start("1Y", END) == date(2025, 11, 13)
    assert v.base_date == date(2025, 11, 13)              # 기간 시작 직전 거래일 종가와 비교
    before = [b for b in DAILY if b.d <= date(2025, 11, 13)][-1]
    assert v.base == before.c and math.isclose(v.pct, (DAILY[-1].c / before.c - 1) * 100)


def test_boundary_week_included_whole():
    v = s.window(DAILY, "1M", "W")
    assert v.bars[0].d <= date(2026, 10, 13) <= (v.bars[0].e or v.bars[0].d) or v.bars[0].d == date(2026, 10, 12)
    assert v.bars[0].n == 5                               # 잘리지 않은 온전한 주


def test_month_end_clamp():
    assert s.period_start("1M", date(2026, 3, 31)) == date(2026, 2, 28)
    assert s.period_start("1Y", date(2024, 2, 29)) == date(2023, 2, 28)


def test_blocked_note_only_when_blocked():
    assert "3년은 일봉" in s.window(DAILY, "3Y").note
    assert s.window(DAILY, "1Y").note == ""


# ── 상장 3년 미만 ────────────────────────────────────────────
def test_period_buttons_short_listing():
    assert s.period_buttons(DAILY[0].d, END) == ["1W", "1M", "3M", "1Y", "3Y"]
    assert s.period_buttons(date(2025, 7, 14), END) == ["1W", "1M", "3M", "1Y", "ALL"]
    assert s.period_buttons(date(2026, 5, 4), END) == ["1W", "1M", "3M", "ALL"]


def test_all_period_uses_first_open():
    short = series_for(date(2025, 7, 14))
    v = s.window(short, "ALL")
    assert v.base_date is None and v.base == short[0].o and v.interval == "W"


# ── 요약 ─────────────────────────────────────────────────────
def test_summary_values():
    v = s.window(DAILY, "3M", "D")
    sm = s.summary(DAILY, v)
    inside = [b for b in DAILY if b.d >= v.bars[0].d]
    assert sm["high"] == max(b.h for b in inside) and sm["low"] == min(b.l for b in inside)
    assert sm["bars"] == len(v.bars)


# ── 액면분할 ─────────────────────────────────────────────────
def split_series():
    d = days(date(2026, 1, 5), date(2026, 3, 27))
    cut = date(2026, 2, 16)
    out = []
    for i, x in enumerate(d):
        if x < cut:
            out.append(Bar(x, 250000, 252000, 248000, 250000, 1000, shares=100))
        else:
            out.append(Bar(x, 50000, 50400, 49600, 50000, 5000, shares=500))
    return out, cut


def test_detect_and_adjust_split():
    raw, cut = split_series()
    ev = s.detect_splits(raw)
    assert len(ev) == 1 and ev[0].d == cut and ev[0].ratio == 5
    adj = s.adjust(raw, ev)
    assert adj[0].c == 50000 and adj[0].v == 5000 and adj[-1].c == 50000
    v = s.window(adj, "3M", "D")
    assert abs(v.pct) < 1                                 # 보정 안 하면 −80%로 보였을 구간


def test_small_share_change_is_not_split():
    raw = series_for(date(2026, 10, 1))
    raw[5] = Bar(raw[5].d, raw[5].o, raw[5].h, raw[5].l, raw[5].c, raw[5].v, shares=1100)   # 유상증자 10%
    assert s.detect_splits(raw) == []


def test_reverse_split():
    d = days(date(2026, 4, 1), date(2026, 4, 30))
    raw = [Bar(x, 1000, 1010, 990, 1000, 100, shares=1000) if i < 10 else Bar(x, 10000, 10100, 9900, 10000, 10, shares=100)
           for i, x in enumerate(d)]
    ev = s.detect_splits(raw)
    assert len(ev) == 1 and ev[0].ratio == 0.1
    assert s.adjust(raw, ev)[0].c == pytest.approx(10000)


# ── 백필 ─────────────────────────────────────────────────────
def test_backfill_range_and_progress():
    want = s.history_start(TODAY)
    assert want == date(2023, 11, 9)
    assert s.backfill_range(None, TODAY) == (want, TODAY)
    assert s.backfill_range(date(2026, 1, 2), TODAY) == (want, date(2026, 1, 1))
    assert s.backfill_range(date(2023, 11, 9), TODAY) is None
    assert s.backfill_range(date(2025, 7, 14), TODAY, done=True) is None
    assert s.backfill_progress(None, TODAY) == 0
    assert 0.35 < s.backfill_progress(date(2025, 9, 15), TODAY) < 0.4


# ── 저장 · 백필 (JSON 파일) ───────────────────────────────────
def api_page(params, total=1500):
    start = (params["pageNo"] - 1) * 1000
    items = []
    for i in range(start, min(start + 1000, total)):
        d = date(2020, 1, 1) + timedelta(days=i)
        items.append({"basDt": d.strftime("%Y%m%d"), "srtnCd": "005930", "itmsNm": "삼성전자", "clpr": "50,000",
                      "mkp": "49900", "hipr": "50500", "lopr": "49500", "trqu": "100", "lstgStCnt": "5969782550"})
    return {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": total, "items": {"item": items}}}}


def test_fetch_range_paginates():
    from engine import price_history as ph
    calls = []

    def get(params):
        calls.append(params["pageNo"])
        return api_page(params)
    rows = ph.fetch_range("005930", date(2020, 1, 1), date(2024, 2, 9), key="k", get=get)
    assert calls == [1, 2] and len(rows) == 1500
    assert rows[0]["d"] < rows[-1]["d"] and rows[0]["c"] == 50000 and rows[0]["s"] == 5969782550


def test_backfill_then_done_and_recent_listing(tmp_path):
    from engine import price_history as ph
    want = s.history_start(TODAY)
    full = [{"d": d.isoformat(), "o": 100, "h": 110, "l": 90, "c": 100, "v": 1, "s": 10} for d in days(want, END)]
    calls = []

    def fetch(code, b, e):
        calls.append((b, e))
        return [r for r in full if b.isoformat() <= r["d"] <= e.isoformat()]
    assert ph.backfill("005930", "삼성전자", TODAY, fetch, tmp_path) == "filled"
    assert ph.backfill("005930", "삼성전자", TODAY, fetch, tmp_path) == "done" and len(calls) == 1
    assert ph.state("005930", TODAY, tmp_path) == (1.0, True)
    recent = [r for r in full if r["d"] >= "2025-07-14"]
    assert ph.backfill("NEW01", "새 종목", TODAY, lambda c, b, e: recent, tmp_path) == "listed_recently"

    def never(c, b, e):
        raise AssertionError("다시 받으면 안 돼요")
    assert ph.backfill("NEW01", "새 종목", TODAY, never, tmp_path) == "done"


def test_merge_daily_keeps_history_and_chart_bars_adjust(tmp_path):
    from engine import price_history as ph
    raw, cut = split_series()
    doc = {"code": "X", "name": "", "rows": [{"d": b.d.isoformat(), "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v,
                                             "s": b.shares} for b in raw], "oldest": None, "done": True}
    ph.save(ph.merge(doc, []), tmp_path)
    ph.merge_daily({"X": [{"date": "2026-03-30", "close": 50500, "open": 50000, "high": 50600, "low": 49900, "volume": 7}]},
                   history_dir=tmp_path)
    daily, events = ph.chart_bars("X", date(2026, 3, 31), tmp_path)
    assert daily[-1].c == 50500 and len(events) == 1 and daily[0].c == 50000  # 분할 전 가격은 그릴 때만 보정
    assert ph.load("X", tmp_path)["rows"][0]["c"] == 250000  # 원본은 그대로 저장


def test_backfill_some_stops_on_error(tmp_path):
    from engine import price_history as ph, quotes

    def boom(code, b, e):
        raise quotes.QuoteError("서버 응답 없음")
    out = ph.backfill_some(["A", "B"], {}, TODAY, fetch=boom, history_dir=tmp_path)
    assert list(out) == ["A"] and out["A"].startswith("error") and not ph.load("A", tmp_path)["done"]


def test_demo_bars_end_at_price_and_cover_three_years():
    from engine import price_history as ph
    bars = ph.demo_bars("HB01", 62200, END)
    assert bars[-1].c == 62200 and bars[0].d <= s.history_start(END) + timedelta(days=3)
    assert all(b.l <= min(b.o, b.c) and b.h >= max(b.o, b.c) for b in bars)
    assert ph.demo_bars("HB01", 62200, END)[100] == bars[100]  # 같은 종목은 같은 모양


def test_avg_cost_moving_average():
    import pandas as pd
    from engine import invest_view as iv
    t = pd.DataFrame([("S01", "2026-10-01", "X", "BUY", 2, 100), ("S01", "2026-10-02", "X", "BUY", 2, 200),
                      ("S01", "2026-10-03", "X", "SELL", 1, 300)],
                     columns=["student_id", "date", "ticker", "side", "qty", "price"])
    assert iv.avg_cost(t, "S01", "X") == (150, 3) and iv.avg_cost(t, "S01", "Y") == (None, 0)


# ── 그래프 (Altair) ───────────────────────────────────────────
def test_chart_candle_line_colors_axis_and_no_zoom():
    import json
    import ui_common as ui
    colors = ui.theme_colors()
    spec = json.dumps(ui.build_price_chart(s.window(DAILY, "1Y"), "candle").to_dict())
    assert '"rule"' in spec and '"bar"' in spec and colors["red"] in spec and colors["blue"] in spec  # 오르면 빨강, 내리면 파랑
    assert '"type": "ordinal"' in spec  # 순서 축: 주말·휴장일 빈칸 없음
    assert '"zoom"' not in spec and '"bind"' not in spec  # 확대·끌기 없음
    line = json.dumps(ui.build_price_chart(s.window(DAILY, "1Y"), "line").to_dict())
    assert '"line"' in line and '"area"' in line


def test_chart_three_date_ticks_avg_line_and_split_flag():
    import json
    import ui_common as ui
    raw, cut = split_series()
    ev = s.detect_splits(raw)
    spec = json.dumps(ui.build_price_chart(s.window(s.adjust(raw, ev), "3M", "D"), "candle", 52000, ev).to_dict(),
                      ensure_ascii=False)
    assert "1:5 분할" in spec and "내 평균 단가 52,000" in spec
    spec = ui.build_price_chart(s.window(DAILY, "1Y"), "candle").to_dict()
    axes = [l["encoding"]["x"]["axis"] for l in spec["layer"] if "encoding" in l and "x" in l["encoding"]
            and isinstance(l["encoding"]["x"], dict) and l["encoding"]["x"].get("axis")]
    assert axes and all(len(a["values"]) == 3 for a in axes)  # 날짜 눈금 3개


def _chart_app():
    from datetime import date
    import ui_common as ui
    from engine import price_history as ph
    bars = ph.demo_bars("HB01", 62200, date(2026, 11, 13))
    ui.render_stock_chart("HB01", bars, date(2026, 11, 16), avg_price=54850, avg_qty="14주")


def test_render_stock_chart_in_streamlit():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_chart_app).run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "1년 동안" in text and "1년 한눈에 보기" in text and "주봉 53개" in text and "내 평균 단가" in text
    at.segmented_control(key="chart-HB01-p-ctl").set_value("3M")
    at = at.run()
    assert "일봉" in " ".join(m.value for m in at.markdown)  # 기간을 바꾸면 그 기간의 기본 봉


def _states_app():
    from datetime import date
    import ui_common as ui
    from engine import price_history as ph
    ui.render_stock_chart("A", [], date(2026, 11, 16))
    bars = ph.demo_bars("HB01", 62200, date(2026, 11, 13))
    recent = [b for b in bars if b.d >= date(2023, 11, 20)]
    ui.render_stock_chart("B", recent, date(2026, 11, 16), backfill_pct=0.4, key_prefix="b")


def test_render_empty_and_backfill_states():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_states_app).run()
    assert not at.exception, at.exception
    assert any("시세를 아직 받지 못했어요" in i.value for i in at.info)
    assert "36개월 중 14개월 받았어요" in " ".join(m.value for m in at.markdown)
    assert "3Y" not in at.segmented_control(key="b-B-p-ctl").options


def _scenario_app():
    from datetime import date
    import ui_common as ui
    from engine import price_history as ph, store
    df = store.load_prices()["005930"]
    bars = ph.close_only_bars(list(zip(df["date"], df["close"])))
    ui.render_stock_chart("005930", bars, date(2026, 10, 2), close_only=True)


def test_scenario_close_only_is_line_without_candle_toggle():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_scenario_app).run()
    assert not at.exception, at.exception
    assert "종가만 있어 선 그래프로 봐요" in " ".join(m.value for m in at.markdown)
    assert not any("kind-ctl" in (c.key or "") for c in at.segmented_control)


def test_flag_off_keeps_old_sparkline(monkeypatch):
    import config
    from conftest import open_app
    monkeypatch.setattr(config, "CHART_V2", False)
    at = open_app("pages/1_가상_주식시장.py", query={"mock": "1"})
    next(b for b in at.button if b.label == "누리바이오 보기").click()
    at = at.run()
    text = " ".join(m.value for m in at.markdown)
    assert "오늘 급등" in text and "한눈에 보기" not in text
