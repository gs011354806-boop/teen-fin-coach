"""14번 내 소비 기준 카드 혜택 계산기."""

import pandas as pd
import pytest

from conftest import open_app
from engine import cards

CARD = cards.load_cards()[0]


def allowance(*rows):
    return pd.DataFrame([("S01", "2026-09-08", "SPEND", -amount, category, "메모") for category, amount in rows],
                        columns=["student_id", "date", "envelope", "amount", "category", "memo"])


def test_card_file_has_source_and_check_date():
    for card in cards.load_cards():
        assert card["source"] and card["checked"] and card["source_urls"]
        assert card["kind"] == "체크카드"  # 청소년은 체크카드만


def test_benefit_per_payment_and_condition():
    result = cards.monthly_benefit(CARD, allowance(("CONVENIENCE", 5300), ("CONVENIENCE", 4790),
                                                   ("MEAL", 45000)), "S01")
    assert result["performance"] == 55090 and result["meets_condition"]
    assert result["benefit"] == 265 + 239  # 1건마다 5%, 1원 미만 버림


def test_transport_is_not_counted_for_condition():
    result = cards.monthly_benefit(CARD, allowance(("CONVENIENCE", 5000), ("TRANSPORT", 48000)), "S01")
    assert result["performance"] == 5000 and not result["meets_condition"]


def test_per_payment_and_monthly_caps():
    one_big = cards.monthly_benefit(CARD, allowance(("CONVENIENCE", 30000), ("MEAL", 30000)), "S01")
    assert one_big["benefit"] == 1000  # 1회 최대 1,000P
    many = cards.monthly_benefit(CARD, allowance(*[("CONVENIENCE", 30000)] * 5), "S01")
    assert many["benefit"] == 3000 and many["capped"]  # 월 최대 3,000P


def test_peer_comparison():
    peer = cards.peer_comparison(allowance(("CONVENIENCE", 5000), ("CAFE_DESSERT", 8000)), "S01", 2)
    assert peer["mine"] == pytest.approx(50.0) and peer["diff"] == pytest.approx(50.0 - peer["peer"])
    assert cards.peer_comparison(allowance(("TRANSPORT", 2000)), "S01", 2) is None


def test_envelope_page_shows_card_benefit():
    at = open_app("pages/2_용돈봉투.py")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "카드의정석 DON CHECK" in text and "추천·가입 권유가 아니에요" in text
    assert [m.label for m in at.metric][-2:] == ["이번 달 예상 적립", "실적 인정 금액"]
    assert at.metric[-2].value == "795P"  # 민지: 편의점 3건 15,900원
