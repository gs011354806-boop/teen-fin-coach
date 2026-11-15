"""행동 기반 포인트·캐릭터·가상 쿠폰 계산. LLM 호출 금지.

- 포인트는 행동(미션 수행, 근거 있는 일지, 저축 목표 달성, 게임 1분 복습, 주간 뉴스 퀴즈)으로만 받는다. 게임 코인과는 연결하지 않는다. 수익률·지출 금액과 연결하지 않는다.
- 받은 포인트는 기록 파일에서 매번 다시 계산한다 (중복 지급 없음). 쓴 포인트만 point_spend.csv에 저장한다.
- 캐릭터는 먹이로만 자라고, 줄어들거나 아프지 않는다.
"""

from engine.detect import MIN_JOURNAL_CHARS, journal_chars
from engine.replay import week_end

MISSION_POINTS = 100        # 미션 1개 수행 (모으기 미션 = 주간 저축 목표 달성 포함)
JOURNAL_POINTS = 20         # 근거 있는 일지 1건 (공백 제외 10자 이상)
GOAL_BONUS_POINTS = 300     # 최종 저축 목표 달성 1회. 하루 상한에서 뺀다
REVIEW_POINTS = 30          # 21번 게임 1분 복습을 모두 맞힘 (같은 날 같은 개념은 1번만)
NEWS_POINTS = 50            # 22번 이번 주 금융 뉴스 퀴즈를 모두 맞힘 (주마다 1번)
SPEND_QUIZ_POINTS = 30      # 23-1번 쓰기 봉투 내 소비 퀴즈 5문제를 모두 맞힘 (하루 1번)
DAILY_CAP = 200             # 미션·일지·복습 포인트의 하루 적립 상한

FEED_COST = 50
STAGES = [("알", 0), ("아기", 4), ("청소년", 10), ("어른", 20)]  # (이름, 필요한 누적 먹이 수)

# 특정 회사 로고·상표는 쓰지 않는다 (데모용 가상 쿠폰). tone은 style.css의 카드 색 이름
COUPONS = [
    {"item": "편의점 1,000원권", "points": 500, "shop": "편의점", "icon": "🏪", "face": 1000,
     "tone": "violet-blue"},
    {"item": "편의점 3,000원권", "points": 1400, "shop": "편의점", "icon": "🏪", "face": 3000,
     "tone": "yellow-orange"},
    {"item": "문화상품권 5,000원권", "points": 2300, "shop": "문화상품권", "icon": "🎬", "face": 5000,
     "tone": "green-blue"},
]
COUPON_VALID_DAYS = 30  # 데모 화면에 보여 줄 가상 유효기간
MAX_COUPON_QTY = 5


def earn_events(student, trades, missions, allowance, reviews=None, news_quiz=None, spend_quiz=None,
                mission_runs=None):
    """포인트를 받을 수 있는 행동 목록 (상한 적용 전). 날짜순.
    reviews: 게임 1분 복습 기록, news_quiz: 주간 뉴스 퀴즈 기록, spend_quiz: 쓰기 봉투 내 소비 퀴즈 기록,
    mission_runs: 28번 미션 탭 결과 (보상 × 수행률, 결과를 본 날)."""
    student_id = student["student_id"]
    events = []
    if news_quiz is not None:
        for r in news_quiz[news_quiz["student_id"] == student_id].drop_duplicates(["week"]).itertuples():
            events.append({"date": r.date, "kind": "뉴스 퀴즈", "capped": True,
                           "label": f"이번 주 금융 뉴스 퀴즈 ({r.week})", "points": NEWS_POINTS})
    if mission_runs is not None:
        done = mission_runs[(mission_runs["student_id"] == student_id) & (mission_runs["status"] == "completed")]
        for r in done.itertuples():
            points = int(float(r.points or 0))
            if points > 0:
                events.append({"date": r.finished_date, "kind": "미션 결과", "capped": True,
                               "label": f"미션 결과: {r.title}", "points": points})
    if spend_quiz is not None:
        for r in spend_quiz[spend_quiz["student_id"] == student_id].drop_duplicates(["date"]).itertuples():
            events.append({"date": r.date, "kind": "소비 퀴즈", "capped": True,
                           "label": "내 소비 퀴즈 5문제 모두 맞힘", "points": SPEND_QUIZ_POINTS})
    if reviews is not None:
        mine = reviews[reviews["student_id"] == student_id].drop_duplicates(["date", "concept"])
        for r in mine.itertuples():
            events.append({"date": r.date, "kind": "복습", "capped": True,
                           "label": f"1분 복습 완료: {REVIEW_LABELS.get(r.concept, r.concept)}",
                           "points": REVIEW_POINTS})
    for t in trades[trades["student_id"] == student_id].itertuples():
        if journal_chars(t.journal) >= MIN_JOURNAL_CHARS:
            events.append({"date": t.date, "kind": "일지", "capped": True,
                           "label": f"근거 있는 일지 ({t.trade_id})", "points": JOURNAL_POINTS})
    for m in missions[(missions["student_id"] == student_id) & (missions["done"] == "TRUE")].itertuples():
        events.append({"date": week_end(m.week_start), "kind": "미션", "capped": True,
                       "label": f"미션 수행: {m.text}", "points": MISSION_POINTS})
    events += daily_news_events(student_id)
    events += real_journal_events(student_id)
    goal_day = goal_reached_date(student, allowance)
    if goal_day:
        events.append({"date": goal_day, "kind": "저축 목표", "capped": False,
                       "label": f"저축 목표 달성: {student['saving_goal']['item']}",
                       "points": GOAL_BONUS_POINTS})
    return sorted(events, key=lambda e: e["date"])


def daily_news_events(student_id, answers=None, reviews=None):
    """오늘의 뉴스 퀴즈 정답 10P · 3문제 완주 +20P · 주말 복습 정답 10P (config, 하루 상한 안). 자동으로 기록 파일을 읽는다."""
    import config
    if not config.NEWS_DAILY:
        return []
    from engine import news_daily, store
    answers = store.load_news_answers() if answers is None else answers
    reviews = store.load_news_reviews() if reviews is None else reviews
    return news_daily.point_events(answers, reviews, student_id)


def real_journal_events(student_id, state=None):
    """실전 주문에 쓴 이유(투자일지)도 기존 규칙 그대로: 근거 10자 이상이면 20P (NEWS_MARKET_SPEC.md 8-4)."""
    import config
    if not config.NEWS_MARKET_FLAGS["realTrading"]:
        return []
    from engine import store
    state = store.load_invest(student_id) if state is None else state
    orders = ((state or {}).get("real") or {}).get("orders", [])
    return [{"date": o["date"], "kind": "일지", "capped": True, "label": f"근거 있는 실전 일지 ({o['id']})",
             "points": JOURNAL_POINTS} for o in orders if journal_chars(o.get("reason") or "") >= MIN_JOURNAL_CHARS]


def _concept_names():
    from engine.store import load_concepts
    return {cid: c["name_ko"] for cid, c in load_concepts().items()}


REVIEW_LABELS = _concept_names()


def goal_reached_date(student, allowance):
    """모으기 봉투 누적액이 처음 목표 금액 이상이 된 날. 아직이면 None."""
    saves = allowance[(allowance["student_id"] == student["student_id"])
                      & (allowance["envelope"] == "SAVE")]
    balance = 0
    for row in saves.sort_values("date", kind="stable").itertuples():
        balance += int(row.amount)
        if balance >= student["saving_goal"]["amount"]:
            return row.date
    return None


def apply_daily_cap(events):
    """상한이 있는 행동은 하루 DAILY_CAP까지만 준다. 넘친 만큼은 granted가 줄어든다."""
    used = {}
    result = []
    for e in events:
        granted = e["points"]
        if e["capped"]:
            granted = max(0, min(e["points"], DAILY_CAP - used.get(e["date"], 0)))
            used[e["date"]] = used.get(e["date"], 0) + granted
        result.append({**e, "granted": granted})
    return result


def balance(granted_events, spends, student_id):
    earned = sum(e["granted"] for e in granted_events)
    spent = sum(int(p) for p in spends.loc[spends["student_id"] == student_id, "points"])
    return earned - spent


def feed_count(spends, student_id):
    return int(((spends["student_id"] == student_id) & (spends["kind"] == "FEED")).sum())


def stage(feeds):
    """(지금 단계 이름, 다음 단계 이름 또는 None, 다음 단계까지 남은 먹이 수)."""
    index = max(i for i, (_, need) in enumerate(STAGES) if feeds >= need)
    if index == len(STAGES) - 1:
        return STAGES[index][0], None, 0
    name, need = STAGES[index + 1]
    return STAGES[index][0], name, need - feeds


def coupon_total(coupon, qty):
    return coupon["points"] * qty


def check_spend(points_needed, current_balance):
    """쓸 수 없으면 이유(문장)를, 쓸 수 있으면 None."""
    if points_needed > current_balance:
        return f"포인트가 {points_needed - current_balance}P 모자라요."
    return None


# ---------- 돼지 저금통 (2026-11-13, 시뮬레이션 · point/tintin_piggy/PIGGY_BANK_SPEC.md) ----------
# 알 키우기(먹이 주기)를 대신한다 (config.PIGGY_BANK). 단계 = 지금 포인트 잔액. 저장하지 않고 매번 계산한다.
# 구간 경계는 쿠폰 가격에 맞춘다: 단계가 오르는 순간 = 그 쿠폰을 바꿀 수 있게 되는 순간 (쓸까, 더 모을까).
# 쓰면 잔액에 맞는 단계로 내려가고, 0P면 분홍 돼지부터. 시간이 지나도 줄지 않는다 (벌칙 없음).
PIGGY_LEVELS = [
    {"no": 1, "key": "pink", "name": "분홍 돼지", "short": "분홍", "min": 0},
    {"no": 2, "key": "sky", "name": "하늘 돼지", "short": "하늘", "min": 500},
    {"no": 3, "key": "mint", "name": "민트 돼지", "short": "민트", "min": 1400},
    {"no": 4, "key": "purple", "name": "보라 돼지", "short": "보라", "min": 2300},
    {"no": 5, "key": "gold", "name": "황금 돼지", "short": "황금", "min": 3500},
]
GOLD_BADGE = "황금 돼지 배지"
GOLD_TITLE = "한 학기 꾸준히 모은 사람"  # 칭호 (현금성 혜택 아님)


def level_of(balance):
    lv = PIGGY_LEVELS[0]
    for level in PIGGY_LEVELS:
        if balance >= level["min"]:
            lv = level
    return lv


def next_level(level):
    return next((l for l in PIGGY_LEVELS if l["no"] == level["no"] + 1), None)


def progress_to_next(balance):
    """(지금 구간 안의 진행률 0~1, 다음 단계까지 남은 포인트 또는 None)."""
    cur = level_of(balance)
    nxt = next_level(cur)
    if nxt is None:
        return 1.0, None
    return (balance - cur["min"]) / (nxt["min"] - cur["min"]), nxt["min"] - balance


def level_range(level):
    nxt = next_level(level)
    return f"{level['min']:,}P 이상" if nxt is None else f"{level['min']:,}P ~ {nxt['min'] - 1:,}P"


def preview_redeem(balance, price):
    """쿠폰 교환 전 미리보기: 가능 여부, 교환 뒤 잔액, 단계 변화."""
    if balance < price:
        return {"ok": False, "short": price - balance}
    after = balance - price
    return {"ok": True, "after": after, "from": level_of(balance), "to": level_of(after), "reset": after == 0}


def preview_text(balance, price):
    """(종류, 문장). 종류: short(모으는 중) / reset / down / same."""
    p = preview_redeem(balance, price)
    if not p["ok"]:
        return "short", f"{p['short']:,}P 더 모으면 바꿀 수 있어요"
    if p["reset"]:
        return "reset", "바꾸면 0P · 분홍 돼지부터 다시 시작해요"
    if p["to"]["no"] < p["from"]["no"]:
        return "down", f"바꾸면 {p['from']['name']} → {p['to']['name']}로 내려가요"
    return "same", f"바꿔도 {p['to']['name']} 그대로예요 ({p['after']:,}P 남음)"


def level_up(before, after):
    """적립으로 단계가 올랐으면 새 단계, 아니면 None (내려간 경우에는 축하하지 않는다)."""
    old, new = level_of(before), level_of(after)
    return new if new["no"] > old["no"] else None


def gold_reached_date(granted_events, spends, student_id):
    """잔액이 처음 3,500P 이상이 된 날 (기록을 날짜순으로 다시 계산). 없으면 None.
    배지는 한 번 받으면 잔액이 줄어도 유지한다."""
    gold = PIGGY_LEVELS[-1]["min"]
    changes = [(e["date"], e["granted"]) for e in granted_events]
    mine = spends[spends["student_id"] == student_id]
    changes += [(d, -int(p)) for d, p in zip(mine["date"], mine["points"])]
    total = 0
    for day, delta in sorted(changes, key=lambda c: (c[0], c[1] < 0)):  # 같은 날은 적립 먼저
        total += delta
        if total >= gold:
            return day
    return None
