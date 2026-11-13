"""투자 탭 화면 값 만들기 (연습 홈 · 연습 리포트 · 실전 홈). LLM 호출 금지.

연습 모드는 기존 가상 계좌(trades.csv / real_trades.csv)를 그대로 읽는다. 시안 재현(?mock)은 data/invest/demo.json.
"""

import math
from datetime import date

from engine import detect, invest_track as it, portfolio, unlock

SURGE_CHIP_PCT = detect.SURGE_PCT


def _row(symbol, name, sub, change, kind):
    return {"symbol": symbol, "name": name, "sub": sub, "changePct": change, "kind": kind,
            "surge": change is not None and change >= SURGE_CHIP_PCT}


def practice_home(student, market, provider, state):
    """기존 가상 계좌 → 연습 홈 카드와 보유·관심 목록."""
    sid = student["student_id"]
    prices, trades, names = market["prices"], market["trades"], market["names"]
    closes = portfolio.close_on(prices, provider.as_of)
    held = portfolio.holdings(trades, sid)
    start = market["student"]["virtual_cash"]
    cash = portfolio.cash_balance(start, trades, sid)
    positions = portfolio.position_rows(held, cash, closes)
    value = cash + sum(p["value"] for p in positions)
    rows = [_row(p["ticker"], names[p["ticker"]], f"{p['qty']}주 · {p['value']:,}원",
                 provider.quote(p["ticker"])["changePct"], "hold") for p in positions]
    for w in state["watch"]:
        if w["account"] == "PRACTICE" and w["symbol"] not in held and w["symbol"] in names:
            rows.append(_row(w["symbol"], names[w["symbol"]], "관심 종목",
                             provider.quote(w["symbol"])["changePct"], "watch"))
    top = positions[0] if positions else None
    return {"value": value, "start": start, "returnPct": round((value / start - 1) * 100, 1),
            "segments": [round(p["weight_pct"]) for p in positions[:4]],
            "investPct": round((value - cash) / value * 100) if value else 0,
            "maxWeight": None if not top else (round(top["weight_pct"]), names[top["ticker"]]),
            "rows": rows, "names": names}


def practice_home_mock(demo, state):
    p = demo["practice"]
    names = {s: m["name"] for s, m in demo["instruments"].items()}
    rows = [_row(h["symbol"], names[h["symbol"]], f"{h['qty']}주 · {h['value']:,}원", h["changePct"], "hold")
            for h in p["holdings"] if h["qty"]]
    for w in state["watch"]:
        if w["account"] == "PRACTICE":
            rows.append(_row(w["symbol"], names[w["symbol"]], "관심 종목",
                             demo["quotes"][w["symbol"]]["changePct"], "watch"))
    a = p["account"]
    return {"value": a["value"], "start": a["start"], "returnPct": a["returnPct"],
            "segments": [h["weightPct"] for h in p["holdings"]], "investPct": a["investPct"],
            "maxWeight": (p["maxWeightPct"], p["maxWeightName"]), "rows": rows, "names": names}


def weeks_between(first, last):
    return max(1, math.ceil(((date.fromisoformat(last) - date.fromisoformat(first)).days + 1) / 7))


def practice_report(student, trades, prices, state, questions, news_quiz):
    """동의 요청에 붙일 연습 리포트 (기존 데이터 그대로). 점수 숫자 없이 '잘하는 중 / 연습 중'만."""
    sid = student["student_id"]
    mine = trades[trades["student_id"] == sid]
    today = portfolio.latest_date(prices)
    weeks = weeks_between(min(mine["date"]), today) if len(mine) else 0
    journals = int(sum(bool(j.strip()) for j in mine["journal"]))
    checks = [c for c in state["checklists"] if c.get("side", "BUY") == "BUY"]
    rate = None if not checks else sum(c["news"] and c["chart"] and c["journal"] for c in checks) / len(checks)

    detections = detect.detect(trades, prices, student)
    weight_now = unlock.max_weight_pct(trades, prices, student)
    asked = int((questions["student_id"] == sid).sum()) + int((news_quiz["student_id"] == sid).sum())
    reasons = unlock.reason_condition(detections)["met"]
    sells, quick = unlock.quick_sells(trades, sid)
    skills = {"knowledge": asked >= 2,
              "risk": (weight_now is None or weight_now < detect.CONCENTRATION_PCT) and quick == 0,
              "decision": reasons}
    highlights = []
    if detections and weight_now is not None:
        first = max(d["weight_pct"] for d in detections[:1])
        if first != round(weight_now):
            word = "나아졌어요" if weight_now < first else "커졌어요"
            highlights.append(f"최대 비중 {first}% → {weight_now:.0f}%로 {word}")
    written = sum(d["journal_chars"] >= detect.MIN_JOURNAL_CHARS for d in detections)
    if detections:
        highlights.append(f"매수 {len(detections)}번 중 {written}번 이유를 적었어요")
    return it.practice_report(weeks, journals, rate, skills, highlights)


def fomo_memory(trades, prices, student, days=3):
    """연습 모드에서 급등 직후 산 기록 한 줄 재료: 가장 최근 급등 추격 매수의 days거래일 뒤 등락. 없으면 None."""
    for d in reversed(detect.detect(trades, prices, student)):
        if detect.SURGE not in d["patterns"]:
            continue
        df = prices[d["ticker"]]
        after = df[df["date"] >= d["date"]]
        if len(after) <= days:
            continue
        buy, later = int(after["close"].iloc[0]), int(after["close"].iloc[days])
        return {"days": days, "pct": round((later / buy - 1) * 100)}
    return None


def fomo_line(memory, change_pct):
    head = f"잠깐! 오늘 {change_pct:+.1f}% 오른 종목이에요"
    if memory:
        body = (f"연습 모드에서 급등 직후 샀을 때, {memory['days']}일 뒤 {memory['pct']:+d}%였던 적이 있어요. "
                "이번엔 어떤 근거로 사나요?")
    else:
        body = "급등한 날은 가격이 크게 흔들릴 수 있어요. 이번엔 어떤 근거로 사나요?"
    return head, body


def real_home(state, provider, today):
    """실전 홈: 계좌 요약, 한도 사용, 보유, 이번 달 기록, 지켜보기 결과."""
    real, g = state["real"], state["guardrails"]
    names = provider.names()
    prices = {s: provider.quote(s)["price"] for s in real["holdings"] if s in names}
    summary = it.real_summary(real, prices)
    values = it.real_values(real, prices)
    month = it.month_key(today)
    usage = it.month_usage(real["orders"], month)
    rows = []
    for s, v in sorted(values.items(), key=lambda kv: -kv[1]):
        q = provider.quote(s)
        rows.append(_row(s, names[s], f"{it.qty_label(real['holdings'][s]['qty'])} · {v:,}원 (소수점)",
                         q["changePct"], "hold"))
    record = it.monthly_record(real, state["watch"], month)
    record["maxWeightPct"] = it.max_weight_pct(values)
    waits = []
    for w in state["watch"]:
        if w["account"] == "REAL" and w["reason"] == "FOMO_WAIT" and w["symbol"] in names:
            result = it.wait_result(w, provider.history(w["symbol"], 60))
            if result:
                waits.append({"name": names[w["symbol"]], **result})
    return {"summary": summary, "usage": usage, "guardrails": g, "rows": rows, "record": record,
            "waits": waits, "names": names}
