"""실전투자 진입 안전장치 (safety/teengrow_real_safety/REAL_SAFETY_SPEC.md 6장 + 앱 화면 흐름)."""

from datetime import date, datetime, timedelta

import pytest

import config
from conftest import open_app
from engine import invest_track as it, real_safety as rs, store, updater

MARKET = "pages/1_가상_주식시장.py"
PARENT = "pages/13_보호자_투자_동의.py"
NOW = datetime(2026, 11, 16, 10, 21)
TODAY_CHECK = rs.SafetyState(last_check_at=datetime(2026, 11, 16, 9, 0), last_check_version=config.REAL_SAFETY_VERSION)


# ---------- 언제 체크리스트가 나오나 (7) ----------

@pytest.mark.parametrize("state,kw,expected", [
    (rs.SafetyState(), {}, True),                                                              # 처음
    (TODAY_CHECK, {}, False),                                                                  # 오늘 이미 함
    (rs.SafetyState(datetime(2026, 11, 15, 23, 59), config.REAL_SAFETY_VERSION), {}, True),    # 자정 지나면 다시
    (rs.SafetyState(datetime(2026, 11, 16, 9, 0), config.REAL_SAFETY_VERSION - 1), {}, True),  # 문구 버전 바뀜
    (TODAY_CHECK, {"settings_changed_at": datetime(2026, 11, 16, 9, 30)}, True),              # 체크 뒤 부모가 설정 변경
    (TODAY_CHECK, {"settings_changed_at": datetime(2026, 11, 16, 8, 0)}, False),              # 체크 전 변경은 무관
    (TODAY_CHECK, {"consent_activated_at": datetime(2026, 11, 16, 10, 0)}, True),             # 동의를 새로 받음
])
def test_needs_checklist(state, kw, expected):
    assert rs.needs_checklist(state, NOW, **kw) is expected


# ---------- 진입 경로 (5) ----------

@pytest.mark.parametrize("consent,state,route", [
    ("PENDING", rs.SafetyState(), ["LOCKED"]),
    ("NONE", TODAY_CHECK, ["LOCKED"]),
    ("REVOKED", rs.SafetyState(), ["SWITCH", "REAL_VIEW_SELL"]),
    ("ACTIVE", rs.SafetyState(), ["SWITCH", "CHECKLIST", "REAL"]),
    ("ACTIVE", TODAY_CHECK, ["SWITCH", "REAL"]),
])
def test_entry_route(consent, state, route):
    assert rs.entry_route(consent, state, NOW) == route


# ---------- 문구 ----------

def test_switch_sheet_copy():
    assert rs.switch_sheet_copy(rs.SafetyState(), NOW)["cta"] == "안전 체크하고 들어가기"
    c = rs.switch_sheet_copy(TODAY_CHECK, NOW)
    assert c["cta"] == "실전으로 들어가기" and "오늘 오전 9:00에 안전 체크를 마쳤어요." == c["notice_b"]


def test_items_filled_with_real_values():
    items = rs.render_items(20000, 50000, 25000, "eod", date(2026, 11, 13))
    assert len(items) == 6 and [i["no"] for i in items] == [1, 2, 3, 4, 5, 6]
    assert items[2]["limit"]["text"] == "남은 한도 20,000원 / 50,000원 · 한 번에 25,000원까지"
    assert items[5]["title"] == "가격은 전날 종가예요" and "11월 13일(금) 종가" in items[5]["body"]
    assert all("{" not in i["title"] + i["body"] for i in items)


def test_items_follow_quote_source_switch():
    assert rs.render_items(20000, 50000, 25000, "broker")[5]["title"] == "가격은 계속 움직여요"


# ---------- 버튼 (4) ----------

@pytest.mark.parametrize("checked,ok,label", [
    ([True] * 6, True, "실전 화면으로 들어가기"),
    ([True] * 5 + [False], False, "1개 더 확인하면 열려요"),
    ([True, True] + [False] * 4, False, "4개 더 확인하면 열려요"),
    ([True] * 5, False, "1개 더 확인하면 열려요"),  # 개수가 모자라면 통과 못 함
])
def test_can_enter(checked, ok, label):
    assert rs.can_enter(checked) is ok and rs.cta_label(checked) == label


# ---------- 들어간 뒤 ----------

def test_record_check_then_same_day_skips_checklist():
    s = rs.record_check(rs.SafetyState(), NOW)
    assert s.in_real_mode and s.last_check_at == NOW and s.last_check_version == config.REAL_SAFETY_VERSION
    assert rs.entry_route("ACTIVE", rs.exit_to_practice(s), NOW + timedelta(hours=2)) == ["SWITCH", "REAL"]


def test_idle_auto_exit():
    s = rs.record_check(rs.SafetyState(), NOW)
    assert not rs.should_auto_exit(s, NOW + timedelta(minutes=9, seconds=59))
    assert rs.should_auto_exit(s, NOW + timedelta(minutes=10))
    assert not rs.should_auto_exit(rs.touch(s, NOW + timedelta(minutes=8)), NOW + timedelta(minutes=12))
    assert not rs.should_auto_exit(rs.exit_to_practice(s), NOW + timedelta(hours=1))
    assert rs.touch(rs.SafetyState(), NOW) == rs.SafetyState()  # 연습에선 무시


def test_parent_badge():
    assert rs.parent_badge(rs.record_check(rs.SafetyState(), NOW), NOW) == "오늘 안전 체크 완료 · 오전 10:21"
    assert rs.parent_badge(TODAY_CHECK, NOW + timedelta(days=1)) == "오늘은 아직 실전에 들어가지 않았어요"


def test_saved_values_and_log():
    state = {"consent": {"status": "ACTIVE", "decided_at": "2026-11-16T09:30:00"},
             "guardrails": {"updatedAt": "2026-11-16T09:40:00"}}
    rs.to_saved(state, rs.record_check(rs.SafetyState(), NOW))
    assert state["safety"] == {"last_check_at": "2026-11-16T10:21:00", "last_check_version": config.REAL_SAFETY_VERSION}
    assert len(state["safety_log"]) == 1
    loaded = rs.from_saved(state)
    assert loaded.last_check_at == NOW and not loaded.in_real_mode  # 진행 중 상태는 저장하지 않는다
    assert rs.settings_changed_at(state) == datetime(2026, 11, 16, 9, 40)
    assert rs.consent_activated_at(state) == datetime(2026, 11, 16, 9, 30)


# ---------- 앱 화면 흐름 ----------

def run(at):
    at = at.run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(m.value for m in at.markdown)


def click(at, key):
    next(b for b in at.button if b.key == key).click()
    return run(at)


def tap_home_real(at):
    at.segmented_control(key="inv-mode-widget").set_value("실전 계좌")
    return run(at)


def test_active_student_starts_in_practice_and_sheet_comes_first():
    at = open_app(MARKET, query={"mock": "safety"})
    assert not at.exception, at.exception
    assert "연습 모드 · 가상 머니" in texts(at) and "실전으로 바꿀까요?" not in texts(at)
    at = tap_home_real(at)
    t = texts(at)
    assert "실전으로 바꿀까요?" in t and "오늘 안전 체크를 아직 안 했어요." in t and "role='dialog'" in t
    assert next(b for b in at.button if b.key == "switch-go").label == "● 안전 체크하고 들어가기"


def test_checklist_needs_all_six_then_real_then_back_and_sheet_only():
    at = tap_home_real(open_app(MARKET, query={"mock": "safety"}))
    at = click(at, "switch-go")
    t = texts(at)
    assert "실전투자 안전 체크리스트" in t and "0 / 6" in t and "남은 한도 <b>20,000원</b>" in t and "11월 13일(금) 종가" in t
    assert not any("모두 확인" in b.label for b in at.button)
    for box in at.checkbox[:5]:
        box.check()
    at = run(at)
    go = next(b for b in at.button if b.key == "check-go")
    assert go.disabled and go.label == "● 1개 더 확인하면 열려요"
    at.checkbox[5].check()
    at = run(at)
    at = click(at, "check-go")
    t = texts(at)
    assert "실전 모드 · 부모님 동의" in t and "real-band" in t  # 실전 화면 + 맨 위 남색 띠
    at.segmented_control(key="inv-mode-widget").set_value("연습 모드")  # 실전 → 연습은 확인 없이 바로
    at = run(at)
    assert "연습 모드 · 가상 머니" in texts(at) and "실전으로 바꿀까요?" not in texts(at)
    at = tap_home_real(at)
    assert "오늘 " in texts(at) and next(b for b in at.button if b.key == "switch-go").label == "● 실전으로 들어가기"
    at = click(at, "switch-go")
    assert "실전 모드 · 부모님 동의" in texts(at)  # 오늘 이미 체크 → 시트만


def test_practice_only_resets_checks():
    at = click(tap_home_real(open_app(MARKET, query={"mock": "safety"})), "switch-go")
    for box in at.checkbox[:3]:
        box.check()
    at = run(at)
    at = click(at, "check-stay")
    assert "연습 모드 · 가상 머니" in texts(at)
    at = click(tap_home_real(at), "switch-go")
    assert "0 / 6" in texts(at) and not any(b.value for b in at.checkbox)  # 다음엔 0/6부터


def test_stock_detail_entry_also_goes_through_sheet():
    at = open_app(MARKET, query={"mock": "safety"})
    at.session_state["inv-screen"] = {"screen": "stock", "symbol": "HB01"}
    at = run(at)
    at.segmented_control(key="stock-mode-HB01").set_value("● 실전 · 부모님 동의")
    at = run(at)
    assert "실전으로 바꿀까요?" in texts(at)


def test_real_screen_cannot_open_directly():
    at = open_app(MARKET, query={"mock": "safety"})
    at.session_state["inv-screen"] = {"screen": "order", "symbol": "HB01"}
    at = run(at)
    assert "연습 모드 · 가상 머니" in texts(at) and "실제 돈으로 거래해요" not in texts(at)


def test_idle_10_minutes_returns_to_practice_with_toast():
    at = open_app(MARKET, query={"mock": "real"})
    assert "실전 모드 · 부모님 동의" in texts(at)
    at.session_state["inv-safety"] = {"in_real_mode": True,
                                      "last_real_activity_at": updater.now_kst() - timedelta(minutes=11)}
    at = run(at)
    assert "연습 모드 · 가상 머니" in texts(at)
    assert any("10분 동안 쉬어서 연습으로 돌아왔어요" in t.value for t in at.toast)


def test_not_consented_is_locked():
    at = open_app(MARKET, query={"mock": "1"})
    at.session_state["inv-screen"] = {"screen": "stock", "symbol": "NR01"}
    at = run(at)
    at.segmented_control(key="stock-mode-NR01").set_value("● 실전 · 부모님 동의")
    at = run(at)
    assert "NO_CONSENT" in texts(at) and "실전으로 바꿀까요?" not in texts(at)


def test_settings_change_after_check_requires_checklist_again():
    at = open_app(MARKET, query={"mock": "real"})  # 오늘 체크한 상태
    box = at.session_state["invest-mock-state"]["state"]
    box["guardrails"] = it.make_guardrails(100_000, it.ETF_LARGECAP,
                                           at=(updater.now_kst() + timedelta(minutes=1)).isoformat(timespec="seconds"))
    at.segmented_control(key="inv-mode-widget").set_value("연습 모드")
    at = run(at)
    at = click(tap_home_real(at), "switch-go")
    assert "실전투자 안전 체크리스트" in texts(at)


def test_real_data_check_is_saved_and_parent_sees_badge(monkeypatch):
    state = it.new_state("S01")
    it.transition(state, "REQUEST", message="해 보고 싶어요", report=None)
    state["guardrails"] = it.make_guardrails(at="2026-11-01T09:00:00")
    from engine import broker
    broker.open_real_account(state, broker.MockBrokerAdapter(), at="2026-11-01T09:00:00")
    store.save_invest("S01", state)
    at = open_app(PARENT)
    assert "오늘은 아직 실전에 들어가지 않았어요" in texts(at)
    at.switch_page(MARKET)
    at = run(at)
    at = click(tap_home_real(at), "switch-go")
    for box in at.checkbox:
        box.check()
    at = run(at)
    at = click(at, "check-go")
    saved = store.load_invest("S01")
    assert saved["safety"]["last_check_version"] == config.REAL_SAFETY_VERSION and len(saved["safety_log"]) == 1
    at.switch_page(PARENT)
    at = run(at)
    assert "오늘 안전 체크 완료" in texts(at)


def test_flag_off_goes_straight_to_real(monkeypatch):
    monkeypatch.setattr(config, "REAL_SAFETY", False)
    at = tap_home_real(open_app(MARKET, query={"mock": "safety"}))
    assert "실전 모드 · 부모님 동의" in texts(at) and "실전으로 바꿀까요?" not in texts(at)
