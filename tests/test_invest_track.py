"""투자 탭 동의 기반 2트랙 (invest/tintin_invest_handoff/INVEST_TAB_SPEC.md): 도메인 규칙 · 어댑터 · 화면 흐름."""

import copy
import inspect

import pytest

from conftest import open_app
from engine import broker, invest_track as it, invest_view as iv, store

MARKET = "pages/1_가상_주식시장.py"
PARENT = "pages/13_보호자_투자_동의.py"
DEMO = broker.load_demo()
PROVIDER = broker.MockMarketDataProvider(DEMO)
GUARD = it.make_guardrails(50_000, it.ETF_LARGECAP, True, True, "2026-10-31T09:00:00")
ACTIVE = {"status": it.ACTIVE}


def check(symbol, amount, usage=30_000, consent=ACTIVE, guard=GUARD, side="BUY", **req):
    q, inst = PROVIDER.quote(symbol), PROVIDER.instrument(symbol)
    return it.validate_order({"side": side, "symbol": symbol, "amount": amount, **req}, guard, consent,
                             {"buys": usage}, q, inst, cash=30_000, held_qty=0.16)


# ---------- 7장 검증 예시 ----------

def test_spec_table_fomo_check_required():
    assert check("HB01", 10_000, fomoAcknowledged=False) == "FOMO_CHECK_REQUIRED"


def test_spec_table_ok_after_fomo_and_reason():
    reason = "실적 공시를 확인했어요 영업이익 증가"
    assert check("HB01", 10_000, fomoAcknowledged=True, reason=reason) is None
    assert GUARD["monthlyLimit"] - 30_000 == 20_000 and GUARD["monthlyLimit"] - 40_000 == 10_000
    assert it.qty_label(it.estimate_qty(10_000, 62_200)) == "0.16주"


def test_spec_table_over_per_order():
    assert check("HB01", 30_000, usage=0) == "OVER_PER_ORDER"


def test_spec_table_out_of_scope_small_cap():
    assert check("NR01", 10_000, usage=0) == "OUT_OF_SCOPE"


def test_spec_table_over_monthly():
    assert check("ETF01", 10_000, usage=45_000) == "OVER_MONTHLY"


def test_spec_table_revoked_blocks_buy_allows_sell():
    revoked = {"status": it.REVOKED}
    assert check("ETF01", 5_000, consent=revoked) == "REVOKED"
    assert check("HB01", 0, consent=revoked, side="SELL", qty=0.16) is None
    assert check("ETF01", 5_000, consent={"status": it.NONE}) == "NO_CONSENT"


def test_validation_order_and_other_codes():
    assert check("ETF01", 5_000, margin=True) == "MARGIN_NOT_ALLOWED"
    assert check("HB01", 10_000, fomoAcknowledged=True, reason="짧아요") == "REASON_REQUIRED"
    assert check("ETF01", 20_000, usage=0) is None
    q, inst = PROVIDER.quote("ETF01"), PROVIDER.instrument("ETF01")
    assert it.validate_order({"side": "BUY", "amount": 20_000}, GUARD, ACTIVE, {"buys": 0}, q, inst,
                             cash=10_000) == "INSUFFICIENT_CASH"
    assert set(it.BLOCK_MESSAGES) >= {"NO_CONSENT", "REVOKED", "OVER_MONTHLY", "OVER_PER_ORDER", "OUT_OF_SCOPE",
                                      "FOMO_CHECK_REQUIRED", "REASON_REQUIRED", "MARGIN_NOT_ALLOWED",
                                      "INSUFFICIENT_CASH"}


def test_scopes():
    etf, large, small = ({"type": "ETF"}, {"type": "STOCK", "isLargeCap": True}, {"type": "STOCK", "isLargeCap": False})
    assert [it.in_scope(it.ETF_ONLY, x) for x in (etf, large, small)] == [True, False, False]
    assert [it.in_scope(it.ETF_LARGECAP, x) for x in (etf, large, small)] == [True, True, False]
    assert [it.in_scope(it.ALL, x) for x in (etf, large, small)] == [True, True, True]


def test_guardrails_defaults_and_margin_always_off():
    g = it.make_guardrails(100_000)
    assert g["perOrderLimit"] == 50_000 and g["scope"] == it.ETF_LARGECAP
    assert g["notifyParentOnTrade"] and g["fomoCheck"] and g["marginAllowed"] is False
    assert it.update_guardrails({"guardrails": g, "notifications": []}, scope=it.ALL)["guardrails"]["marginAllowed"] is False


def test_sells_do_not_restore_monthly_limit():
    orders = [{"side": "BUY", "amount": 20_000, "date": "2026-11-02"},
              {"side": "SELL", "amount": 15_000, "date": "2026-11-03"},
              {"side": "BUY", "amount": 9_000, "date": "2026-10-30"}]
    assert it.month_usage(orders, "2026-11") == {"buys": 20_000}


def test_chips_disable_over_per_order_or_left():
    assert it.chip_states(GUARD, {"buys": 30_000}) == [(5_000, True), (10_000, True), (20_000, True)]
    assert it.chip_states(GUARD, {"buys": 40_000}) == [(5_000, True), (10_000, True), (20_000, False)]
    small = it.make_guardrails(20_000)
    assert it.chip_states(small, {"buys": 0}) == [(5_000, True), (10_000, True), (20_000, False)]


# ---------- 6-1 트랙 · 레벨 무관 ----------

def test_track_needs_active_consent_and_linked_account():
    assert it.resolve_invest_track(True, {"status": it.ACTIVE}, True) == it.REAL
    assert it.resolve_invest_track(True, {"status": it.ACTIVE}, False) == it.PRACTICE
    for status in (it.NONE, it.PENDING, it.REJECTED, it.REVOKED):
        assert it.resolve_invest_track(True, {"status": status}, True) == it.PRACTICE


def test_level_never_decides_track_limit_or_scope():
    """레벨(단계)은 함수 입력에 들어가지도 않는다. flag가 꺼졌을 때만 예전 레벨 결과를 쓴다."""
    for fn in (it.resolve_invest_track, it.validate_order, it.make_guardrails, it.chip_states):
        params = inspect.signature(fn).parameters
        assert not any(p in params for p in ("level", "stage", "exp")), fn
    for stage in (1, 2, 3):
        level = it.legacy_level_track(stage)
        assert it.resolve_invest_track(True, {"status": it.NONE}, False, level) == it.PRACTICE
        assert it.resolve_invest_track(True, {"status": it.ACTIVE}, True, level) == it.REAL
    assert it.resolve_invest_track(False, {"status": it.ACTIVE}, True, it.legacy_level_track(3)) == it.PRACTICE


# ---------- 6-2 동의 상태 전이 ----------

def test_transitions_history_and_notices():
    s = it.new_state("S01")
    it.transition(s, "REQUEST", at="2026-11-01T10:00:00", message="해 보고 싶어요", report={"weeks": 9})
    assert s["consent"]["status"] == it.PENDING and s["consent"]["report_snapshot"] == {"weeks": 9}
    broker.open_real_account(s, broker.MockBrokerAdapter(), at="2026-11-02T10:00:00")
    assert s["consent"]["status"] == it.ACTIVE and it.account_linked(s)
    it.transition(s, "REVOKE", at="2026-11-03T10:00:00")
    assert [h["to"] for h in s["history"]] == [it.PENDING, it.ACTIVE, it.REVOKED]
    assert {n["to"] for n in s["notifications"]} == {"STUDENT", "PARENT"}
    assert len(s["notifications"]) == 6  # 전이마다 양쪽에 알림
    assert it.can_view_real(s)


def test_bad_transitions_and_7_day_cooldown():
    s = it.new_state("S01")
    with pytest.raises(ValueError):
        it.transition(s, "APPROVE", account_id="X")
    it.transition(s, "REQUEST", at="2026-11-01T10:00:00")
    with pytest.raises(ValueError):
        it.transition(s, "REQUEST", at="2026-11-01T11:00:00")  # PENDING에서 또 요청 불가
    it.transition(s, "REJECT", at="2026-11-02T10:00:00")
    assert it.cooldown_left(s["consent"], "2026-11-05") == 4
    with pytest.raises(ValueError):
        it.transition(s, "REQUEST", at="2026-11-05T10:00:00")
    it.transition(s, "REQUEST", at="2026-11-09T10:00:00")
    assert s["consent"]["status"] == it.PENDING


# ---------- 6-4 · 6-6 ----------

def demo_real_state():
    s = it.new_state("U00001")
    s["consent"]["status"] = it.ACTIVE
    s["guardrails"] = copy.deepcopy(GUARD)
    s["real"] = copy.deepcopy(DEMO["real"])
    s["watch"] = copy.deepcopy(DEMO["watch"])
    return s


def test_mock_broker_order_flow_updates_account_and_notifies_parent():
    s = demo_real_state()
    req = {"side": "BUY", "symbol": "HB01", "amount": 10_000, "fomoAcknowledged": True,
           "reason": "실적 공시를 확인했어요 영업이익 증가"}
    result = broker.submit_real_order(s, broker.MockBrokerAdapter(), PROVIDER, req, "2026-11-13", 30_000)
    assert result["ok"] and result["filledQty"] == pytest.approx(0.1607, abs=1e-4)
    assert it.month_usage(s["real"]["orders"], "2026-11") == {"buys": 40_000}
    assert s["real"]["funded"] == 40_000 and s["real"]["cash"] == 0
    parent = [n["text"] for n in s["notifications"] if n["to"] == "PARENT"]
    assert parent and "이유: 실적 공시를 확인했어요" in parent[-1]
    blocked = broker.submit_real_order(s, broker.MockBrokerAdapter(), PROVIDER, {**req, "amount": 20_000},
                                       "2026-11-13", 30_000)
    assert blocked == {"ok": False, "code": "OVER_MONTHLY"}


def test_real_broker_is_interface_only():
    with pytest.raises(NotImplementedError):
        broker.RealBrokerAdapter().place_order({}, {}, {}, "2026-11-13")


def test_sell_allowed_after_revoke_and_proceeds_go_to_cash():
    s = demo_real_state()
    it.transition(s, "REVOKE")
    req = {"side": "SELL", "symbol": "HB01", "qty": 0.08}
    result = broker.submit_real_order(s, broker.MockBrokerAdapter(), PROVIDER, req, "2026-11-13", 0)
    assert result["ok"] and s["real"]["cash"] == round(0.08 * 62_200)
    assert s["real"]["holdings"]["HB01"]["qty"] == pytest.approx(0.15997 - 0.08)
    buy = {"side": "BUY", "symbol": "ETF01", "amount": 5_000}
    assert broker.submit_real_order(s, broker.MockBrokerAdapter(), PROVIDER, buy, "2026-11-13", 30_000)["code"] == "REVOKED"


def test_change_request_is_student_written_and_parent_decides():
    s = demo_real_state()
    with pytest.raises(ValueError):
        it.request_change(s, "", 100_000)
    r = it.request_change(s, "ETF를 매달 나눠 사고 싶어요", 100_000, None, True, at="2026-11-13T10:00:00")
    with pytest.raises(ValueError):  # 같은 내용은 7일에 한 번
        it.request_change(s, "다시 부탁해요", 100_000, None, at="2026-11-15T10:00:00")
    assert s["guardrails"]["monthlyLimit"] == 50_000  # 요청만으로는 바뀌지 않는다
    it.decide_change(s, r["id"], "ADJUSTED", "7만 원은 없어서 10만 원 대신 범위는 그대로", monthly_limit=100_000)
    assert s["guardrails"]["monthlyLimit"] == 100_000 and s["guardrails"]["perOrderLimit"] == 50_000
    assert "메모" in s["notifications"][-1]["text"] and s["notifications"][-1]["to"] == "STUDENT"
    r2 = it.request_change(s, "전체 종목도 보고 싶어요", None, it.ALL, at="2026-11-13T11:00:00")
    it.decide_change(s, r2["id"], "DECLINED")
    assert s["guardrails"]["scope"] == it.ETF_LARGECAP


def test_monthly_record_matches_mockup():
    s = demo_real_state()
    view = iv.real_home(s, PROVIDER, "2026-11-13")
    r = view["record"]
    assert (r["journalCount"], r["fomoWaitCount"], r["reasonRate"], r["maxWeightPct"]) == (3, 2, 1.0, 68)
    assert view["summary"]["value"] == 31_150 and view["summary"]["changePct"] == 1.1
    assert view["usage"] == {"buys": 30_000}
    assert [row["sub"] for row in view["rows"]] == ["0.6주 · 21,200원 (소수점)", "0.16주 · 9,950원 (소수점)"]


def test_wait_result_uses_next_trading_day_close():
    w = {"symbol": "X", "addedAt": "2026-11-06", "priceAtAdd": 10_000}
    assert it.wait_result(w, [("2026-11-06", 10_000)]) is None
    assert it.wait_result(w, [("2026-11-06", 10_000), ("2026-11-07", 9_500)])["diff_pct"] == -5.0


def test_practice_report_has_no_score_numbers():
    trades, prices = store.load_trades(), store.load_prices()
    student = next(s for s in store.load_students() if s["student_id"] == "S01")
    report = iv.practice_report(student, trades, prices, it.new_state("S01"), store.load_questions(),
                                store.load_news_quiz())
    assert set(report["skills"]) == {"knowledge", "risk", "decision"}
    assert all(isinstance(v, bool) for v in report["skills"].values())
    assert report["weeks"] >= 1 and report["checklistRate"] is None


def test_scenario_provider_wraps_existing_prices():
    names, prices = store.load_ticker_names(), store.load_prices()
    p = broker.PriceTableProvider(names, prices, "scenario")
    q = p.quote("005930")
    assert q["price"] == int(prices["005930"]["close"].iloc[-1]) and "연습용 가상 시세" in q["label"]
    assert p.instrument("005930")["isLargeCap"] and p.headlines("005930") == []
    assert len(p.history("005930", 30)) == min(30, len(prices["005930"]))


def test_no_buy_advice_words_in_messages():
    words = ["사세요", "추천", "꼭 사", "오를 거", "매수하세요"]
    texts = list(it.BLOCK_MESSAGES.values()) + [iv.fomo_line({"days": 3, "pct": -11}, 11.2)[1],
                                               iv.fomo_line(None, 11.2)[1]]
    assert not any(w in t for t in texts for w in words)


# ---------- 화면 ----------

def run(at):
    at = at.run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(m.value for m in at.markdown)


def press(at, label):
    next(b for b in at.button if b.label == label).click()
    return run(at)


def test_practice_home_mock_matches_mockup():
    at = open_app(MARKET, query={"mock": "1"})
    assert not at.exception, at.exception
    t = texts(at)
    for part in ["연습 모드 · 가상 머니", "1,032,400원", "+3.2%", "시작 1,000,000원", "투자 60% · 현금 40%",
                 "최대 비중 41% (ETF)", "국내 대표지수 ETF", "12주 · 423,000원", "누리바이오", "오늘 +15%",
                 "<b class='hl'>진짜</b>"]:
        assert part in t, part
    assert any(b.label == "부모님께 동의 요청하기" for b in at.button)


def test_practice_order_checklist_changes_cta():
    at = open_app(MARKET, query={"mock": "1"})
    at = press(at, "누리바이오 보기")
    t = texts(at)
    assert "48,300원" in t and "실제 시세 · 15분 지연 · 11/13 14:20 기준" in t and "오늘 급등" in t
    assert "임상시험 결과 발표 일정 안내" in t and "0/3" in t
    assert any(b.label == "체크리스트 없이 가상으로 1주 사기" for b in at.button)
    for box in at.checkbox:
        box.check()
    at = run(at)
    assert "3/3" in texts(at) and any(b.label == "가상으로 1주 사기" for b in at.button)


def test_full_consent_flow_in_mock_without_saving(tmp_path):
    at = open_app(MARKET, query={"mock": "1"})
    at = press(at, "부모님께 동의 요청하기")
    t = texts(at)
    assert "부모님께 보낼 연습 리포트" in t and "9주" in t and "92%" in t and "잘하는 중" in t
    assert "87" not in t and "38 → 55" not in t  # 역량 점수 숫자는 보여 주지 않는다
    at = press(at, "부모님께 요청 보내기")
    assert any(b.label == "다시 알림 보내기" for b in at.button)
    at.switch_page(PARENT)
    at = run(at)
    assert at.title[0].value == "민지의 실전 투자 동의" and "아이의 연습 리포트" in texts(at)
    at = press(at, "동의하고 계좌 개설로 이동")
    assert any("계좌" in s.value for s in at.success)
    at.switch_page(MARKET)
    at = run(at)
    assert "실전 모드 · 부모님 동의" in texts(at) and "실제 돈" in texts(at)
    assert not store.INVEST_PATH.exists()  # 시안은 저장하지 않는다


def test_real_home_mock_matches_mockup():
    at = open_app(MARKET, query={"mock": "real"})
    assert not at.exception, at.exception
    t = texts(at)
    for part in ["실전 모드 · 부모님 동의", "연계 증권 계좌 (미성년자)", "실제 돈", "31,150원", "+1.1%",
                 "30,000 / 50,000원", "부모님 설정 · ETF + 대형주 · 1회 25,000원까지", "0.6주 · 21,200원 (소수점)",
                 "오늘 +11%", "투자일지 <b>3회</b>", "급등주 지켜보기 <b>2회</b>", "근거 쓰고 산 비율 <b>100%</b>",
                 "최대 비중 <b>68%</b>", "한도와 종목 범위는 레벨로 바뀌지 않아요"]:
        assert part in t, part


def test_real_order_fomo_then_reason_then_mock_fill():
    at = open_app(MARKET, query={"mock": "real"})
    at = press(at, "한빛전자 더 사기")
    t = texts(at)
    assert "잠깐! 오늘 +11.2% 오른 종목이에요" in t and "3일 뒤 -11%였던 적이 있어요" in " ".join(
        m.value for m in at.markdown) + " ".join(str(e.value) for e in at.get("text"))
    at = press(at, "근거 쓰고 계속하기")
    labels = {b.label: b.disabled for b in at.button}
    assert labels["5,000원"] is False and labels["20,000원"] is False and "실제로 5,000원 사기" in labels
    at = press(at, "10,000원")
    t = texts(at)
    assert "약 0.16주" in t and "20,000 → 10,000원" in t and "주문 즉시 전송" in t
    at = press(at, "실제로 10,000원 사기")
    assert any(it.BLOCK_MESSAGES["REASON_REQUIRED"] in e.value for e in at.error)
    at.text_area[0].set_value("실적 공시를 확인했어요 영업이익 증가")
    at = press(at, "실제로 10,000원 사기")
    assert "40,000 / 50,000원" in texts(at)


def test_real_order_fomo_wait_adds_watch():
    at = open_app(MARKET, query={"mock": "real"})
    at = press(at, "한빛전자 더 사기")
    at = press(at, "오늘은 지켜보기 (관심 종목에 담기)")
    assert "연계 증권 계좌 (미성년자)" in texts(at)


def test_real_data_flow_saves_state_and_level_does_not_matter(tmp_path, monkeypatch):
    unlocks = tmp_path / "unlocks.csv"
    unlocks.write_text("student_id,stage,date\n", encoding="utf-8")  # 1단계 (레벨 가장 낮음)
    monkeypatch.setattr(store, "UNLOCKS_PATH", unlocks)
    at = open_app(MARKET)
    assert "연습 모드 · 가상 머니" in texts(at)
    assert not at.radio[0].disabled  # 실제 시세 연습은 레벨과 무관하게 누구나
    at = press(at, "부모님께 동의 요청하기")
    at = press(at, "부모님께 요청 보내기")
    assert store.load_invest("S01")["consent"]["status"] == it.PENDING
    at.switch_page(PARENT)
    at = run(at)
    at = press(at, "동의하고 계좌 개설로 이동")
    saved = store.load_invest("S01")
    assert saved["consent"]["status"] == it.ACTIVE and saved["guardrails"]["monthlyLimit"] == 50_000
    at.switch_page(MARKET)
    at = run(at)
    assert "실전 모드 · 부모님 동의" in texts(at)
    assert unlock_stage(unlocks) == 1  # 레벨은 그대로 1단계인데 실전 모드


def unlock_stage(path):
    from engine import unlock
    return unlock.stage(store.load_unlocks(path), "S01")


def test_flag_off_returns_old_level_screen(monkeypatch):
    import config
    monkeypatch.setattr(config, "INVEST_CONSENT_TRACK", False)
    at = open_app(MARKET)
    assert not at.exception, at.exception
    assert "연습 모드 · 가상 머니" not in texts(at)
    assert any(b.label == "주문 넣기" for b in at.button)


def test_parent_page_without_request():
    at = open_app(PARENT)
    assert not at.exception, at.exception
    assert any("아직 실전 투자 동의 요청이 없어요" in i.value for i in at.info)


def test_tab_label_is_invest():
    import ui_common as ui
    assert ("market", ui.MARKET, "투자", "chart", "green") in ui.NAV_ITEMS
