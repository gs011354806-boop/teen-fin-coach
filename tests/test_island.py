"""틴틴 자산섬 (game/tintin_island_handoff/ISLAND_GAME_SPEC.md 6장 로직 · 7장 검산 · 8장 완료 기준)."""

from datetime import datetime

import pandas as pd
import pytest

from conftest import open_app
from engine import island, store

PAGE = "pages/11_자산_키우기_게임.py"


# ---------- 6-2 성장 단계 ----------
@pytest.mark.parametrize("current, stage", [(0, 1), (24, 1), (25, 2), (49, 2), (50, 3), (89, 3), (90, 4), (100, 4)])
def test_crop_stage_boundaries(current, stage):
    assert island.crop_stage(current, 100) == stage


def test_segments_are_rounded_tenths():
    assert [island.segments(p) for p in (0, 34.4, 35, 64, 100, 130)] == [0, 3, 4, 6, 10, 10]


# ---------- 6-3 이자 ----------
def test_installment_interest_matches_spec():
    assert round(island.installment_interest(10_000, 0.03, 12)) == 1950


def test_compound_and_simple_examples():
    assert round(island.compound_amount(100_000, 0.03, 10)) == 134_392
    assert round(island.simple_amount(100_000, 0.03, 10)) == 130_000
    assert island.compound_text(True).endswith("134,392원") and island.compound_text(False).endswith("130,000원")


# ---------- 6-4 나무 ----------
def test_tree_type_by_volatility_and_etf(monkeypatch):
    calm = [100, 101, 100, 101, 100, 101]
    wild = [100, 110, 95, 112, 90, 108]
    assert island.tree_type("X", calm) == "apple"
    assert island.tree_type("X", wild) == "mango"
    monkeypatch.setattr(island, "ETF_TICKERS", {"ETF1"})
    assert island.tree_type("ETF1", wild) == "basket"


def test_tree_count_and_max_five():
    assert [island.tree_count(w) for w in (3, 22, 35, 78, 100)] == [1, 1, 2, 4, 5]
    holdings = [{"type": "mango", "name": "A", "weight": 78}, {"type": "apple", "name": "B", "weight": 22}]
    assert [t["type"] for t in island.trees(holdings)] == ["mango"] * 4 + ["apple"]


def test_split_preview_matches_03b():
    holdings = [{"type": "mango", "name": "바이오A", "weight": 78}, {"type": "apple", "name": "대형주B", "weight": 22}]
    preview = island.split_preview(holdings)
    assert [round(h["weight"]) for h in preview] == [40, 25, 35]
    assert [t["type"] for t in island.trees(preview)] == ["mango", "mango", "apple", "basket", "basket"]
    assert island.orchard_status(holdings)[0] is True and island.orchard_status(preview)[0] is False


def test_etf_basket_is_not_concentration():
    preview = island.split_preview([{"type": "apple", "name": "반도체A", "weight": 100}])
    assert island.max_weight(preview) == 40 and island.orchard_status(preview)[0] is False


@pytest.mark.parametrize("change, kind", [(-5, "storm"), (-3, "storm"), (-0.5, "cloudy"), (0, "sunny"), (None, "cloudy")])
def test_weather_kind(change, kind):
    assert island.weather_kind(change) == kind


# ---------- 6-5 가방 · 태그 ----------
@pytest.mark.parametrize("category, memo, icon, tag", [
    ("TRANSPORT", "버스카드 충전", "card", "need"), ("CONVENIENCE", "편의점 간식", "snack", "want"),
    ("CONVENIENCE", "편의점 음료", "can", "want"), ("MEAL", "분식집", "onigiri", "need"),
    ("OTHER", "PC방", "keyring", "want"), ("CAFE_DESSERT", "카페", "can", "want")])
def test_item_rules(category, memo, icon, tag):
    assert island.item_rule(category, memo) == (icon, tag)


def test_bag_groups_same_item_and_user_tag_wins():
    rows = [{"category": "CONVENIENCE", "memo": "편의점 음료", "amount": 1800},
            {"category": "CONVENIENCE", "memo": "편의점 음료", "amount": 1800},
            {"category": "TRANSPORT", "memo": "버스카드 충전", "amount": 5000}]
    items = island.bag_items(rows, {"편의점 음료": "need"})
    drink = next(i for i in items if i["name"] == "편의점 음료")
    assert drink["qty"] == 2 and drink["amount"] == 3600 and drink["tag"] == "need" and drink["tag_source"] == "user"


def test_mock_bag_totals_match_spec():
    view = island.build_mock_view()
    assert (view["bag"]["need"], view["bag"]["want"], view["bag"]["want_pct"]) == ("8,800원", "9,600원", 52)
    assert sum(i["amount"] for i in view["bag"]["items"]) == 18_400


def test_wish_remaining():
    now = datetime(2026, 11, 13, 10, 0)
    assert island.wish_remaining("2026-11-13T00:22", now) == "14:22"
    assert island.wish_remaining("2026-11-12T09:00", now) is None


def test_shop_cards_compute_numbers():
    bundle, sub = island.shop_cards("2026-11-13")
    assert "개당" in bundle["body"] and sub["badge"] == "자동결제 주의" and "1년이면" in sub["body"]


# ---------- 6-6 씨앗 · 레벨 ----------
def test_daily_seed_cap():
    assert island.capped_grant(100, 0) == 100
    assert island.capped_grant(100, 150) == 50
    assert island.capped_grant(20, 200) == 0


def test_grant_once_per_key_and_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    (tmp_path / "students").mkdir()
    assert island.grant(store, "S01", "2026-10-03", 150, "퀘스트", "quest-1") == 150
    assert island.grant(store, "S01", "2026-10-03", 150, "퀘스트", "quest-1") == 0       # 같은 보상은 한 번만
    assert island.grant(store, "S01", "2026-10-03", 100, "수확", "harvest-x") == 50     # 하루 200 상한
    assert island.grant(store, "S01", "2026-10-04", 20, "찜 취소", "wish-1") == 20       # 다음 날은 다시
    assert island.seed_balance(store.load_island("seeds"), "S01") == 220


def test_level_from_exp():
    assert island.level_from_exp(0) == (1, 0, 100)
    assert island.level_from_exp(150) == (2, 50, 200)
    assert island.level_from_exp(300) == (3, 0, 300)


# ---------- 6-7 · 6-8 ----------
def test_stars():
    assert island.stars(3, 4, 78, 52) == 1
    assert island.stars(3, 4, 40, 50) == 3
    assert island.stars(0, 0, 100, 80) == 0


def test_quests_recommend_low_skills_then_trigger():
    good = {"planSpend": True, "goalSaving": False, "knowledge": True, "risk": False, "decision": True}
    quests = island.recommend_quests(good, "SPEND_FREQ_HIGH", {"label": "편의점", "count": 4})
    assert [q["skill"] for q in quests] == ["risk", "goalSaving", "planSpend"]
    assert [q["selected"] for q in quests] == [True, True, False]
    assert quests[2]["title"] == "편의점은 3번만 가기" and quests[2]["mission_option"] == "A"


def test_mock_view_matches_spec_numbers():
    view = island.build_mock_view()
    assert view["status"]["assets"] == {"farm": "178,000", "orchard": "64,000", "total": "242,000"}
    assert [p["note"] for p in view["farm"]["plots"]][2] == "만기 이자 열매 약 +1,950원"
    assert view["hud"] == {"date": "11/13 (금)", "weather": "sunny", "title": "Lv.7 민지의 섬", "seeds": "1,240"}
    assert view["status"]["next"]["skill"] == "위험관리" and view["status"]["next"]["to"] == "orchard"


def test_status_shows_no_skill_numbers():
    """CLAUDE.md 규칙 5 (2026-11-13 결정): 능력은 숫자·막대 없이 '잘하는 것 / 다음에 키울 능력'만."""
    view = island.build_mock_view()
    for skill in view["status"]["skills"]:
        assert set(skill) == {"key", "label", "good", "next"}


def test_weekly_shows_weight_not_return():
    """CLAUDE.md 규칙 4: 결산에 수익률을 보여 주지 않는다 (날씨와 비중으로)."""
    rows = island.build_mock_view()["weekly"]["rows"]
    assert all("-11%" not in r["value"] for r in rows) and "비중" in rows[1]["value"]


def test_virtual_names_hide_real_company_names():
    tickers = store.load_ticker_names()
    for s in store.load_students():
        ctx = _ctx()
        view = island.build_view(s, ctx)
        text = str(view)
        assert not any(name in text for name in tickers.values()), s["name"]


def _ctx():
    return dict(allowance=store.load_allowance(), trades=store.load_trades(), prices=store.load_prices(),
                runs=store.load_mission_runs(), concepts=store.load_concepts(), lessons=store.load_lessons(),
                reviews=store.load_game_reviews(), questions=store.load_questions(),
                **{name: pd.DataFrame(columns=cols) for name, (_, cols) in store.ISLAND_TABLES.items()})


def test_real_view_numbers_come_from_records():
    s = store.load_students()[0]
    view = island.build_view(s, _ctx())
    from engine import envelope
    saved = envelope.balances(store.load_allowance(), s["student_id"])["SAVE"]
    assert view["status"]["assets"]["farm"] == f"{saved:,}"
    assert view["farm"]["plots"][0]["target"] == s["saving_goal"]["amount"]


# ---------- 화면 ----------
def test_island_page_renders_real_and_mock():
    at = open_app(PAGE)
    assert not at.exception, at.exception
    assert at.title[0].value == "틴틴 자산섬"
    at = open_app(PAGE, query={"mock": "1"})
    assert not at.exception, at.exception


def test_island_flag_off_shows_old_game(monkeypatch):
    import config

    monkeypatch.setattr(config, "ISLAND_GAME", False)
    at = open_app(PAGE)
    assert not at.exception and at.title[0].value == "자산 키우기 게임"
