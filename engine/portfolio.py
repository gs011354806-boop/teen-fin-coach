"""가상투자 보유 현황 계산. LLM 호출 금지."""


def latest_date(prices):
    """모든 종목에 가격이 있는 가장 최근 거래일."""
    return min(df["date"].iloc[-1] for df in prices.values())


def close_on(prices, day):
    """{종목코드: day의 종가}"""
    return {ticker: int(df.loc[df["date"] == day, "close"].iloc[0])
            for ticker, df in prices.items()}


def day_change_pct(price_df, day):
    """day의 종가가 직전 거래일보다 몇 % 변했는지. 직전 거래일이 없으면 None."""
    rows = price_df[price_df["date"] <= day]
    if len(rows) < 2:
        return None
    prev, cur = int(rows["close"].iloc[-2]), int(rows["close"].iloc[-1])
    return (cur / prev - 1) * 100


def holdings(trades, student_id):
    """{종목코드: 보유 수량} (수량이 0인 종목은 뺀다)"""
    result = {}
    for t in trades[trades["student_id"] == student_id].itertuples():
        sign = 1 if t.side == "BUY" else -1
        result[t.ticker] = result.get(t.ticker, 0) + sign * int(t.qty)
    return {ticker: qty for ticker, qty in result.items() if qty > 0}


def cash_balance(virtual_cash, trades, student_id):
    """가상 투자금에서 매수 금액을 빼고 매도 금액을 더한 남은 현금."""
    cash = virtual_cash
    for t in trades[trades["student_id"] == student_id].itertuples():
        sign = 1 if t.side == "BUY" else -1
        cash -= sign * int(t.qty) * int(t.price)
    return cash


def position_rows(held, cash, closes):
    """보유 종목별 평가금액과 비중. 비중은 총자산(주식 + 현금) 대비 %."""
    values = {ticker: qty * closes[ticker] for ticker, qty in held.items()}
    total = sum(values.values()) + cash
    rows = [{"ticker": ticker, "qty": held[ticker], "close": closes[ticker],
             "value": value, "weight_pct": value / total * 100}
            for ticker, value in values.items()]
    return sorted(rows, key=lambda r: r["value"], reverse=True)


def check_order(side, qty, price, cash, held_qty):
    """주문할 수 없으면 이유(문장)를, 할 수 있으면 None을 돌려준다."""
    if qty < 1:
        return "수량은 1주 이상이어야 해요."
    if side == "BUY" and qty * price > cash:
        return f"가상 현금이 부족해요. 지금은 최대 {cash // price}주까지 살 수 있어요."
    if side == "SELL" and qty > held_qty:
        return f"가진 수량보다 많이 팔 수 없어요. 지금 {held_qty}주를 갖고 있어요."
    return None
