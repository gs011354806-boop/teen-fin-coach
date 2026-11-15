"""투자 탭 동의 기반 2트랙 (2026-11-13, 시뮬레이션 · invest/tintin_invest_handoff/INVEST_TAB_SPEC.md). LLM 호출 금지.

- 연습 모드(PRACTICE): 누구나. 기존 가상주식시장 그대로 (가상 머니).
- 실전 모드(REAL): 부모 동의(ACTIVE) + 계좌 연결이 있을 때만. 레벨·경험치와 무관하다.
- 한도·범위는 부모 설정과 학생 요청(부모 결정)으로만 바뀐다. 자동으로 바꾸거나 제안하지 않는다.
- 모든 실전 주문은 validate_order()를 통과해야 한다. 미수·신용 경로는 없다.
- 계산만 한다. 저장은 store, 증권사·시세는 engine/broker.py 어댑터 뒤에 있다.
"""

import copy
import math
from datetime import date, datetime

PRACTICE, REAL = "PRACTICE", "REAL"
NONE, PENDING, ACTIVE, REJECTED, REVOKED = "NONE", "PENDING", "ACTIVE", "REJECTED", "REVOKED"
ETF_ONLY, ETF_LARGECAP, ALL = "ETF_ONLY", "ETF_LARGECAP", "ALL"

MONTHLY_LIMITS = (50_000, 100_000, 200_000)
PER_ORDER_RATIO = 0.5          # 1회 주문 상한 = 한 달 한도의 50%
FOMO_THRESHOLD_PCT = 10        # 하루 +10% 이상이면 급등주 확인 단계
MIN_REASON_CHARS = 10          # 급등주 근거는 10자 이상 (공백 포함 글자 수, 명세 6-3)
REQUEST_COOLDOWN_DAYS = 7      # 거절·철회 뒤 동의 재요청, 같은 내용 변경 요청은 7일에 한 번
AMOUNT_CHIPS = (5_000, 10_000, 20_000)

SCOPES = {
    ETF_ONLY: ("ETF만", "여러 회사를 묶은 상품부터 시작"),
    ETF_LARGECAP: ("ETF + 대형주", "시가총액 상위 종목까지"),
    ALL: ("전체 종목", "변동이 큰 종목도 포함"),
}

# 막힌 이유 → 학생에게 보여 줄 한 줄 (6-3). 투자 권유 문구는 쓰지 않는다.
BLOCK_MESSAGES = {
    "NO_CONSENT": "실전 주문은 부모님 동의가 있어야 할 수 있어요. 연습 모드에서는 지금도 해 볼 수 있어요.",
    "REVOKED": "부모님이 실전 모드를 멈췄어요. 가진 종목을 보거나 파는 것은 할 수 있어요.",
    "MARGIN_NOT_ALLOWED": "미수·신용거래는 항상 막혀 있어요. 가진 돈 안에서만 살 수 있어요.",
    "OVER_PER_ORDER": "한 번에 살 수 있는 금액을 넘었어요. 부모님이 정한 1회 상한 안에서 골라 주세요.",
    "OVER_MONTHLY": "이번 달 투자 한도를 넘었어요. 남은 한도 안에서 골라 주세요.",
    "OUT_OF_SCOPE": "이 종목은 부모님이 정한 범위 밖이에요. 연습 모드에서 먼저 해볼까요?",
    "NO_HOLDING": "가진 수량보다 많이 팔 수 없어요.",
    "FOMO_CHECK_REQUIRED": "오늘 많이 오른 종목이라 먼저 확인 단계를 거쳐야 해요.",
    "REASON_REQUIRED": f"사는 이유를 {MIN_REASON_CHARS}자 이상 써 주세요. 투자일지에 함께 남아요.",
    "INSUFFICIENT_CASH": "계좌에 있는 돈이 부족해요. 용돈 계좌의 투자 봉투를 확인해 주세요.",
    "INSUFFICIENT_SHARES": "가진 수량보다 많이 팔 수 없어요.",
    "QUOTE_STALE": "최신 시세를 아직 불러오지 못했어요. 지금은 주문할 수 없어요.",
    "MARKET_CLOSED": "지금은 장이 닫혀 있어요. 다음 장 시작 때 주문되도록 예약할 수 있어요.",
    "BAD_AMOUNT": "금액을 다시 골라 주세요.",
}


# 실전 주문이 막힐 때 화면 (NEWS_MARKET_SPEC.md 8-3 · images/11): 코드 → (제목, 설명, 버튼, 버튼 동작)
BLOCK_SCREENS = {
    "NO_CONSENT": ("실전은 부모님 동의 후에 열려요", "동의 요청 3단계를 거치면 시작할 수 있어요. 연습 모드는 계속 쓸 수 있어요.",
                   "부모님께 동의 요청하기", "consent"),
    "REVOKED": ("부모님이 실전 거래를 멈췄어요", "새로 사기는 막혀 있고, 가진 주식 보기와 팔기는 할 수 있어요.",
                "가진 주식 보기", "holdings"),
    "QUOTE_STALE": ("최신 종가가 아직 안 들어왔어요", "오늘 종가 업데이트가 끝나지 않아 실전 주문만 잠갔어요. 오래된 가격으로는 주문하지 않아요.",
                    "다시 불러오기", "reload"),
    "MARKET_CLOSED": ("지금은 장이 닫혀 있어요", "증권사 실시간 시세에서는 장 밖 주문을 다음 장 예약으로 받아요.",
                      "다음 장에 예약하기", "reserve"),
    "OVER_PER_ORDER": ("한 번에 살 수 있는 금액을 넘었어요", "부모님이 정한 1회 상한 안에서 금액을 골라 주세요.",
                       "금액 다시 고르기", "amount"),
    "OVER_MONTHLY": ("이번 달 한도를 다 썼어요", "다음 달 1일에 다시 채워져요. 그동안 연습 모드에서 해 볼 수 있어요.",
                     "연습 모드로 가기", "practice"),
    "OUT_OF_SCOPE": ("부모님이 정한 범위 밖 종목이에요", "이 종목은 연습 모드에서 먼저 해 볼까요?", "연습 모드에서 보기", "practice_view"),
    "FOMO_CHECK_REQUIRED": ("오늘 많이 오른 종목이에요", "급등주 확인이 켜져 있으면 근거를 쓰기 전엔 주문할 수 없어요.",
                            "오늘은 지켜보기", "watch"),
    "REASON_REQUIRED": ("사는 이유를 10자 이상 써 주세요", "쓴 이유는 투자일지와 부모님 알림에 함께 남아요.", "이유 쓰러 가기", "amount"),
    "INSUFFICIENT_CASH": ("계좌에 돈이 부족해요", "용돈 계좌의 투자 봉투를 확인해 주세요.", "금액 다시 고르기", "amount"),
    "INSUFFICIENT_SHARES": ("팔 수 있는 주식이 부족해요", "가진 수량 안에서 팔 수 있어요.", "가진 주식 보기", "holdings"),
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


# ---------- 상태 ----------

def new_state(student_id, parent_id=None):
    """학생 한 명의 투자 탭 상태 (data/students/invest.json에 학생별로 저장)."""
    return {
        "student_id": student_id,
        "consent": {"status": NONE, "parent_id": parent_id or f"P-{student_id}"},
        "guardrails": None,
        "history": [],            # 동의 상태 전이 기록
        "real": None,             # 실전 계좌 (계좌 개설 뒤): account_id, holdings, orders, funded
        "watch": [],              # 관심 종목 (지켜보기 포함)
        "change_requests": [],    # 학생이 쓴 한도·범위 변경 요청
        "notifications": [],      # 학생·부모 알림 기록 (to: STUDENT / PARENT)
        "checklists": [],         # 연습 주문의 사기 전 체크리스트 기록
    }


def migrate(state, student_id):
    base = new_state(student_id)
    for key, value in base.items():
        state.setdefault(key, value)
    return state


def account_linked(state):
    return bool(state.get("real") and state["real"].get("account_id"))


# ---------- 6-1 트랙 결정 ----------

def resolve_invest_track(flag_on, consent, linked, level_track=PRACTICE):
    """flag(consentTrack)가 꺼져 있으면 예전(레벨 기반) 결과를 그대로, 켜져 있으면 동의와 계좌 연결만 본다.
    레벨은 받지도 않는다 (level_track은 flag가 꺼졌을 때만 쓴다)."""
    if not flag_on:
        return level_track
    if consent.get("status") == ACTIVE and linked:
        return REAL
    return PRACTICE


def legacy_level_track(stage):
    """예전 구조: 3단계(실전 준비 완료)도 보호자 신청 시안일 뿐 실전 주문과 연결하지 않았다 → 늘 연습."""
    return PRACTICE


def can_view_real(state):
    """실전 계좌 조회·매도 화면을 볼 수 있는지: 동의 중이거나, 철회됐어도 계좌가 있으면."""
    return account_linked(state) and state["consent"]["status"] in (ACTIVE, REVOKED)


# ---------- 6-2 동의 상태 전이 ----------

TRANSITIONS = {
    "REQUEST": ({NONE, REJECTED, REVOKED}, PENDING),
    "APPROVE": ({PENDING}, ACTIVE),     # 부모 동의 + 계좌 개설 성공
    "REJECT": ({PENDING}, REJECTED),
    "REVOKE": ({ACTIVE}, REVOKED),
}
ACTORS = {"REQUEST": "STUDENT", "APPROVE": "PARENT", "REJECT": "PARENT", "REVOKE": "PARENT"}
NOTICES = {
    PENDING: ("부모님께 실전 투자 동의를 요청했어요.", "실전 투자 동의 요청이 왔어요. 연습 리포트를 확인해 주세요."),
    ACTIVE: ("부모님이 동의했어요. 실전 계좌가 연결됐어요.", "동의하고 계좌를 연결했어요."),
    REJECTED: ("부모님이 이번에는 동의하지 않았어요. 연습 모드는 계속 쓸 수 있어요.", "동의 요청을 거절했어요."),
    REVOKED: ("부모님이 실전 모드를 멈췄어요. 가진 종목 보기와 팔기는 할 수 있어요.", "실전 모드를 멈췄어요."),
}


def cooldown_left(consent, today):
    """거절·철회 뒤 재요청까지 남은 날 (0이면 바로 가능)."""
    if consent["status"] not in (REJECTED, REVOKED):
        return 0
    stamp = consent.get("revoked_at") if consent["status"] == REVOKED else consent.get("decided_at")
    if not stamp:
        return 0
    passed = (date.fromisoformat(today) - date.fromisoformat(stamp[:10])).days
    return max(0, REQUEST_COOLDOWN_DAYS - passed)


def transition(state, event, at=None, **fields):
    """동의 상태를 바꾼다. 안 되는 전이면 ValueError. 이력과 양쪽 알림을 남긴다."""
    at = at or now_iso()
    consent = state["consent"]
    allowed, target = TRANSITIONS[event]
    if consent["status"] not in allowed:
        raise ValueError(f"{consent['status']}에서 {event}를 할 수 없어요")
    if event == "REQUEST" and cooldown_left(consent, at[:10]):
        raise ValueError(f"{cooldown_left(consent, at[:10])}일 뒤에 다시 요청할 수 있어요")
    before = consent["status"]
    consent["status"] = target
    if event == "REQUEST":
        consent["requested_at"] = at
        consent["student_message"] = fields.get("message", "")
        consent["report_snapshot"] = fields.get("report")
    elif event in ("APPROVE", "REJECT"):
        consent["decided_at"] = at
        if event == "APPROVE":
            consent["broker_account_id"] = fields["account_id"]
    else:
        consent["revoked_at"] = at
    state["history"].append({"at": at, "from": before, "to": target, "by": ACTORS[event]})
    student_text, parent_text = NOTICES[target]
    notify(state, "STUDENT", student_text, at)
    notify(state, "PARENT", parent_text, at)
    return state


def notify(state, to, text, at=None):
    state["notifications"].append({"at": at or now_iso(), "to": to, "text": text})


# ---------- 부모 안전장치 ----------

def make_guardrails(monthly_limit=MONTHLY_LIMITS[0], scope=ETF_LARGECAP, notify_parent=True, fomo_check=True,
                    at=None):
    """부모가 정한 안전장치. 1회 상한은 한도의 절반, 미수·신용은 항상 막힘(바꿀 수 없음)."""
    if scope not in SCOPES:
        raise ValueError("범위를 다시 골라 주세요")
    return {"monthlyLimit": int(monthly_limit), "perOrderLimit": int(monthly_limit * PER_ORDER_RATIO),
            "scope": scope, "notifyParentOnTrade": bool(notify_parent), "fomoCheck": bool(fomo_check),
            "fomoThresholdPct": FOMO_THRESHOLD_PCT, "marginAllowed": False,
            "updatedBy": "PARENT", "updatedAt": at or now_iso()}


def update_guardrails(state, at=None, **changes):
    """부모가 요청 없이도 바꿀 수 있다. 바뀌면 학생에게 알린다."""
    g = state["guardrails"]
    new = make_guardrails(changes.get("monthly_limit", g["monthlyLimit"]), changes.get("scope", g["scope"]),
                          changes.get("notify_parent", g["notifyParentOnTrade"]),
                          changes.get("fomo_check", g["fomoCheck"]), at)
    if {k: new[k] for k in new if k != "updatedAt"} != {k: g[k] for k in g if k != "updatedAt"}:
        state["guardrails"] = new
        notify(state, "STUDENT", f"부모님이 안전장치를 바꿨어요: {guardrail_summary(new)}", at)
    return state


def guardrail_summary(g):
    return f"한 달 {g['monthlyLimit']:,}원 · {SCOPES[g['scope']][0]} · 1회 {g['perOrderLimit']:,}원까지"


# ---------- 한도 집계 ----------

def month_key(day):
    return day[:7]


def month_usage(orders, month):
    """그 달 매수 금액 합계. 매도 대금은 한도를 회복시키지 않는다."""
    return {"buys": sum(o["amount"] for o in orders if o["side"] == "BUY" and month_key(o["date"]) == month)}


def in_scope(scope, instrument):
    if scope == ALL:
        return True
    if instrument["type"] == "ETF":
        return True
    return scope == ETF_LARGECAP and bool(instrument.get("isLargeCap"))


# ---------- 6-3 실전 주문 검증 ----------

def validate_order(req, guardrails, consent, month_usage, quote, instrument, cash, held_qty=0.0,
                   fresh=True, market_open=True, source="eod"):
    """순서대로 검사하고 처음 걸리는 코드를 돌려준다. 통과하면 None (NEWS_MARKET_SPEC.md 8-3).
    req: side BUY/SELL, amount(매수, 원), qty(매도), reason, fomoAcknowledged, margin(항상 False여야 함), reserve.
    fresh: 시세가 최신인지 (eod: 기준일 >= 있어야 할 최신 종가일, broker: 60초 안).
    market_open·source: 장 시간 검사는 source가 broker일 때만 (eod는 전날 종가로 체결)."""
    side = req["side"]
    status = consent.get("status")
    if status != ACTIVE:
        if not (status == REVOKED and side == "SELL"):  # 철회돼도 매도는 허용
            return "REVOKED" if status == REVOKED else "NO_CONSENT"
    if req.get("margin") or req.get("credit"):
        return "MARGIN_NOT_ALLOWED"
    if not fresh and (source == "eod" or market_open):
        return "QUOTE_STALE"
    if source == "broker" and not market_open and not req.get("reserve"):
        return "MARKET_CLOSED"
    if side == "SELL":
        qty = float(req.get("qty") or 0)
        return None if 0 < qty <= held_qty + 1e-9 else "INSUFFICIENT_SHARES"
    amount = int(req.get("amount") or 0)
    if amount <= 0:
        return "BAD_AMOUNT"
    if amount > guardrails["perOrderLimit"]:
        return "OVER_PER_ORDER"
    if month_usage["buys"] + amount > guardrails["monthlyLimit"]:
        return "OVER_MONTHLY"
    if not in_scope(guardrails["scope"], instrument):
        return "OUT_OF_SCOPE"
    fomo = guardrails["fomoCheck"] and quote["changePct"] >= guardrails["fomoThresholdPct"]
    if fomo and not req.get("fomoAcknowledged"):
        return "FOMO_CHECK_REQUIRED"
    if len((req.get("reason") or "").strip()) < MIN_REASON_CHARS:  # 실전 매수는 늘 근거 필수 (8-3)
        return "REASON_REQUIRED"
    if amount > cash:
        return "INSUFFICIENT_CASH"
    return None


def needs_fomo_check(guardrails, quote):
    return bool(guardrails and guardrails["fomoCheck"] and quote["changePct"] >= guardrails["fomoThresholdPct"])


def chip_states(guardrails, usage):
    """금액 칩: (금액, 고를 수 있는지). 1회 상한을 넘거나 남은 한도를 넘으면 비활성."""
    left = guardrails["monthlyLimit"] - usage["buys"]
    return [(a, a <= guardrails["perOrderLimit"] and a <= left) for a in AMOUNT_CHIPS]


def fee_of(amount):
    import config
    return int(amount * config.BROKER_FEE_RATE)


def estimate_qty(amount, price, with_fee=True):
    """소수점 수량 (넷째 자리에서 버림). 수수료를 뺀 금액으로 산다."""
    spend = amount - (fee_of(amount) if with_fee else 0)
    return math.floor(spend / price * 10_000) / 10_000


def qty_label(qty):
    text = f"{qty:.2f}".rstrip("0").rstrip(".")
    return f"{text}주"


# ---------- 6-4 매매 뒤 처리 ----------

def after_trade(state, order, name, guardrails, at=None):
    """부모 알림(설정이 켜져 있으면)과 학생 알림. 투자일지는 주문 기록(order.reason) 자체로 남는다."""
    verb = "샀어요" if order["side"] == "BUY" else "팔았어요"
    amount = f"{order['amount']:,}원" if order["side"] == "BUY" else qty_label(order["qty"])
    if guardrails and guardrails["notifyParentOnTrade"]:
        why = f" · 이유: {order['reason']}" if order.get("reason") else ""
        notify(state, "PARENT", f"{name} {amount} {verb}{why}", at)
    notify(state, "STUDENT", f"실전 계좌에서 {name} {amount} {verb}.", at)


def add_watch(state, symbol, price, reason, account, day):
    """관심 종목에 담는다 (같은 종목이 이미 있으면 그대로). reason: FOMO_WAIT / USER."""
    if any(w["symbol"] == symbol and w["account"] == account for w in state["watch"]):
        return False
    state["watch"].append({"symbol": symbol, "addedAt": day, "priceAtAdd": price, "reason": reason,
                           "account": account})
    return True


def wait_result(watch_item, history_rows):
    """지켜보기 다음 거래일 종가와 비교: '기다렸다면 n% 차이'. 다음 거래일 시세가 아직 없으면 None.
    history_rows: [(date, close)] 시간순."""
    later = [(d, c) for d, c in history_rows if d > watch_item["addedAt"]]
    if not later:
        return None
    day, close = later[0]
    return {"date": day, "close": close, "diff_pct": round((close / watch_item["priceAtAdd"] - 1) * 100, 1)}


# ---------- 6-6 한도·범위 변경 요청 ----------

def request_change(state, message, monthly_limit=None, scope=None, attach_record=False, at=None):
    """학생이 직접 쓰는 변경 요청. 같은 내용은 7일에 한 번만 보낸다 (알림 피로 방지)."""
    at = at or now_iso()
    message = " ".join((message or "").split())
    if not message:
        raise ValueError("왜 바꾸고 싶은지 한 줄 써 주세요")
    if monthly_limit is None and scope is None:
        raise ValueError("바꾸고 싶은 한도나 범위를 골라 주세요")
    for r in state["change_requests"]:
        same = (r.get("requestedMonthlyLimit"), r.get("requestedScope")) == (monthly_limit, scope)
        days = (date.fromisoformat(at[:10]) - date.fromisoformat(r["at"][:10])).days
        if same and days < REQUEST_COOLDOWN_DAYS:
            raise ValueError(f"같은 요청은 {REQUEST_COOLDOWN_DAYS - days}일 뒤에 다시 보낼 수 있어요")
    req = {"id": f"CR{len(state['change_requests']) + 1:03d}", "at": at,
           "requestedMonthlyLimit": monthly_limit, "requestedScope": scope, "message": message,
           "attachRecord": bool(attach_record), "status": "SENT", "parentNote": ""}
    state["change_requests"].append(req)
    notify(state, "PARENT", f"한도·범위 변경 요청이 왔어요: {change_label(req)}", at)
    return req


def change_label(req):
    parts = []
    if req.get("requestedMonthlyLimit"):
        parts.append(f"한 달 {req['requestedMonthlyLimit']:,}원")
    if req.get("requestedScope"):
        parts.append(SCOPES[req["requestedScope"]][0])
    return " · ".join(parts)


def decide_change(state, request_id, decision, note="", monthly_limit=None, scope=None, at=None):
    """부모 결정: APPROVED(요청대로) / DECLINED / ADJUSTED(다른 값으로). 결과를 학생에게 알린다."""
    req = next(r for r in state["change_requests"] if r["id"] == request_id)
    if req["status"] != "SENT":
        raise ValueError("이미 결정한 요청이에요")
    if decision not in ("APPROVED", "DECLINED", "ADJUSTED"):
        raise ValueError(decision)
    req["status"], req["parentNote"], req["decidedAt"] = decision, note, at or now_iso()
    if decision == "APPROVED":
        monthly_limit, scope = req.get("requestedMonthlyLimit"), req.get("requestedScope")
    if decision != "DECLINED":
        changes = {}
        if monthly_limit:
            changes["monthly_limit"] = monthly_limit
        if scope:
            changes["scope"] = scope
        g = state["guardrails"]
        state["guardrails"] = make_guardrails(changes.get("monthly_limit", g["monthlyLimit"]),
                                              changes.get("scope", g["scope"]), g["notifyParentOnTrade"],
                                              g["fomoCheck"], at)
    result = {"APPROVED": "승인했어요", "DECLINED": "이번엔 그대로 두기로 했어요", "ADJUSTED": "조정해서 승인했어요"}
    text = f"부모님이 변경 요청을 {result[decision]}."
    if note:
        text += f" 메모: {note}"
    notify(state, "STUDENT", text, at)
    return req


# ---------- 화면에 쓰는 기록 ----------

def checklist_cta(count):
    """사기 전 체크리스트 수 → (버튼 글자, 강조 여부). 3개를 다 채워야 파란 버튼."""
    return ("가상으로 사기", True) if count >= 3 else ("체크리스트 없이 가상으로 사기", False)


def monthly_record(real, watch, month):
    """이번 달 내 투자 기록 (평가·등급이 아니라 돌아보는 기록).
    투자일지 수, 급등주 지켜보기 횟수, 근거 쓰고 산 비율, 최대 비중(보유 평가액 기준)."""
    orders = [o for o in (real or {}).get("orders", []) if month_key(o["date"]) == month]
    buys = [o for o in orders if o["side"] == "BUY"]
    journals = sum(bool((o.get("reason") or "").strip()) for o in orders)
    reasoned = sum(len((o.get("reason") or "").strip()) >= MIN_REASON_CHARS for o in buys)
    waits = sum(w["reason"] == "FOMO_WAIT" and month_key(w["addedAt"]) == month for w in watch)
    return {"journalCount": journals, "fomoWaitCount": waits,
            "reasonRate": None if not buys else reasoned / len(buys)}


def max_weight_pct(values):
    """{종목: 평가액} 중 가장 큰 비중 % (보유 평가액 합계 대비). 없으면 None."""
    total = sum(values.values())
    return None if not total else round(max(values.values()) / total * 100)


def real_values(real, prices):
    """실전 보유 {종목: 평가액(원)}. prices: {종목: 지금 가격}."""
    return {s: round(h["qty"] * prices[s]) for s, h in real["holdings"].items() if h["qty"] > 0 and s in prices}


def real_summary(real, prices):
    """평가금액(보유 평가액 + 계좌 현금)과 원가 대비 등락."""
    values = real_values(real, prices)
    cost = sum(h["qty"] * h["avgPrice"] for h in real["holdings"].values() if h["qty"] > 0)
    stock = sum(values.values())
    return {"value": stock + real.get("cash", 0), "stock": stock,
            "changePct": None if not cost else round((stock / cost - 1) * 100, 1)}


def apply_fill(real, order):
    """체결 결과를 실전 계좌에 반영한다 (MockBrokerAdapter가 부른다)."""
    h = real["holdings"].setdefault(order["symbol"], {"qty": 0.0, "avgPrice": 0.0})
    if order["side"] == "BUY":
        total = h["qty"] * h["avgPrice"] + order["amount"]
        h["qty"] = round(h["qty"] + order["qty"], 6)
        h["avgPrice"] = total / h["qty"]
        real["cash"] -= order["amount"]
    else:
        h["qty"] = round(h["qty"] - order["qty"], 6)
        real["cash"] += order["amount"]
    real["orders"].append(order)


SKILL_WORDS = {True: "잘하는 중", False: "연습 중"}


def practice_report(weeks, journal_count, checklist_rate, skills, highlights):
    """동의 요청에 붙는 연습 리포트. skills는 {"knowledge"/"risk"/"decision": True(잘하는 중)/False(연습 중)}.
    점수 숫자는 넣지 않는다 (CLAUDE.md 규칙 5). highlights는 행동 사실 문장."""
    return {"weeks": weeks, "journalCount": journal_count, "checklistRate": checklist_rate,
            "skills": dict(skills), "highlights": list(highlights)}


def copy_state(state):
    return copy.deepcopy(state)
