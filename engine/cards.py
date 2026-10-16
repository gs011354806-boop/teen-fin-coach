"""내 소비 기준 카드 혜택 계산. LLM 호출 금지.

카드 정보: data/reference/cards.json (출처·확인일 포함). 추천·가입 권유가 아니라
"이번 달 내 지출에 이 카드를 썼다면" 받을 수 있었던 혜택을 계산해 보여 준다.
"""

import json
from pathlib import Path

from engine import consumption, envelope

CARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "cards.json"


def load_cards(path=None):
    return json.loads(Path(path or CARDS_PATH).read_text(encoding="utf-8"))


def monthly_benefit(card, allowance, student_id):
    """한 달(데모 기록 4주) 지출로 계산한 혜택.

    - 실적: 쓰기 봉투 지출 합계 (prev_month_excludes 카테고리 제외). 이번 달 실적으로 조건 충족 여부를 본다.
    - 혜택: 대상 카테고리 결제 1건마다 금액 × 적립률 (1원 미만 버림), 1회 한도, 월 한도 적용.
    """
    spent = envelope.spending(allowance, student_id)
    counted = spent[~spent["category"].isin(card["prev_month_excludes"])]
    performance = int(-counted["amount"].sum())
    eligible = spent[spent["category"].isin(card["benefit_categories"])]
    per_payment = [min(int(-amount * card["benefit_rate"]), card["per_payment_cap"])
                   for amount in eligible["amount"]]
    uncapped = sum(per_payment)
    benefit = min(uncapped, card["monthly_cap"])
    return {
        "performance": performance,
        "meets_condition": performance >= card["min_prev_month_spend"],
        "eligible_count": len(eligible),
        "eligible_amount": int(-eligible["amount"].sum()),
        "benefit": benefit,
        "capped": uncapped > card["monthly_cap"],
    }


def peer_comparison(allowance, student_id, gender, category="CONVENIENCE"):
    """BC 통계(같은 성별 20세 미만)와 비교한 결제 건수 비중 (%p). BC 카테고리 지출이 없으면 None."""
    spent = envelope.spending(allowance, student_id)
    bc = spent[spent["category"].isin(consumption.BC_CATEGORIES)]
    if len(bc) == 0:
        return None
    mine = (bc["category"] == category).mean() * 100
    peer = consumption.baseline()[gender][category]["count_share"] * 100
    return {"mine": mine, "peer": peer, "diff": mine - peer}
