"""내 소비 기준 체크카드 혜택 비교. LLM 호출 금지.

카드 정보: data/reference/cards.json (출처·확인일 포함). "이번 달 내 지출에 이 카드를 썼다면"
받을 수 있었던 혜택을 카드마다 계산하고, 가장 큰 카드를 보여 준다. 가입 권유가 아니다.

계산 규칙
- 실적: 쓰기 봉투 지출 합계 (performance_excludes 제외). 데모는 4주 기록이라 이번 달 실적으로 조건을 본다.
- 실적 구간(tiers): 실적이 min_spend 이상인 가장 높은 구간의 한도를 쓴다. 구간이 있는데 못 채우면 특별 혜택 0.
- 특별 혜택(rules): 대상 카테고리 결제 1건마다 금액 × 비율 (1원 미만 버림), 1회 한도, 영역별 월 한도, 통합 월 한도.
- 기본 혜택(base_rate): 특별 혜택을 받지 않은 결제에 적용. 실적 조건 없음.
"""

import json
from pathlib import Path

from engine import consumption, envelope

CARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "cards.json"


def load_cards(path=None):
    return json.loads(Path(path or CARDS_PATH).read_text(encoding="utf-8"))


def image_path(card):
    """카드 사진 파일 (data/reference/ 안). 없으면 None → 화면은 카드 모양 그래픽을 쓴다."""
    path = CARDS_PATH.parent / card.get("image", "")
    return path if card.get("image") and path.is_file() else None


def _cap(value, cap):
    return value if cap is None else min(value, cap)


def card_benefit(card, allowance, student_id):
    spent = envelope.spending(allowance, student_id)
    performance = int(-spent.loc[~spent["category"].isin(card["performance_excludes"]), "amount"].sum())
    met = [t for t in card["tiers"] if performance >= t["min_spend"]]
    tier = met[-1] if met else None
    eligible = spent[~spent["category"].isin(card["benefit_excludes"])]

    special, used = 0, set()
    by_rule = {}
    if tier or not card["tiers"]:
        for rule in card["rules"]:
            rows = eligible[eligible["category"].isin(rule["categories"])]
            rows = rows[-rows["amount"] >= rule.get("min_payment", 0)]
            amount = sum(_cap(int(-a * rule["rate"]), rule.get("per_payment_cap")) for a in rows["amount"])
            amount = _cap(amount, tier["rule_monthly_cap"] if tier else None)
            by_rule[rule["label"]] = amount
            special += amount
            used |= set(rows.index)
        special = _cap(special, tier["total_monthly_cap"] if tier else None)
    base_rows = eligible.drop(index=list(used))
    base = sum(int(-a * card["base_rate"]) for a in base_rows["amount"])

    first = card["tiers"][0]["min_spend"] if card["tiers"] else 0
    return {
        "card": card,
        "performance": performance,
        "tier_met": tier is not None or not card["tiers"],
        "min_spend": first,
        "gap": max(0, first - performance),
        "special": special,
        "base": base,
        "benefit": special + base,
        "by_rule": by_rule,
    }


def compare(cards, allowance, student_id):
    """카드별 결과를 혜택이 큰 순서로. 같으면 cards.json 순서."""
    results = [card_benefit(card, allowance, student_id) for card in cards]
    return sorted(results, key=lambda r: -r["benefit"])


def max_special_if_met(card):
    """첫 실적 구간을 채웠을 때 받을 수 있는 특별 혜택 최대치 (한도를 모르면 None)."""
    if not card["tiers"]:
        return None
    return card["tiers"][0]["total_monthly_cap"]


def peer_comparison(allowance, student_id, gender, category="CONVENIENCE"):
    """BC 통계(같은 성별 20세 미만)와 비교한 결제 건수 비중 (%p). BC 카테고리 지출이 없으면 None."""
    spent = envelope.spending(allowance, student_id)
    bc = spent[spent["category"].isin(consumption.BC_CATEGORIES)]
    if len(bc) == 0:
        return None
    mine = (bc["category"] == category).mean() * 100
    peer = consumption.baseline()[gender][category]["count_share"] * 100
    return {"mine": mine, "peer": peer, "diff": mine - peer}
