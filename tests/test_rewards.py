"""7번 포인트·캐릭터·가상 쿠폰 검증."""

from pathlib import Path

import pandas as pd
import pytest
from conftest import open_app

from engine import rewards, store

ROOT = Path(__file__).resolve().parent.parent
PAGE = "pages/5_포인트와_캐릭터.py"
STUDENT = {"student_id": "S01", "saving_goal": {"item": "에어팟", "amount": 10000}}


def trades(*journals, date="2026-09-08"):
    return pd.DataFrame([("T%04d" % i, "S01", date, "005930", "BUY", 1, 100, j)
                         for i, j in enumerate(journals, 1)], columns=store.TRADE_COLUMNS)


def missions(*rows):
    return pd.DataFrame([{"student_id": "S01", "week_start": w, "done": d, "text": "미션"}
                         for w, d in rows], columns=["student_id", "week_start", "done", "text"])


def allowance(*amounts):
    return pd.DataFrame([("S01", f"2026-09-{7 + i:02d}", "SAVE", a) for i, a in enumerate(amounts)],
                        columns=["student_id", "date", "envelope", "amount"])


def test_journal_points_only_for_reasoned_journals():
    events = rewards.earn_events(STUDENT, trades("", "더 오를듯", "반도체 수요가 늘 것 같아서"),
                                 missions(), allowance())
    assert [e["points"] for e in events] == [rewards.JOURNAL_POINTS]


def test_mission_points_only_when_done_on_week_end():
    events = rewards.earn_events(STUDENT, trades(),
                                 missions(("2026-09-14", "TRUE"), ("2026-09-14", "FALSE"),
                                          ("2026-09-21", "")), allowance())
    assert [(e["date"], e["points"]) for e in events] == [("2026-09-20", rewards.MISSION_POINTS)]


def test_goal_bonus_once_on_reach_day():
    events = rewards.earn_events(STUDENT, trades(), missions(), allowance(6000, 6000, -3000, 6000))
    assert [(e["date"], e["points"], e["capped"]) for e in events] == [
        ("2026-09-08", rewards.GOAL_BONUS_POINTS, False)]


def test_daily_cap():
    journal = "근거를 충분히 길게 적었어요"
    events = rewards.earn_events(STUDENT, trades(*[journal] * 12), missions(), allowance())
    granted = rewards.apply_daily_cap(events)
    assert sum(e["granted"] for e in granted) == rewards.DAILY_CAP
    assert granted[-1]["granted"] == 0


def test_goal_bonus_is_outside_daily_cap():
    journal = "근거를 충분히 길게 적었어요"
    events = rewards.earn_events(STUDENT, trades(*[journal] * 12, date="2026-09-08"), missions(),
                                 allowance(6000, 6000))
    total = sum(e["granted"] for e in rewards.apply_daily_cap(events))
    assert total == rewards.DAILY_CAP + rewards.GOAL_BONUS_POINTS


def test_balance_and_feed_count():
    events = [{"granted": 300}, {"granted": 100}]
    spends = pd.DataFrame([("S01", "FEED", "50"), ("S01", "COUPON", "500"), ("S02", "FEED", "50")],
                          columns=["student_id", "kind", "points"])
    spends = spends[spends["kind"] == "FEED"]
    assert rewards.balance(events, spends, "S01") == 350
    assert rewards.feed_count(spends, "S01") == 1


@pytest.mark.parametrize("feeds, expected", [
    (0, ("알", "아기", 4)), (3, ("알", "아기", 1)), (4, ("아기", "청소년", 6)),
    (19, ("청소년", "어른", 1)), (20, ("어른", None, 0)), (99, ("어른", None, 0)),
])
def test_stage(feeds, expected):
    assert rewards.stage(feeds) == expected


def test_stage_never_goes_down():
    names = [rewards.stage(n)[0] for n in range(30)]
    order = [s for s, _ in rewards.STAGES]
    assert [order.index(n) for n in names] == sorted(order.index(n) for n in names)


def test_check_spend():
    assert rewards.check_spend(50, 50) is None
    assert "30P" in rewards.check_spend(500, 470)


def test_no_link_to_returns_or_spending_amount():
    """규칙 4: 거래 가격·수량이나 지출 금액이 바뀌어도 포인트는 같다."""
    base = rewards.earn_events(STUDENT, trades("근거를 충분히 길게 적었어요"), missions(), allowance())
    rich = trades("근거를 충분히 길게 적었어요")
    rich["price"], rich["qty"] = 999999, 99
    assert rewards.earn_events(STUDENT, rich, missions(), allowance()) == base


def test_append_spend(tmp_path):
    path = tmp_path / "point_spend.csv"
    assert store.append_spend("S01", "2026-10-04", "FEED", "먹이", 50, path=path) == "P0001"
    assert store.append_spend("S01", "2026-10-04", "COUPON", "편의점 1,000원권", 500, path=path) == "P0002"
    spends = store.load_spends(path)
    assert list(spends["points"]) == ["50", "500"] and list(spends.columns) == store.SPEND_COLUMNS


# --- 화면 ---

@pytest.fixture
def spend_path(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SPEND_PATH", tmp_path / "point_spend.csv")
    return tmp_path / "point_spend.csv"


def open_page():
    at = open_app(PAGE)
    assert not at.exception, at.exception
    return at


def test_page_feed(spend_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "PIGGY_BANK", False)  # 예전 알 키우기 화면 (돼지 저금통 스위치를 끄면 그대로)
    monkeypatch.setattr(rewards, "balance", lambda *args: 500)
    at = open_page()
    at.sidebar.selectbox[0].select("서연 (고1)").run()
    next(b for b in at.button if b.label.startswith("먹이 주기")).click().run()
    assert not at.exception
    spends = store.load_spends(spend_path)
    assert list(spends["kind"]) == ["FEED"] and spends.iloc[0]["student_id"] == "S03"
    assert any("냠냠" in m.value for m in at.success)
    assert "1개" in " ".join(m.value for m in at.markdown)  # 먹은 먹이 수가 바로 반영


def view(at, item):
    next(b for b in at.button if b.key == f"view-{item}").click().run()
    assert not at.exception, at.exception
    return at


def test_coupon_detail_and_exchange_with_quantity(spend_path, monkeypatch):
    monkeypatch.setattr(rewards, "balance", lambda *args: 5000)
    at = view(open_page(), "편의점 1,000원권")
    text = " ".join(m.value for m in at.markdown)
    assert "편의점 1,000원권" in text and "500P" in text and "유효기간" in text

    at.number_input(key="coupon_qty").set_value(3).run()
    assert "1,500P" in " ".join(m.value for m in at.markdown)  # 수량 × 가격
    next(b for b in at.button if b.label == "나에게 교환하기").click().run()
    assert not at.exception

    spends = store.load_spends(spend_path)
    assert list(spends["item"]) == ["편의점 1,000원권"] * 3
    assert list(spends["points"]) == ["500"] * 3
    assert any("3장" in m.value for m in at.success)
    assert any(b.key and b.key.startswith("view-") for b in at.button)  # 상점 목록으로 돌아옴


def test_coupon_exchange_disabled_without_enough_points(spend_path, monkeypatch):
    monkeypatch.setattr(rewards, "balance", lambda *args: 1000)
    at = open_page()  # 돼지 저금통: 모자라면 상점에서 바로 회색 [모으는 중] (상세로 들어갈 수 없다)
    button = next(b for b in at.button if b.key == "view-문화상품권 5,000원권")
    assert button.disabled and button.label == "모으는 중"
    assert "1,300P 더 모으면 바꿀 수 있어요" in " ".join(m.value for m in at.markdown)
    assert len(store.load_spends(spend_path)) == 0


def test_back_to_shop(spend_path, monkeypatch):
    monkeypatch.setattr(rewards, "balance", lambda *args: 2000)
    at = view(open_page(), "편의점 3,000원권")
    next(b for b in at.button if b.label == "← 상점으로").click().run()
    assert sum(1 for b in at.button if b.key and b.key.startswith("view-")) == len(rewards.COUPONS)


# --- 돼지 저금통 (point/tintin_piggy/PIGGY_BANK_SPEC.md 3장) ---

@pytest.mark.parametrize("balance, no, left", [
    (0, 1, 500), (499, 1, 1), (500, 2, 900), (1650, 3, 650), (2300, 4, 1200), (3500, 5, None), (9999, 5, None),
])
def test_piggy_level_from_balance(balance, no, left):
    assert rewards.level_of(balance)["no"] == no
    assert rewards.progress_to_next(balance)[1] == left


def test_piggy_levels_start_at_coupon_prices_and_gold_is_last():
    prices = [c["points"] for c in rewards.COUPONS]
    assert [l["min"] for l in rewards.PIGGY_LEVELS[1:4]] == prices
    assert rewards.PIGGY_LEVELS[-1]["key"] == "gold" and rewards.PIGGY_LEVELS[-1]["name"] == "황금 돼지"


def test_piggy_redeem_preview():
    p = rewards.preview_redeem(1650, 1400)
    assert p["after"] == 250 and p["to"]["no"] == 1 and not p["reset"]
    p = rewards.preview_redeem(500, 500)
    assert p["after"] == 0 and p["to"]["no"] == 1 and p["reset"]
    assert rewards.preview_redeem(400, 500) == {"ok": False, "short": 100}
    assert rewards.preview_text(800, 500) == ("down", "바꾸면 하늘 돼지 → 분홍 돼지로 내려가요")
    assert rewards.preview_text(1100, 500) == ("same", "바꿔도 하늘 돼지 그대로예요 (600P 남음)")
    assert rewards.preview_text(500, 500) == ("reset", "바꾸면 0P · 분홍 돼지부터 다시 시작해요")
    assert rewards.preview_text(800, 1400) == ("short", "600P 더 모으면 바꿀 수 있어요")


def test_piggy_level_up_only_when_rising():
    assert rewards.level_up(480, 520)["name"] == "하늘 돼지"
    assert rewards.level_up(520, 480) is None and rewards.level_up(600, 700) is None


def test_gold_badge_date_and_kept_after_spending():
    events = [{"date": "2026-10-01", "granted": 3000}, {"date": "2026-10-03", "granted": 600}]
    spends = pd.DataFrame([("S01", "2026-10-02", "500"), ("S01", "2026-10-05", "2300")],
                          columns=["student_id", "date", "points"])
    assert rewards.gold_reached_date(events, spends, "S01") is None  # 3000 → 2500 → 3100
    events.append({"date": "2026-10-04", "granted": 400})
    assert rewards.gold_reached_date(events, spends, "S01") == "2026-10-04"  # 3500, 그 뒤 써도 배지 날짜는 그대로


def test_earning_rules_unchanged():
    assert (rewards.MISSION_POINTS, rewards.JOURNAL_POINTS, rewards.GOAL_BONUS_POINTS, rewards.DAILY_CAP) == (
        100, 20, 300, 200)


@pytest.mark.parametrize("balance, name, line", [
    (800, "하늘 돼지", "민트 돼지까지 600P 남았어요"),
    (0, "분홍 돼지", "하늘 돼지까지 500P 남았어요"),
    (3600, "황금 돼지", "한 학기 동안 꾸준히 모았어요!"),
])
def test_piggy_page(spend_path, monkeypatch, balance, name, line):
    monkeypatch.setattr(rewards, "balance", lambda *args: balance)
    at = open_page()
    text = " ".join(m.value for m in at.markdown)
    assert "내 돼지 저금통" in text and name in text and line in text
    assert not any(b.label.startswith("먹이 주기") for b in at.button)  # 먹이 주기는 없다
    assert ("pig-spark" in text) == (name == "황금 돼지")


def test_piggy_exchange_to_zero_goes_back_to_pink(spend_path, monkeypatch):
    state = {"balance": 500}
    monkeypatch.setattr(rewards, "balance", lambda *args: state["balance"])
    at = view(open_page(), "편의점 1,000원권")
    assert any("분홍 돼지부터 다시 시작해요" in w.value for w in at.warning)
    next(b for b in at.button if b.label == "나에게 교환하기").click().run()
    assert list(store.load_spends(spend_path)["points"]) == ["500"]
    state["balance"] = 0
    at = at.run()
    assert "Lv.1" in " ".join(m.value for m in at.markdown)

