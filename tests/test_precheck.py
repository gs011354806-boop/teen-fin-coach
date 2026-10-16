"""15번 사기 전 1분 점검: 주문 저장 전에 감지 기준으로 미리 보고, 걸리면 AI 질문 후 학생이 결정."""

import pytest

from conftest import open_app
from engine import detect, store
from llm import client

STUDENTS = {s["student_id"]: s for s in store.load_students()}
MARKET = "pages/1_가상_주식시장.py"


def scenario():
    return store.load_trades(store.TRADES_PATH), store.load_prices()


def test_precheck_flags_concentration_and_no_reason_for_minji():
    trades, prices = scenario()
    detection, past = detect.precheck(trades, prices, STUDENTS["S01"], "005930", 2, 56800, "", "2026-10-02")
    assert set(detection["patterns"]) == {detect.CONCENTRATION, detect.NO_REASON}
    assert past  # 민지는 전에도 같은 패턴이 있었다
    assert len(trades) == len(store.load_trades(store.TRADES_PATH))  # 거래는 저장하지 않는다


def test_precheck_passes_small_reasoned_buy():
    trades, prices = scenario()
    detection, _ = detect.precheck(trades, prices, STUDENTS["S03"], "005930", 1, 56800,
                                   "반도체 수요 기사를 읽고 한 주만 나눠 담아요", "2026-10-02")
    assert detection["patterns"] == []


def test_default_question_has_fact_and_no_advice():
    trades, prices = scenario()
    detection, _ = detect.precheck(trades, prices, STUDENTS["S01"], "005930", 2, 56800, "", "2026-10-02")
    question = detect.precheck_default_question(detection, "삼성전자")
    assert "비중" in question and question.endswith("볼까요?")
    client.validate("precheck_question", {"question": question})  # 존댓말·금지 표현 검사 통과


@pytest.mark.parametrize("bad", ["삼성전자는 사지 마세요.", "지금은 멈추세요."])
def test_do_not_buy_advice_is_blocked(bad):
    with pytest.raises(ValueError):
        client.validate("precheck_question", {"question": bad})


@pytest.fixture
def files(tmp_path, monkeypatch):
    trades = tmp_path / "trades.csv"
    trades.write_text(store.TRADES_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(store, "TRADES_PATH", trades)
    monkeypatch.setattr(store, "PRECHECK_PATH", tmp_path / "prechecks.csv")
    monkeypatch.setattr(client, "ask", lambda name, payload, default=None, check=None: dict(default))
    return trades


def submit_buy(qty, journal=""):
    at = open_app(MARKET)  # 민지, 삼성전자
    at.number_input[0].set_value(qty)
    at.text_area[0].set_value(journal)
    next(b for b in at.button if b.label == "주문 넣기").click()
    at = at.run()
    assert not at.exception, at.exception
    return at


def test_risky_buy_stops_for_check_then_buy(files):
    before = len(store.load_trades(files))
    at = submit_buy(2)
    assert len(store.load_trades(files)) == before  # 아직 저장 안 됨
    assert any("주문 전 1분 점검" in m.value for m in at.markdown)
    assert any("볼까요?" in i.value for i in at.info)

    at.text_area(key="precheck_reason").set_value("배당이 꾸준한 회사라서")
    next(b for b in at.button if b.label == "이대로 주문하기").click()
    at = at.run()
    trades = store.load_trades(files)
    assert len(trades) == before + 1 and trades.iloc[-1]["journal"] == "배당이 꾸준한 회사라서"
    log = store.load_prechecks()
    assert list(log["decision"]) == ["BUY"] and log.iloc[0]["trade_id"] == trades.iloc[-1]["trade_id"]
    assert set(log.iloc[0]["patterns"].split("|")) == {"몰빵", "근거 없음"}


def test_risky_buy_can_be_cancelled(files):
    before = len(store.load_trades(files))
    at = submit_buy(2)
    next(b for b in at.button if b.label == "다시 생각할게요").click()
    at = at.run()
    assert len(store.load_trades(files)) == before
    assert list(store.load_prechecks()["decision"]) == ["CANCEL"]
    assert any("주문을 취소했어요" in s.value for s in at.success)


def test_safe_buy_goes_straight_through(files):
    at = open_app(MARKET)
    at.sidebar.selectbox[0].select("서연 (고1)")
    at = at.run()
    at.text_area[0].set_value("반도체 수요 기사를 읽고 한 주만 나눠 담아요")
    next(b for b in at.button if b.label == "주문 넣기").click()
    at = at.run()
    assert store.load_trades(files).iloc[-1]["student_id"] == "S03"
    assert len(store.load_prechecks()) == 0  # 점검 없이 바로 주문


def test_precheck_facts_are_written_before_buying():
    trades, prices = scenario()
    detection, _ = detect.precheck(trades, prices, STUDENTS["S01"], "005930", 2, 56800, "", "2026-10-02")
    facts = detect.fact_sentences(detection, "삼성전자", before=True)
    assert facts == ["이번에 사면 삼성전자 비중이 총자산의 95%가 돼요.", "투자 일지가 비어 있어요."]


# --- 시연 모드 저장 응답 ---

def test_demo_key_is_pattern_combo_in_fixed_order():
    assert detect.precheck_demo_key(["근거 없음", "몰빵"]) == "몰빵|근거 없음"


def test_saved_precheck_questions_cover_every_combo_without_numbers():
    import itertools
    if not store.DEMO_PATH.exists():
        pytest.skip("demo_responses.json 없음")
    names = store.load_ticker_names().values()
    combos = {detect.precheck_demo_key(c) for r in (1, 2, 3)
              for c in itertools.combinations(detect.PATTERNS, r)}
    for student_id, entry in store.load_demo()["students"].items():
        saved = entry["responses"]["precheck_question"]
        assert set(saved) == combos, student_id
        for response in saved.values():
            q = client.validate("precheck_question", response)["question"]
            assert not any(c.isdigit() for c in q) and not any(n in q for n in names), q


def test_demo_on_uses_saved_precheck_question(files, monkeypatch):
    def failing(name, payload, **kwargs):
        raise client.QuotaExceededError("429")
    monkeypatch.setattr(client, "ask", failing)
    at = open_app(MARKET)
    at.session_state["demo_mode"] = True
    at.number_input[0].set_value(2)
    next(b for b in at.button if b.label == "주문 넣기").click()
    at = at.run()
    saved = store.demo_response("S01", "precheck_question", "몰빵|근거 없음")["question"]
    assert any(saved in i.value for i in at.info)
