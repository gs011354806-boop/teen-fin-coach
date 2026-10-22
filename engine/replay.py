"""주간 지표와 미션 수행 결과 계산. LLM 호출 금지.

데모는 data/의 4주 기록을 한 주씩 재생한다. 주는 월요일에 시작한다.
"""

from datetime import date, timedelta

from engine import envelope, portfolio
from engine.detect import MIN_JOURNAL_CHARS, journal_chars


def week_starts(allowance):
    """용돈 기록이 있는 기간의 월요일 목록."""
    first = date.fromisoformat(allowance["date"].min())
    last = date.fromisoformat(allowance["date"].max())
    day = first - timedelta(days=first.weekday())
    starts = []
    while day <= last:
        starts.append(day.isoformat())
        day += timedelta(days=7)
    return starts


def week_end(week_start):
    return (date.fromisoformat(week_start) + timedelta(days=6)).isoformat()


def next_week(week_start):
    return (date.fromisoformat(week_start) + timedelta(days=7)).isoformat()


def week_label(week_start, starts):
    start = date.fromisoformat(week_start)
    end = start + timedelta(days=6)
    return f"{starts.index(week_start) + 1}주차 ({start.month}/{start.day}~{end.month}/{end.day})"


def week_metrics(student, trades, allowance, prices, week_start):
    """한 주의 행동 지표. 수익률은 계산하지 않는다."""
    student_id = student["student_id"]
    end = week_end(week_start)

    mine = trades[trades["student_id"] == student_id]
    in_week = (mine["date"] >= week_start) & (mine["date"] <= end)
    buys = mine[in_week & (mine["side"] == "BUY")]
    no_reason = sum(journal_chars(j) < MIN_JOURNAL_CHARS for j in buys["journal"])

    upto = mine[mine["date"] <= end]
    held = portfolio.holdings(upto, student_id)
    cash = portfolio.cash_balance(student["virtual_cash"], upto, student_id)
    any_prices = next(iter(prices.values()))
    last_day = any_prices.loc[any_prices["date"] <= end, "date"].max()
    rows = portfolio.position_rows(held, cash, portfolio.close_on(prices, last_day))

    saves = allowance[(allowance["student_id"] == student_id) & (allowance["envelope"] == "SAVE")]
    week_saves = saves[(saves["date"] >= week_start) & (saves["date"] <= end)]["amount"]
    deposit = int(week_saves[week_saves > 0].sum())
    withdraw = int(-week_saves[week_saves < 0].sum())

    spent = envelope.spending(allowance, student_id)
    spent = spent[(spent["date"] >= week_start) & (spent["date"] <= end)]
    spend_total = int(-spent["amount"].sum())
    wants = spent[spent["category"].isin(envelope.IMPULSE_CATEGORIES)]
    impulse_spend = int(-wants["amount"].sum())

    return {
        "week_start": week_start,
        "buy_count": len(buys),
        "no_reason_count": int(no_reason),
        "no_reason_buy_pct": None if len(buys) == 0 else no_reason / len(buys) * 100,
        "max_weight_pct": max((r["weight_pct"] for r in rows), default=0.0),
        "save_deposit": deposit,
        "save_withdraw": withdraw,
        "withdraw_count": int((week_saves < 0).sum()),
        "save_net": deposit - withdraw,
        "save_balance": int(saves[saves["date"] <= end]["amount"].sum()),
        # 19번 지출 코칭: 쓰기 봉투 지출 중 편의점·카페·디저트 (금액 기준)
        "spend_total": spend_total,
        "impulse_spend": impulse_spend,
        "impulse_count": len(wants),
        "impulse_share_pct": None if spend_total == 0 else impulse_spend / spend_total * 100,
    }


def mission_result(target_metric, metrics):
    """미션 지표의 이번 주 값. 매수가 없으면 근거 없는 매수 비율은 0으로 본다."""
    if target_metric == "no_reason_buy_pct":
        return metrics["no_reason_buy_pct"] or 0.0
    return float(metrics[target_metric])


def is_done(target_metric, target_value, result_value):
    """모으기는 목표 이상, 나머지(비중·근거 없는 매수 비율·편의점·카페 지출)는 목표 이하면 수행."""
    if target_metric == "save_net":
        return result_value >= target_value
    return result_value <= target_value


def result_sentence(target_metric, metrics):
    """화면과 LLM에 줄 결과 문장."""
    if target_metric == "max_weight_pct":
        return f"주말 기준 가장 큰 종목 비중은 총자산의 {metrics['max_weight_pct']:.0f}%였어요."
    if target_metric == "no_reason_buy_pct":
        if metrics["buy_count"] == 0:
            return "이번 주에는 매수가 없었어요."
        return (f"매수 {metrics['buy_count']}번 중 근거가 10자 미만인 매수는 "
                f"{metrics['no_reason_count']}번이었어요.")
    if target_metric == "impulse_spend":
        return (f"편의점·카페·디저트에 {metrics['impulse_count']}번, "
                f"{metrics['impulse_spend']:,}원을 썼어요.")
    return (f"모으기 봉투에 {metrics['save_deposit']:,}원을 넣고 {metrics['save_withdraw']:,}원을 꺼내 "
            f"{metrics['save_net']:,}원이 남았어요.")


def grade_missions(missions, metrics):
    """그 주 미션들의 결과값과 수행 여부. missions: target_metric, target_value 컬럼이 있는 표."""
    results = []
    for m in missions.itertuples():
        value = mission_result(m.target_metric, metrics)
        results.append({"mission_id": m.mission_id, "result_value": round(value, 1),
                        "done": is_done(m.target_metric, float(m.target_value), value),
                        "result": result_sentence(m.target_metric, metrics)})
    return results
