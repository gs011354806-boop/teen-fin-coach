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
    goal_day = goal_reached_date(student, allowance)
    if goal_day:
        events.append({"date": goal_day, "kind": "저축 목표", "capped": False,
                       "label": f"저축 목표 달성: {student['saving_goal']['item']}",
                       "points": GOAL_BONUS_POINTS})
    return sorted(events, key=lambda e: e["date"])


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
