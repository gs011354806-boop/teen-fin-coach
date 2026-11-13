"""틴틴 자산섬 v2 규칙 엔진 (game2/tintin_island_handoff/ISLAND_GAME_SPEC.md 6장 · 7장 검산 · 8장 완료 기준)."""

import copy

import pytest

from engine import island_game as g

DATE = "2026-11-13"


@pytest.fixture
def demo():
    return g.load_demo()


# ---------- 7장 검산 ----------
def test_demo_net_worth_matches_spec(demo):
    nw = g.net_worth(demo)
    assert (nw["cash"], nw["deposit"], nw["trees"], nw["storage"], nw["house"], nw["loans"]) == (2480, 1000, 1752, 1320, 3000, 0)
    assert nw["total"] == 9552


def test_demo_concentration_82(demo):
    assert round(g.max_weight(demo)) == 82


def test_diversify_like_03b(demo):
    for action, tree in [("buy_tree", "red"), ("sell_tree", "gold"), ("sell_tree", "gold"),
                         ("buy_tree", "basket"), ("buy_tree", "basket")]:
        ok, _ = g.act(demo, {"action": action, "tree": tree})
        assert ok
    assert demo["trees"] == {"red": 2, "gold": 1, "mango": 0, "basket": 2}
    assert demo["cash"] == 2628 and g.orchard_value(demo) == 1604 and round(g.max_weight(demo)) == 39
    assert demo["ap"] == 0  # 나무 3종류 첫 거래만 행동력 1씩


def test_plots_cost_profit(demo):
    info = [g.plot_info(demo, i) for i in range(4)]
    assert [(p["sale"], p["profit"], p["profit_pct"]) for p in info[:3]] == [(480, 240, 100), (150, 90, 150), (660, 360, 120)]
    assert [p["seg"] for p in info[:3]] == [6, 10, 3]
    assert info[1]["ready"] and not info[0]["ready"] and info[2]["days_left"] == 4 and info[3]["empty"]


def test_tool_payback_8_days(demo):
    t = g.tool_offer(demo)
    assert (t["price"], t["extra_per_day"], t["payback"]) == (600, 75, 8)


def test_house_plan_save_or_loan(demo):
    p = g.house_plan(demo)
    assert (p["name"], p["shortfall"], p["avg_net"], p["save_days"]) == ("통나무집", 2520, 420, 6)
    assert (p["repay"], p["interest"]) == (2646, 126)


def test_opportunity_cost_apples(demo):
    assert g.opportunity_text(demo, 1200).startswith("1,200냥이면 사과 27개")


def test_neighbor_trade_values(demo):
    assert g.offer_values(demo) == {"give": 150, "want": 120, "good": True}
    ok, msg = g.act(demo, {"action": "trade"})
    assert ok and demo["inventory"]["shell"] == 10 and demo["inventory"]["strawberry"] == 6 and "이득" in msg


# ---------- 6-2 시세 ----------
def test_sell_full_price_then_supply_drop(demo):
    ok, _ = g.act(demo, {"action": "sell", "item": "apple"})
    assert ok and demo["cash"] == 2480 + 12 * 45 and "apple" not in demo["inventory"]
    assert g.supply_drop(10) == 0 and g.supply_drop(12) == pytest.approx(0.04) and g.supply_drop(40) == 0.2
    demo["inventory"]["apple"] = 5
    assert g.unit_prices(demo, "apple", 5) == [round(45 * 0.96)] * 5


def test_festival_raises_price_and_unlocks_supply_demand(demo):
    plain = g.item_price_on(1, 5, "firewood", [])
    fest = g.item_price_on(1, 5, "firewood", [{"kind": "festival", "target": "firewood"}])
    assert fest == pytest.approx(plain * 1.4, abs=1)
    g.act(demo, {"action": "sell", "item": "firewood"})
    assert "supply_demand" in demo["dex"]


def test_item_price_within_volatility():
    for day in range(1, 40):
        p = g.item_price_on(7, day, "apple", [])
        assert 40 * 0.85 - 1 <= p <= 40 * 1.15 + 1


# ---------- 6-3 나무 ----------
def test_tree_returns_seeded_and_storm_shock():
    calm = g.tree_returns(3, 9, [])
    assert calm == g.tree_returns(3, 9, [])  # 같은 시드 → 같은 결과
    storm = g.tree_returns(3, 9, [{"kind": "storm", "target": "gold"}])
    assert storm["gold"] == pytest.approx(calm["gold"] - 0.2)
    assert calm["basket"] == pytest.approx((calm["red"] + calm["gold"] + calm["mango"]) / 3)


def test_buy_needs_cash(demo):
    demo["cash"] = 100
    ok, msg = g.act(demo, {"action": "buy_tree", "tree": "gold"})
    assert not ok and "모자라요" in msg


# ---------- 6-1 하루 진행 ----------
def test_end_day_is_reproducible(demo):
    a, b = copy.deepcopy(demo), copy.deepcopy(demo)
    assert g.end_day(a, DATE) == g.end_day(b, DATE) and a == b


def test_end_day_order_and_effects(demo):
    cash = demo["cash"]
    rec = g.end_day(demo, DATE)
    assert demo["day"] == 13 and demo["ap"] == 5
    assert ["생활비", -100] in rec["expense"]
    assert ["배당 열매 (빨간사과나무)", 8] in rec["income"]   # 8냥 × 1그루 (규칙값, 시안 mock은 24)
    assert demo["cash"] == cash - 100 + 8
    assert demo["events"]["today"] == [{"kind": "storm", "target": "gold"}]  # 하루 전 예고된 태풍이 오늘
    assert demo["history"][-1]["day"] == 12 and demo["history"][-1]["netWorth"] == rec["netWorth"] == g.net_worth(demo)["total"]


def test_storm_loss_unlocks_concentration(demo):
    g.end_day(demo, DATE)
    if demo["treeHist"]["gold"][-1] < demo["treeHist"]["gold"][-2]:
        assert "concentration" in demo["dex"]


def test_daily_progress_cap(demo):
    for _ in range(3):
        assert g.end_day(demo, DATE) is not None
    assert g.end_day(demo, DATE) is None and demo["day"] == 15
    assert g.end_day(demo, "2026-11-14") is not None


def test_deposit_interest_every_7_days_compound():
    s = g.new_state("민지", 5)
    g.act(s, {"action": "deposit", "amount": 500})
    for i in range(7):
        g.end_day(s, f"2026-11-{10 + i}")
    assert s["deposit"]["amount"] == 505 and "compound" in s["dex"]
    for i in range(7):
        g.end_day(s, f"2026-12-{10 + i}")
    assert s["deposit"]["amount"] == 510  # 505 × 1.01 = 510.05


def test_living_cost_shortfall_no_game_over():
    s = g.new_state("민지", 5)
    s["cash"] = 30
    rec = g.end_day(s, DATE)
    assert s["cash"] == 0 and s["day"] == 2 and ["생활비", -100] in rec["expense"]
    assert s["daily"][-1]["missed_living"] == 1


def test_loan_build_and_repay_on_due_day(demo):
    ok, _ = g.act(demo, {"action": "build", "mode": "loan"})
    assert ok and demo["house"] == 2 and demo["cash"] == 0 and demo["loans"][0]["due"] == 2646
    assert g.net_worth(demo)["total"] == 9552 - 126  # 현금 2,480 + 빌린 2,520 → 집 값으로, 이자 126만큼 줄어든다
    assert "interest" in demo["dex"]
    demo["cash"] = 5000
    for i in range(7):
        g.end_day(demo, f"2026-11-{14 + i}")
    assert demo["loans"][0]["repaid"]


def test_loan_overdue_is_marked_not_forced():
    s = g.new_state("민지", 5)
    s["loans"].append({"principal": 1000, "due": 1050, "takenDay": 1, "dueDay": 1, "repaid": False, "overdue": False})
    s["cash"] = 200
    g.end_day(s, DATE)
    assert s["loans"][0]["overdue"] and not s["loans"][0]["repaid"] and s["cash"] == 100


def test_build_with_cash(demo):
    demo["cash"] = 6000
    ok, _ = g.act(demo, {"action": "build", "mode": "cash"})
    assert ok and demo["cash"] == 1000 and g.house(demo)["name"] == "통나무집" and len(demo["plots"]) == 4


# ---------- 행동력 · 밭 · 창고 ----------
def test_action_points_run_out(demo):
    for _ in range(3):
        g.act(demo, {"action": "gather", "kind": "shell"})
    ok, msg = g.act(demo, {"action": "gather", "kind": "shell"})
    assert not ok and "행동력" in msg


def test_harvest_and_plant(demo):
    ok, _ = g.act(demo, {"action": "harvest", "plot": 1})
    assert ok and demo["inventory"]["potato"] == 6 and demo["plots"][1]["crop"] is None
    ok, _ = g.act(demo, {"action": "plant", "plot": 3, "crop": "strawberry"})
    assert ok and demo["cash"] == 2480 - 240 and ["딸기 씨앗 구입", -240] in demo["today"]["expense"]


def test_tool_upgrade_raises_yield(demo):
    g.act(demo, {"action": "upgrade"})
    assert demo["tools"]["wateringCan"] == 2 and g.crop_yield(demo, "strawberry") == 10 and "payback" in demo["dex"]


def test_storage_limit():
    s = g.new_state("민지", 5)
    s["inventory"] = {i: 1 for i in list(g.RULES["items"])[:5]}
    s["house"] = 0
    s["inventory"]["x1"] = 1
    s["inventory"]["x2"] = 1
    s["inventory"]["x3"] = 1  # 텐트 창고 8칸이 가득
    ok, msg = g.act(s, {"action": "gather", "kind": "firewood"})
    assert not ok and "창고" in msg


# ---------- 찜 · 기회비용 ----------
def test_wish_then_drop_unlocks_opportunity_cost(demo):
    g.act(demo, {"action": "wish"})
    assert demo["wish"]["name"] == "한정판 등불 장식" and demo["temptation"] is None
    ok, _ = g.act(demo, {"action": "wish_drop"})
    assert ok and "opportunity_cost" in demo["dex"] and demo["cash"] == 2480


def test_buy_now_lowers_planning(demo):
    demo["statsOverride"] = None
    before = g.stats(demo)["planning"]
    g.act(demo, {"action": "buy_now"})
    assert demo["cash"] == 1280 and g.stats(demo)["planning"] < before


# ---------- 6-8 · 6-10 ----------
def test_stats_range_and_risk_from_weight(demo):
    demo["statsOverride"] = None
    st = g.stats(demo)
    assert set(st) == set(g.STAT_KEYS) and all(0 <= v <= 100 for v in st.values())
    assert st["risk"] == round(100 - (g.max_weight(demo) - 30))


def test_level_and_title(demo):
    assert g.level_from_exp(demo["exp"])[:2] == (4, 200)
    assert g.title_for(4) == "새내기 상인"


def test_new_state_day_one():
    s = g.new_state("민지", 99)
    assert (s["day"], s["cash"], s["house"], s["ap"], len(s["plots"])) == (1, 1000, 0, 4, 2)
    assert g.net_worth(s)["total"] == 1000


# ---------- 화면 · 분리 (8장 완료 기준) ----------
PAGE = "pages/11_자산_키우기_게임.py"


def test_page_renders_start_mock_and_result(tmp_path, monkeypatch):
    from conftest import open_app
    from engine import store

    monkeypatch.setattr(store, "ISLAND_GAME_FILE", "island_game_test_unused.json")
    for query in (None, {"mock": "1"}, {"mock": "result"}):
        at = open_app(PAGE, query=query)
        assert not at.exception, (query, at.exception)
        assert at.title[0].value == "틴틴 자산섬"


def test_version_1_still_available(monkeypatch):
    import config
    from conftest import open_app

    monkeypatch.setattr(config, "ISLAND_VERSION", 1)
    at = open_app(PAGE)
    assert not at.exception, at.exception


def test_game_engine_does_not_use_app_financial_data():
    """게임은 앱의 실제 금융 데이터(용돈·거래·가상투자)를 읽거나 쓰지 않는다."""
    import inspect

    from engine import island_view

    for module in (g, island_view):
        source = inspect.getsource(module)
        assert "store" not in source.split('"""', 2)[-1] or "from engine import store" not in source
        for word in ("allowance", "trades.csv", "load_trades", "load_allowance", "mission_runs"):
            assert word not in source


def test_save_and_load_game_state(tmp_path):
    from engine import store

    s = g.new_state("민지", 1)
    store.save_island_game("S01", s, data_dir=tmp_path)
    assert store.load_island_game("S01", data_dir=tmp_path) == s
    assert store.load_island_game("S02", data_dir=tmp_path) is None


def test_view_numbers_agree_between_hud_status_and_result(demo):
    from engine import island_view

    g.act(demo, {"action": "sell", "item": "apple"})
    g.end_day(demo, DATE)
    v = island_view.build_view(demo, DATE)
    nw = g.net_worth(demo)["total"]
    assert v["status"]["net_worth"] == f"{nw:,}" and v["hud"]["cash"] == f"{demo['cash']:,}"
    assert demo["lastResult"]["netWorth"] == nw
