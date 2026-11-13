"""9번 Skill Unlock: 연습 과정을 보고 다음 단계를 연다. LLM 호출 금지.

- 1단계 연습용 가상 시세 → 2단계 실제 시세 연습 → 3단계 실전 준비 완료 (보호자 승인 요청 시안)
- 기준은 과정만 본다: 근거 기록, 비중, 보유 기간, 돌아보기·규칙, 미션. 수익률·이익·손실은 넣지 않는다.
- 학생 화면에는 조건마다 '채웠어요 / 연습 중'과 행동 사실만 보여 준다. 점수는 없다.
- 3단계도 실제 주문과 연결하지 않는다. 신청 기록만 남기고 보호자 화면에 시안으로 보여 준다.
- 한 번 연 단계는 unlocks.csv에 남아 다시 잠기지 않는다.
"""

from datetime import date

from engine import detect, portfolio

STAGES = {1: "연습용 가상 시세", 2: "실제 시세 연습", 3: "실전 준비 완료"}
OPENS = {1: "연습용 가상 종목으로 사고팔며 투자 일지 쓰기",
         2: "실제 종목의 진짜 종가로 연습하기 (돈은 여전히 가상)",
         3: "보호자에게 실전 소수점 투자 신청 보내기 (시안 · 실제 주문은 연결하지 않아요)"}

# 투자 탭 동의 기반 2트랙(config.INVEST_CONSENT_TRACK)에서는 레벨이 투자 진입·한도·범위를 정하지 않는다.
# 단계 자체(연습 과정 기록)는 그대로 두고, 이름과 설명에서 투자 해금 문구만 뺀다 (INVEST_TAB_SPEC.md 5장).
CONSENT_STAGES = {1: "첫 연습", 2: "습관 다지기", 3: "스스로 점검"}
CONSENT_OPENS = {1: "가상으로 사고팔며 투자 일지 쓰기",
                 2: "근거 기록 · 비중 · 돌아보기 습관이 자리 잡았어요",
                 3: "미션 · 보유 기간 · 근거 습관까지 스스로 점검했어요"}


def names():
    """화면에 쓰는 단계 이름 (동의 2트랙이면 투자 해금 문구가 없는 이름)."""
    import config
    return CONSENT_STAGES if config.INVEST_CONSENT_TRACK else STAGES


def opens():
    import config
    return CONSENT_OPENS if config.INVEST_CONSENT_TRACK else OPENS


RECENT_BUYS = 3        # 최근 매수 몇 번을 볼지
MIN_HOLD_DAYS = 5      # 매수하고 이 날수(달력 기준) 안에 팔면 '급하게 판 것'
MIN_MISSION_WEEKS = 2  # 미션을 해낸 주가 이만큼 있어야 3단계


def condition(title, met, fact):
    return {"title": title, "met": bool(met), "fact": fact}


def reason_condition(detections):
    recent = detections[-RECENT_BUYS:]
    written = sum(d["journal_chars"] >= detect.MIN_JOURNAL_CHARS for d in recent)
    fact = (f"최근 매수 {len(recent)}번 중 {written}번 이유를 적었어요." if recent
            else "아직 매수가 없어요.")
    return condition(f"최근 매수 {RECENT_BUYS}번 모두 이유를 {detect.MIN_JOURNAL_CHARS}자 이상 적기",
                     len(recent) == RECENT_BUYS and written == RECENT_BUYS, fact)


def max_weight_pct(trades, prices, student):
    """지금(마지막 시세일) 가장 큰 종목 비중 (총자산 대비 %)."""
    student_id = student["student_id"]
    held = portfolio.holdings(trades, student_id)
    cash = portfolio.cash_balance(student["virtual_cash"], trades, student_id)
    rows = portfolio.position_rows(held, cash, portfolio.close_on(prices, portfolio.latest_date(prices)))
    return max((r["weight_pct"] for r in rows), default=None)


def weight_condition(trades, prices, student):
    weight = max_weight_pct(trades, prices, student)
    fact = "지금 가진 종목이 없어요." if weight is None else f"지금 가장 큰 종목 비중은 {weight:.0f}%예요."
    return condition(f"가장 큰 종목 비중을 {detect.CONCENTRATION_PCT}% 아래로 두기",
                     weight is None or weight < detect.CONCENTRATION_PCT, fact)


def review_condition(detections, lessons, rules, student_id):
    """돌아볼 매수가 있으면 1번 이상 돌아보고 나만의 규칙 1개. 돌아볼 매수가 없으면 채운 것으로 본다."""
    title = "실수에서 배우기로 돌아보고 나만의 규칙 1개 정하기"
    if not detect.mistakes(detections):
        return condition(title, True, "돌아볼 매수가 없었어요.")
    reviewed = lessons[lessons["student_id"] == student_id]["trade_id"].nunique()
    made = int((rules["student_id"] == student_id).sum())
    return condition(title, reviewed >= 1 and made >= 1, f"돌아본 매수 {reviewed}개, 나만의 규칙 {made}개예요.")


def mission_condition(missions, student_id):
    done = missions[(missions["student_id"] == student_id) & (missions["done"] == "TRUE")]
    weeks = done["week_start"].nunique()
    return condition(f"미션을 해낸 주 {MIN_MISSION_WEEKS}주 이상", weeks >= MIN_MISSION_WEEKS,
                     f"미션을 해낸 주가 {weeks}주예요.")


def quick_sells(trades, student_id):
    """(판 횟수, 매수하고 MIN_HOLD_DAYS일 안에 판 횟수). 같은 종목의 가장 최근 매수일과 비교한다."""
    mine = trades[trades["student_id"] == student_id].sort_values("date", kind="stable")
    last_buy, sells, quick = {}, 0, 0
    for t in mine.itertuples():
        if t.side == "BUY":
            last_buy[t.ticker] = t.date
        elif t.side == "SELL":
            sells += 1
            bought = last_buy.get(t.ticker)
            if bought and (date.fromisoformat(t.date) - date.fromisoformat(bought)).days < MIN_HOLD_DAYS:
                quick += 1
    return sells, quick


def hold_condition(all_trades, student_id):
    """all_trades: 시나리오·실제 시세 거래 표 목록 (두 연습 모두 본다)."""
    counts = [quick_sells(t, student_id) for t in all_trades]
    sells, quick = sum(c[0] for c in counts), sum(c[1] for c in counts)
    fact = "아직 판 적이 없어요." if not sells else f"판 {sells}번 중 {MIN_HOLD_DAYS}일 안에 판 건 {quick}번이에요."
    return condition(f"매수하고 {MIN_HOLD_DAYS}일 안에 팔지 않기", quick == 0, fact)


def real_practice_condition(real_trades, student_id):
    buys = real_trades[(real_trades["student_id"] == student_id) & (real_trades["side"] == "BUY")]
    written = sum(detect.journal_chars(j) >= detect.MIN_JOURNAL_CHARS for j in buys["journal"])
    return condition("실제 시세 연습에서 이유를 적고 매수 1번 이상", written >= 1,
                     f"실제 시세로 이유를 적고 산 매수가 {written}번이에요.")


def conditions(student, trades, prices, real_trades, lessons, rules, missions):
    """{2: [조건...], 3: [조건...]}. trades·prices는 연습용 가상 시세(시나리오) 기준."""
    student_id = student["student_id"]
    detections = detect.detect(trades, prices, student)
    return {
        2: [reason_condition(detections), weight_condition(trades, prices, student),
            review_condition(detections, lessons, rules, student_id)],
        3: [mission_condition(missions, student_id), hold_condition([trades, real_trades], student_id),
            real_practice_condition(real_trades, student_id)],
    }


def stage(unlocks, student_id):
    """지금 열린 가장 높은 단계 (기록이 없으면 1)."""
    mine = unlocks[unlocks["student_id"] == student_id]["stage"]
    return max((int(s) for s in mine), default=1)


def can_open(current, target, conds):
    """바로 다음 단계이고 조건을 모두 채웠으면 열 수 있다."""
    return target == current + 1 and all(c["met"] for c in conds[target])
