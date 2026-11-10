"""28번 미션 탭 · 투자 미션 (Replay → Simulation → 미션). LLM 호출 금지.

⚠️ 만들어만 두고 앱에서는 실행하지 않는다 (config.INVEST_MISSION_ENABLED = False).
   명세가 요구하는 모의투자 주문 로그(viewed_info 포함)와 과거 시세 데이터가 아직 없다.
   데이터가 생기면 아래 함수에 그대로 넘기면 된다.

입력 형식 (명세 5장)
- orders: DataFrame [order_id, user_id, datetime, symbol, side(BUY/SELL), qty, price, viewed_info(bool), memo]
- prices: {symbol: [(date, close), ...]} 날짜순

명세 6-3(트리거) · 6-4(과거 시세 재생) · 6-6(Skill Unlock Lv.3 조건)
⚠️ 6-4는 대안을 수익률로 비교한다. CLAUDE.md 규칙 4(수익률로 평가하지 않는다)와 부딪히므로,
   켜기 전에 화면 표시 방식을 정해야 한다 (docs/MISSION_TAB.md).
"""

from datetime import date, timedelta

JUMP_PCT = 10          # FOMO_BUY: 전일 대비 +10% 이상
CONCENTRATION_PCT = 50
REVENGE_DAYS = 3
DAY_TRADES_MAX = 5
REPLAY_DAYS = 3        # 매수일 ~ +N일
WATCH_DAYS = 3         # '관찰 후 매수'는 +k일 종가
ANSWER_CONCEPTS = {    # ⑤ "왜 이 종목을 샀나요?" → 1분 레슨 개념 (content/concepts id)
    "fomo": ("계속 오를 것 같아서", "FOMO"),
    "peer": ("친구가 추천해서", "INVESTMENT_JOURNAL"),
    "news": ("기업 소식을 봐서", "INVESTMENT_JOURNAL"),   # '정보와 가격 반영' 카드가 아직 없어 판단근거 카드로
    "curious": ("그냥 궁금해서", "DIVERSIFICATION"),       # '분할매수' 카드가 아직 없어 분산투자 카드로
}
UNLOCK_LV3 = {"weeks": 8, "journal": 4, "max_weight": 50, "impulse": 1}


def _closes(prices, symbol):
    return [c for _, c in prices[symbol]]


def _index_on(prices, symbol, day):
    return next(i for i, (d, _) in enumerate(prices[symbol]) if d == day)


# ---------- 6-3 트리거 ----------

def fomo_buys(orders, prices):
    """전일 대비 +10% 이상 오른 날(24시간 안) 매수한 주문."""
    found = []
    for o in orders[orders["side"] == "BUY"].itertuples():
        day = str(o.datetime)[:10]
        i = _index_on(prices, o.symbol, day)
        if i == 0:
            continue
        prev, close = prices[o.symbol][i - 1][1], prices[o.symbol][i][1]
        jump = (close - prev) / prev * 100
        if jump >= JUMP_PCT:
            found.append({"order_id": o.order_id, "symbol": o.symbol, "day": day, "jump_pct": round(jump)})
    return found


def max_weight_pct(orders, cash):
    """가장 큰 종목에 넣은 돈이 처음 가상자산(cash)의 몇 %인지 (매수 − 매도 금액 기준)."""
    held = {}
    for o in orders.itertuples():
        sign = 1 if o.side == "BUY" else -1
        held[o.symbol] = held.get(o.symbol, 0) + sign * o.qty * o.price
    return round(max(held.values(), default=0) / cash * 100) if cash else 0


def no_research(orders):
    """매수 전 정보를 안 봤거나 근거(memo)를 안 쓴 매수."""
    buys = orders[orders["side"] == "BUY"]
    return [o.order_id for o in buys.itertuples() if not o.viewed_info or not str(o.memo).strip()]


def revenge_trades(orders, prices):
    """손실 매도 후 3일 안에 같은 종목 재매수, 또는 하루 5회 이상 매매."""
    hits = []
    rows = orders.sort_values("datetime")
    buys_cost = {}
    for o in rows.itertuples():
        if o.side == "BUY":
            buys_cost.setdefault(o.symbol, o.price)
        elif o.price < buys_cost.get(o.symbol, o.price):
            sold = date.fromisoformat(str(o.datetime)[:10])
            again = rows[(rows["side"] == "BUY") & (rows["symbol"] == o.symbol)
                         & (rows["datetime"].astype(str).str[:10] > sold.isoformat())
                         & (rows["datetime"].astype(str).str[:10] <= (sold + timedelta(days=REVENGE_DAYS)).isoformat())]
            hits += list(again["order_id"])
    per_day = rows["datetime"].astype(str).str[:10].value_counts()
    for day in per_day[per_day >= DAY_TRADES_MAX].index:
        hits += list(rows[rows["datetime"].astype(str).str[:10] == day]["order_id"])
    return sorted(set(hits))


def triggers(orders, prices, cash):
    """걸린 트리거 코드 목록 (명세 6-3)."""
    found = []
    if fomo_buys(orders, prices):
        found.append("FOMO_BUY")
    if max_weight_pct(orders, cash) >= CONCENTRATION_PCT:
        found.append("CONCENTRATION")
    if no_research(orders):
        found.append("NO_RESEARCH")
    if revenge_trades(orders, prices):
        found.append("REVENGE_TRADE")
    return found


# ---------- 6-4 과거 시세 재생 ----------

def _ret(buy, sell):
    return (sell - buy) / buy * 100


def replay_compare(prices, symbol, buy_day, peers=None, days=REPLAY_DAYS, watch=WATCH_DAYS):
    """같은 투자금·같은 기간(매수일 ~ +days일)을 재생한 N일 후 수익률(%).
    peers: 분산 대안에 쓸 다른 2종목 (없으면 그 대안은 뺀다)."""
    closes = _closes(prices, symbol)
    i = _index_on(prices, symbol, buy_day)
    end = min(i + days, len(closes) - 1)
    result = [{"key": "mine", "label": "급등 직후 전액 매수", "return_pct": round(_ret(closes[i], closes[end])),
               "mine": True}]
    w = min(i + watch, end)
    result.append({"key": "watch", "label": f"{watch}일 지켜본 뒤 매수",
                   "return_pct": round(_ret(closes[w], closes[end]))})
    split = [closes[min(i + k, end)] for k in range(3)]
    result.append({"key": "split", "label": "세 번 나눠 매수",
                   "return_pct": round(sum(_ret(p, closes[end]) for p in split) / 3)})
    if peers:
        rets = [_ret(closes[i], closes[end])]
        for p in peers:
            pc = _closes(prices, p)
            rets.append(_ret(pc[i], pc[min(end, len(pc) - 1)]))
        result.append({"key": "spread", "label": "3종목에 나눠 투자", "return_pct": round(sum(rets) / len(rets))})
    return result


# ---------- 6-6 Skill Unlock Lv.3 ----------

def skill_unlock(weeks, journals, max_weight, impulse):
    """Lv.3(Prove) 조건 4칸. met = 기준 충족."""
    return [
        {"key": "weeks", "label": "참여", "current": weeks, "target": UNLOCK_LV3["weeks"],
         "met": weeks >= UNLOCK_LV3["weeks"], "unit": "주"},
        {"key": "journal", "label": "투자일지", "current": journals, "target": UNLOCK_LV3["journal"],
         "met": journals >= UNLOCK_LV3["journal"], "unit": "회"},
        {"key": "maxWeight", "label": "최대 비중", "current": max_weight, "target": UNLOCK_LV3["max_weight"],
         "met": max_weight <= UNLOCK_LV3["max_weight"], "unit": "%"},
        {"key": "impulse", "label": "충동거래", "current": impulse, "target": UNLOCK_LV3["impulse"],
         "met": impulse <= UNLOCK_LV3["impulse"], "unit": "회"},
    ]


MISSION_OPTIONS = [  # ⑥ 다음 주 미션 (보상은 수행률 × 포인트)
    {"id": "split", "title": "다음 매수는 세 번 나눠 사기", "subtitle": "한 번에 가상자산의 30% 이하로",
     "reward_points": 200},
    {"id": "check", "title": "매수 전 체크리스트 3개 확인", "subtitle": "공시 · 뉴스 · 최근 5일 등락",
     "reward_points": 200},
]
