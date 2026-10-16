"""14번 내 소비 기준 체크카드 혜택 비교."""

import pandas as pd
import pytest

from conftest import open_app
from engine import cards

CARDS = {c["card_id"]: c for c in cards.load_cards()}


def allowance(*rows):
    return pd.DataFrame([("S01", "2026-09-08", "SPEND", -amount, category, "메모") for category, amount in rows],
                        columns=["student_id", "date", "envelope", "amount", "category", "memo"])


def test_card_file_has_source_and_check_date():
    for card in CARDS.values():
        assert card["kind"] == "체크카드"
        assert card["source"] and card["checked"] and card["source_urls"]
        assert card["unit"] in ("P", "원")


def test_don_check_per_payment_and_condition():
    r = cards.card_benefit(CARDS["DON_CHECK"], allowance(("CONVENIENCE", 5300), ("CONVENIENCE", 4790),
                                                          ("MEAL", 45000)), "S01")
    assert r["performance"] == 55090 and r["tier_met"]
    assert r["benefit"] == 265 + 239  # 1건마다 5%, 1원 미만 버림


def test_transport_top_up_is_excluded():
    r = cards.card_benefit(CARDS["DON_CHECK"], allowance(("CONVENIENCE", 5000), ("TRANSPORT", 48000)), "S01")
    assert r["performance"] == 5000 and not r["tier_met"] and r["benefit"] == 0 and r["gap"] == 45000


def test_don_check_caps():
    assert cards.card_benefit(CARDS["DON_CHECK"], allowance(("CONVENIENCE", 30000), ("MEAL", 30000)),
                              "S01")["benefit"] == 1000  # 1회 최대 1,000P
    assert cards.card_benefit(CARDS["DON_CHECK"], allowance(*[("CONVENIENCE", 30000)] * 5),
                              "S01")["benefit"] == 3000  # 월 최대 3,000P


def test_no_condition_card_gives_base_on_everything():
    r = cards.card_benefit(CARDS["NAVERPAY_CHECK"], allowance(("CONVENIENCE", 5000), ("MEAL", 18950)), "S01")
    assert r["tier_met"] and r["benefit"] == 50 + 189


def test_tiered_card_gives_only_base_below_condition():
    r = cards.card_benefit(CARDS["EVERYDAY_CHECK"], allowance(("CAFE_DESSERT", 8000), ("MEAL", 20000)), "S01")
    assert not r["tier_met"] and r["special"] == 0 and r["benefit"] == 16 + 40  # 0.2%만


def test_tiered_card_above_condition_uses_rule_caps():
    rows = [("CAFE_DESSERT", 100000)] * 4  # 실적 40만, 커피 1% = 4,000 → 영역 한도 3,000
    r = cards.card_benefit(CARDS["EVERYDAY_CHECK"], allowance(*rows), "S01")
    assert r["tier_met"] and r["special"] == 3000 and r["base"] == 0


def test_compare_orders_by_benefit():
    results = cards.compare(list(CARDS.values()), allowance(*[("CONVENIENCE", 5000)] * 12), "S01")
    assert [r["benefit"] for r in results] == sorted((r["benefit"] for r in results), reverse=True)
    assert results[0]["card"]["card_id"] == "DON_CHECK"  # 편의점 6만 원: 5% 적립 3,000P


def test_peer_comparison():
    peer = cards.peer_comparison(allowance(("CONVENIENCE", 5000), ("CAFE_DESSERT", 8000)), "S01", 2)
    assert peer["mine"] == pytest.approx(50.0) and peer["diff"] == pytest.approx(50.0 - peer["peer"])
    assert cards.peer_comparison(allowance(("TRANSPORT", 2000)), "S01", 2) is None


def test_envelope_page_shows_card_recommendation():
    at = open_app("pages/2_용돈봉투.py")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "카드의정석 DON CHECK" in text and "가입 권유 아님" in text
    assert "네이버페이 우리카드 체크" in text and "부족" in text  # 실적 미달 카드에 이유 표시
    assert at.metric[-1].label == "이번 달 예상 혜택" and at.metric[-1].value == "795P"  # 민지
    assert any("더 쓰는 돈이 훨씬 커요" in w.value for w in at.warning)


def test_every_card_has_a_photo():
    for card in CARDS.values():
        assert cards.image_path(card) is not None, card["card_id"]


def test_page_uses_photos():
    at = open_app("pages/2_용돈봉투.py")
    photos = [m.value for m in at.markdown if "card-photo" in m.value]
    assert len(photos) == 4 and all("data:image/png;base64," in p for p in photos)
