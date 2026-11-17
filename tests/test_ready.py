"""실전 준비 기준 (criteria/teengrow_ready/READY_SPEC.md 7장). 앞쪽 21개는 reference 테스트 그대로."""
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import pytest

from engine import ready as rd, store

T0 = datetime(2026, 10, 12, 16, 0)        # 월요일
NOW = datetime(2026, 11, 17, 14, 0)


def tr(i, day, code="005930", side="BUY", pnl=None, hour=16):
    return rd.Trade(f"t{i}", T0.replace(hour=hour) + timedelta(days=day), code, side, pnl)


def full_trades():
    """5주에 걸쳐 12회, 팔기 4회(손실 1회 포함)."""
    plan = [(0, "BUY"), (2, "BUY"), (7, "SELL"), (9, "BUY"), (14, "BUY"), (16, "SELL"),
            (21, "BUY"), (23, "SELL"), (28, "BUY"), (30, "SELL"), (31, "BUY"), (33, "BUY")]
    return [tr(i, d, f"00{i:04d}", s, pnl=(-4200 if i == 2 else 2600) if s == "SELL" else None) for i, (d, s) in enumerate(plan)]


def journals(n, base="수출이 늘면 실적이 좋아질 것 같아요"):
    topics = ["반도체", "금리", "환율", "배당", "분산", "ETF", "실적", "뉴스", "가격", "비중"]
    return [rd.Journal(T0 + timedelta(days=i * 3), f"{topics[i]} 때문에 {i}번째로 생각을 정리했어요") for i in range(n)]


def refl(tid, kind, day=20, ok=True):
    a = ("많이 오르고 있어서 더 오를 줄 알았어요", "다음 날부터 내려서 손해를 보고 팔았어요",
         "이유부터 찾고 하루 기다렸다가 정할래요") if ok else ("몰라", "그냥", "다음엔 잘")
    return rd.Reflection(T0 + timedelta(days=day), tid, kind, a)


QUIZ_OK = [rd.QuizAttempt(T0 + timedelta(days=30), 9)]


def evaluate(**kw):
    args = dict(trades=full_trades(), journals=journals(9), refls=[refl("t2", "loss"), refl("t5", "gain", 25)], quiz=QUIZ_OK)
    args.update(kw)
    return rd.evaluate(NOW, args["trades"], args["journals"], args["refls"], args["quiz"], kw.get("state", rd.ReadyState()))


# ── 전체 ─────────────────────────────────────────────────────
def test_all_done_can_request():
    r = evaluate()
    assert r.all_done and r.can_request_consent and r.done_count == 5 and r.remaining() == []


def test_returns_and_codes_do_not_matter():
    lossy = [rd.Trade(t.id, t.at, t.code, t.side, -99999 if t.side == "SELL" else None) for t in full_trades()]
    assert evaluate(trades=lossy).all_done        # 전부 손실이어도 기준은 같다


# ── 1. 연습 기간 ─────────────────────────────────────────────
def test_period_needs_28_days_and_3_weeks():
    burst = [tr(i, 0, f"{i:06d}", "BUY") for i in range(2)]
    r = rd.evaluate(T0 + timedelta(days=40), burst, [], [], [])
    p = r.items[0]
    assert not p.done and p.parts[0][1] == 40 and p.parts[1][1] == 1   # 날짜는 지났지만 한 주에만 거래


def test_period_counts_iso_weeks():
    ts = [tr(0, 0), tr(1, 6, side="SELL"), tr(2, 13), tr(3, 28)]        # 월, 일(같은 주), 다음 주 일, 5주 뒤
    counted = rd.count_trades(ts)
    assert len({e.day.isocalendar()[:2] for e in counted}) == 3


# ── 2. 거래 세기 ─────────────────────────────────────────────
def test_daily_cap_two():
    ts = [tr(i, 0, f"{i:06d}", hour=9 + i) for i in range(5)]
    assert len(rd.count_trades(ts)) == 2


def test_same_day_roundtrip_counts_once_not_as_sell():
    ts = [tr(0, 0, "005930", "BUY", hour=9), tr(1, 0, "005930", "SELL", pnl=100, hour=10), tr(2, 0, "005930", "BUY", hour=11)]
    c = rd.count_trades(ts)
    assert len(c) == 1 and c[0].kind == "ROUNDTRIP"


def test_trades_need_three_sells():
    buys_only = [tr(i, i * 3, f"{i:06d}") for i in range(12)]
    it = rd.evaluate(NOW, buys_only, [], [], []).items[1]
    assert not it.done and it.parts == (("인정된 거래", 12, 10), ("그중 팔기", 0, 3))


# ── 3. 일지 ──────────────────────────────────────────────────
def test_journal_rules():
    js = [rd.Journal(T0, "급등해서"),                                      # 10자 미만
          rd.Journal(T0 + timedelta(1), "수출이 늘면 실적이 좋아질 것 같아요"),
          rd.Journal(T0 + timedelta(2), "수출이 늘면 실적이 좋아질 것 같아요!!"),   # 기호만 다름
          rd.Journal(T0 + timedelta(3), "수출이 늘면 실적이 좋아질 것 같아서요"),   # 거의 같음
          rd.Journal(T0 + timedelta(4), "한 종목에 너무 많아서 나눠 담으려고 팔아요")]
    assert rd.count_journals(js) == 2


# ── 4. 돌아보기 ──────────────────────────────────────────────
def test_reflection_needs_loss_when_loss_exists():
    n, ok = rd.count_reflections([refl("t5", "gain"), refl("t9", "regret", 26)], full_trades())
    assert n == 2 and not ok                       # 손실 거래가 있었는데 손실을 안 돌아봄


def test_reflection_regret_ok_when_no_loss():
    winners = [rd.Trade(t.id, t.at, t.code, t.side, 500 if t.side == "SELL" else None) for t in full_trades()]
    n, ok = rd.count_reflections([refl("t5", "gain"), refl("t9", "regret", 26)], winners)
    assert n == 2 and ok


def test_reflection_same_trade_once_and_short_answers_rejected():
    n, _ = rd.count_reflections([refl("t2", "loss"), refl("t2", "loss", 22), refl("t5", "gain", 23, ok=False)], full_trades())
    assert n == 1


# ── 5. 퀴즈 ──────────────────────────────────────────────────
def test_quiz_bank_and_grading():
    assert len(rd.QUESTIONS) == rd.QUIZ_TOTAL and len({q.id for q in rd.QUESTIONS}) == 10
    rnd = rd.quiz_round(1, user_seed=7)
    picks = [order.index(q.answer) for q, order in rnd]
    assert rd.grade(rnd, picks) == (10, [])
    picks[0] = (picks[0] + 1) % 4
    score, wrong = rd.grade(rnd, picks)
    assert score == 9 and wrong == [rnd[0][0].topic]


def test_retry_reshuffles():
    a = [q.id for q, _ in rd.quiz_round(1, 7)]
    b = [q.id for q, _ in rd.quiz_round(2, 7)]
    assert a != b and sorted(a) == sorted(b)


def test_quiz_pass_mark():
    assert not evaluate(quiz=[rd.QuizAttempt(NOW, 7)]).items[4].done
    assert evaluate(quiz=[rd.QuizAttempt(NOW, 7), rd.QuizAttempt(NOW, 8)]).items[4].done


# ── 6개월 재확인 ─────────────────────────────────────────────
def test_recheck_after_183_days():
    s = rd.ReadyState(qualified_at=T0, last_active_at=NOW)
    later = NOW + timedelta(days=184)
    s2 = rd.on_app_open(s, later)
    assert s2.recheck_since == later and s2.last_active_at == later
    r = rd.evaluate(later, full_trades(), journals(9), [refl("t2", "loss"), refl("t5", "gain", 25)], QUIZ_OK, s2)
    assert r.needs_recheck and not r.can_request_consent
    assert [i.done for i in r.items] == [True, True, True, True, False]    # 퀴즈만 다시
    assert rd.can_enter_real(s2, QUIZ_OK, "ACTIVE") == "RECHECK_QUIZ"
    q2 = QUIZ_OK + [rd.QuizAttempt(later + timedelta(minutes=5), 8)]
    assert rd.can_enter_real(s2, q2, "ACTIVE") is None
    assert rd.after_quiz(s2, q2).recheck_since is None


def test_no_recheck_within_183_days_or_if_never_qualified():
    s = rd.ReadyState(qualified_at=T0, last_active_at=NOW)
    assert rd.on_app_open(s, NOW + timedelta(days=183)).recheck_since is None
    never = rd.ReadyState(last_active_at=NOW)
    assert rd.on_app_open(never, NOW + timedelta(days=400)).recheck_since is None


def test_failed_recheck_keeps_lock():
    s = rd.ReadyState(qualified_at=T0, last_active_at=NOW, recheck_since=NOW)
    assert rd.can_enter_real(s, [rd.QuizAttempt(NOW + timedelta(1), 6)], "ACTIVE") == "RECHECK_QUIZ"


def test_enter_real_order_of_checks():
    assert rd.can_enter_real(rd.ReadyState(), QUIZ_OK, "ACTIVE") == "NOT_READY"
    q = rd.ReadyState(qualified_at=T0)
    assert rd.can_enter_real(q, QUIZ_OK, "PENDING") == "NO_CONSENT"
    assert rd.can_enter_real(q, QUIZ_OK, "ACTIVE") is None


def test_mark_qualified_once():
    s = rd.mark_qualified(rd.ReadyState(), evaluate(), NOW)
    assert s.qualified_at == NOW
    assert rd.mark_qualified(s, evaluate(), NOW + timedelta(1)).qualified_at == NOW


# ── 기준은 바꿀 수 없다 ──────────────────────────────────────
def test_no_override_parameters():
    import inspect
    params = set(inspect.signature(rd.evaluate).parameters)
    assert params == {"now", "trades", "journals", "refls", "quiz", "state"}


# ── 리포트 ───────────────────────────────────────────────────
def test_report_has_no_returns():
    r = evaluate()
    rep = rd.build_report(NOW, r, full_trades(), journals(9), [refl("t2", "loss"), refl("t5", "gain", 25)], QUIZ_OK, ["수수료·세금"])
    assert rep["trades"] == 12 and rep["sells"] == 4 and rep["quiz_best"] == 9 and rep["weeks"] >= 3
    flat = str(rep)
    assert "pnl" not in flat and "005930" not in flat and "%" not in flat
    with pytest.raises(ValueError):
        rd.build_report(NOW, evaluate(quiz=[]), full_trades(), [], [], [], [])


# ── 앱 기록 연결 (trades.csv · ready.json) ───────────────────
MARKET = "pages/1_가상_주식시장.py"
PARENT = "pages/13_보호자_투자_동의.py"
COLS = ["trade_id", "student_id", "date", "ticker", "side", "qty", "price", "journal"]
ANSWERS = ("많이 오르고 있어서 더 오를 줄 알았어요", "다음 날부터 내려서 손해를 보고 팔았어요", "이유부터 찾고 하루 기다렸다가 정할래요")


def test_practice_trades_pnl_order_and_journals():
    t = pd.DataFrame([("T1", "S01", "2026-10-01", "A", "BUY", 2, 100, "반도체 수요가 늘 것 같아서 샀어요"),
                      ("T2", "S01", "2026-10-02", "A", "BUY", 2, 200, ""),
                      ("T3", "S01", "2026-10-03", "A", "SELL", 1, 120, "비중을 줄이려고 팔았어요"),
                      ("T4", "S02", "2026-10-03", "A", "SELL", 1, 120, "다른 학생")], columns=COLS)
    trades, journals, info = rd.practice_trades([t], "S01")
    assert [x.id for x in trades] == ["T1", "T2", "T3"] and trades[0].at < trades[1].at
    assert trades[2].pnl == -30 and info["T3"]["pnl"] == -30          # 평균 단가 150에 120으로 1주
    assert len(journals) == 2 and journals[0].trade_id == "T1"


def test_grandfather_kind_and_stage():
    s = rd.grandfather(rd.ReadyState(), {"status": "ACTIVE", "decided_at": "2026-10-31T09:00:00"})
    assert s.qualified_at == datetime(2026, 10, 31, 9)                 # 기준이 생기기 전에 이미 동의받은 사람
    assert rd.grandfather(rd.ReadyState(), {"status": "PENDING"}).qualified_at is None
    assert rd.reflection_kind(-1, True) == "loss" and rd.reflection_kind(5, True, True) == "gain"
    assert rd.reflection_kind(5, False, True) == "regret" and rd.reflection_kind(5, False) == "gain"
    assert rd.stage_of(rd.evaluate(NOW, [], [], [], [])) == "early" and rd.stage_of(evaluate()) == "ready"


def test_add_reflection_rejects_short_and_repeat():
    doc = {}
    assert not rd.add_reflection(doc, NOW, "t1", "loss", ("짧아", "그냥", "다음엔"))
    assert rd.add_reflection(doc, NOW, "t1", "loss", ANSWERS)
    assert not rd.add_reflection(doc, NOW, "t1", "loss", ANSWERS)       # 같은 거래는 한 번만
    assert len(rd.reflections_from(doc)) == 1


def seed(tmp_path, monkeypatch, *, quiz=True, refl=True):
    """S01이 5가지를 다 채운 기록 (오늘 기준 5주 전부터, T0002는 손실 난 팔기). quiz/refl을 끄면 그 기준만 비운다."""
    from engine import updater
    now = updater.now_kst()
    start = now.date() - timedelta(days=35)
    plan = [(0, "BUY"), (2, "BUY"), (7, "SELL"), (9, "BUY"), (14, "BUY"), (16, "SELL"),
            (21, "BUY"), (23, "SELL"), (28, "BUY"), (30, "SELL"), (31, "BUY"), (33, "BUY")]
    topics = ["반도체", "금리", "환율", "배당", "분산", "ETF", "실적", "뉴스", "가격", "비중", "수출", "내수"]
    rows = []
    for i, (d, side) in enumerate(plan):
        price = 60000 if side == "BUY" else (50000 if i == 2 else 70000)
        rows.append((f"T{i:04d}", "S01", (start + timedelta(days=d)).isoformat(), "005930", side, 1, price,
                     f"{topics[i]} 때문에 {i}번째로 생각을 정리했어요"))
    path = tmp_path / "trades.csv"
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)
    monkeypatch.setattr(store, "TRADES_PATH", path)
    monkeypatch.setattr(store, "REAL_TRADES_PATH", tmp_path / "no_real_trades.csv")
    doc = {}
    if refl:
        rd.add_reflection(doc, now, "T0002", "loss", ANSWERS)
        rd.add_reflection(doc, now, "T0005", "gain", ANSWERS)
    if quiz:
        rd.add_quiz(doc, now, 9, ["수수료·세금"])
    store.save_ready("S01", doc)
    return now


def run(at):
    at = at.run()
    assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(m.value for m in at.markdown)


def press(at, label):
    next(b for b in at.button if b.label == label).click()
    return run(at)


def test_progress_locked_until_all_five(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch, quiz=False)
    at = open_app(MARKET)
    assert "실전 준비 4 / 5" in texts(at)
    at = press(at, "실전 준비 4 / 5 · 남은 것 보기")                 # 동의 요청 대신 진행 화면
    t = texts(at)
    assert "거의 다 왔어요! 1가지 남았어요" in t and "퀴즈 8점이 남았어요" in t and "4 / 5" in t
    locked = next(b for b in at.button if b.key == "rd-locked")
    assert locked.disabled and locked.label == "1가지를 더 채우면 열려요"
    assert not any(b.label == "부모님께 동의 요청하기" for b in at.button)
    assert "수익률·종목은 기준에 들어가지 않아요" in t


def test_consent_screen_shows_progress_until_ready(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch, refl=False)
    at = open_app(MARKET)
    at.session_state["inv-screen"] = {"screen": "consent", "symbol": None}  # 다른 길로 동의 요청 화면에 와도
    at = run(at)
    assert "4 / 5" in texts(at) and any(b.key == "rd-locked" for b in at.button)
    assert not any(b.label == "부모님께 요청 보내기" for b in at.button)


def test_quiz_round_saves_attempt_and_completes_item(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch, quiz=False)
    at = open_app(MARKET)
    at.session_state["inv-screen"] = {"screen": "ready_quiz", "symbol": None}
    at = run(at)
    rnd = rd.quiz_round(1, rd.user_seed("S01"))
    for n, (q, order) in enumerate(rnd):
        assert f"실전 준비 퀴즈 {n + 1}/10" in texts(at)
        pos = order.index(q.answer)
        next(b for b in at.button if b.key == f"rd-opt-1-{n}-{pos}").click()
        at = run(at)
        assert "정답이에요!" in texts(at)
        at = press(at, "결과 보기" if n == 9 else "다음 문제")
    assert "10문제 중 <b>10개</b> 정답" in texts(at)
    assert [q["score"] for q in store.load_ready("S01")["quiz"]] == [10]
    at = press(at, "실전 준비로 돌아가기")
    assert "실전 준비를 모두 마쳤어요" in texts(at) and any(b.label == "부모님께 동의 요청하기" for b in at.button)
    assert store.load_ready("S01")["state"]["qualified_at"]          # 처음 다 채운 시각


def test_quiz_wrong_answer_shows_explain_and_retry_reshuffles(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch, quiz=False)
    at = open_app(MARKET)
    at.session_state["inv-screen"] = {"screen": "ready_quiz", "symbol": None}
    at = run(at)
    rnd = rd.quiz_round(1, rd.user_seed("S01"))
    for n, (q, order) in enumerate(rnd):
        pos = (order.index(q.answer) + 1) % 4                        # 일부러 모두 틀린다
        next(b for b in at.button if b.key == f"rd-opt-1-{n}-{pos}").click()
        at = run(at)
        assert "이번엔 아쉬워요" in texts(at) and q.explain in texts(at)
        at = press(at, "결과 보기" if n == 9 else "다음 문제")
    assert "틀린 문제 해설" in texts(at)
    saved = store.load_ready("S01")["quiz"]
    assert saved[0]["score"] == 0 and len(saved[0]["wrong"]) == 10
    at = press(at, "다시 풀기 (순서가 바뀌어요)")
    first2 = rd.quiz_round(2, rd.user_seed("S01"))[0][0]
    assert escape(first2.text) in texts(at)                                   # 2회차 순서


def test_reflection_write_screen(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch, refl=False)
    at = open_app(MARKET)
    at.session_state["inv-screen"] = {"screen": "reflect", "symbol": None}
    at = run(at)
    t = texts(at)
    assert "1. 돌아볼 거래 고르기" in t and "잃은 돈보다 배운 걸 적는 게 중요해요" in t
    radio = at.radio(key="rd-pick-w")
    assert radio.value == "T0009" and len(radio.options) == 4 and "−10,000원 (−16.7%)" in radio.options[-1]  # 최근 팔기부터
    radio.set_value("T0002")
    at.text_area(key="rd-a2").input("짧아")
    at = press(at, "저장하기 · 돌아보기 1/2")
    assert any("10자 이상" in e.value for e in at.error) and "reflections" not in store.load_ready("S01")
    for key, text in zip(("rd-a2", "rd-a3", "rd-a4"), ANSWERS):
        at.text_area(key=key).input(text)
    at = press(at, "저장하기 · 돌아보기 1/2")
    saved = store.load_ready("S01")["reflections"]
    assert [(r["trade_id"], r["kind"]) for r in saved] == [("T0002", "loss")]   # 손실 난 거래
    assert "1 / 2회" in texts(at)                                      # 진행 화면으로 돌아왔다


def test_ready_request_parent_report_and_decline_with_note(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch)
    at = open_app(MARKET)
    at = press(at, "부모님께 동의 요청하기")
    t = texts(at)
    assert "의 실전 준비 리포트" in t and "인정된 거래 12회 · 그중 팔기 4회" in t and "이 리포트에 없는 것" in t
    at = press(at, "부모님께 요청 보내기")
    snap = store.load_invest("S01")["consent"]["report_snapshot"]
    assert snap["kind"] == "ready" and "pnl" not in str(snap) and "005930" not in str(snap)
    at.switch_page(PARENT)
    at = run(at)
    t = texts(at)
    assert "5가지 기준을 모두 채웠어요" in t and "10문제 중 9개 정답" in t and "수수료·세금" in t
    at.text_input(key="pg-reject-note").input("다음 달에 같이 이야기해 보자")
    at = press(at, "지금은 동의하지 않기 (한마디 남기기)")
    saved = store.load_invest("S01")
    assert saved["consent"]["status"] == "REJECTED" and saved["consent"]["parent_note"] == "다음 달에 같이 이야기해 보자"
    at.switch_page(MARKET)
    at = run(at)
    assert "부모님 한마디: “다음 달에 같이 이야기해 보자”" in texts(at)
    assert store.load_ready("S01")["state"]["qualified_at"]          # 동의하지 않아도 자격은 그대로


def test_ready_then_parent_approves_and_real_entry_reaches_switch_sheet(tmp_path, monkeypatch):
    from conftest import open_app
    seed(tmp_path, monkeypatch)
    at = open_app(MARKET)
    at = press(at, "부모님께 동의 요청하기")
    at = press(at, "부모님께 요청 보내기")
    at.switch_page(PARENT)
    at = run(at)
    at = press(at, "동의하고 계좌 개설로 이동")
    at.switch_page(MARKET)
    at = run(at)
    at.segmented_control(key="inv-mode-widget").set_value("실전 계좌")
    at = run(at)
    assert "실전으로 바꿀까요?" in texts(at)                            # 준비 기준 → 동의 → 전환 확인 시트


def test_six_month_recheck_locks_real_until_quiz(tmp_path, monkeypatch):
    """자격을 얻고 동의도 받은 사람이 184일 쉬고 오면: 실전 입구 → 진행 화면(퀴즈만 다시)."""
    from conftest import open_app
    from engine import broker, invest_track as it
    now = seed(tmp_path, monkeypatch)
    doc = store.load_ready("S01")
    rd.state_to(doc, rd.ReadyState(qualified_at=now - timedelta(days=220), last_active_at=now - timedelta(days=184)))
    doc["quiz"][0]["at"] = (now - timedelta(days=220)).isoformat(timespec="seconds")  # 예전에 통과한 퀴즈
    store.save_ready("S01", doc)
    state = it.new_state("S01")
    it.transition(state, "REQUEST", message="", report={})
    state["guardrails"] = it.make_guardrails()
    broker.open_real_account(state, broker.MockBrokerAdapter())
    store.save_invest("S01", state)
    at = open_app(MARKET)
    assert store.load_ready("S01")["state"]["recheck_since"]           # 앱을 열 때 걸렸다
    assert "연습 모드 · 가상 머니" in texts(at)                         # 연습은 바로
    at.segmented_control(key="inv-mode-widget").set_value("실전 계좌")
    at = run(at)
    t = texts(at)
    assert "오랜만이에요! 퀴즈만 다시 확인해요" in t and "다시 확인" in t
    assert next(b for b in at.button if b.key == "rd-locked").label == "퀴즈를 통과하면 실전이 다시 열려요"


def test_ready_touch_throttles_writes():
    import ui_common as ui
    t0 = datetime(2026, 11, 17, 9, 0)
    ui.ready_touch("S01", t0)
    assert store.load_ready("S01")["state"]["last_active_at"] == "2026-11-17T09:00:00"
    ui.ready_touch("S01", t0 + timedelta(minutes=5))
    assert store.load_ready("S01")["state"]["last_active_at"] == "2026-11-17T09:00:00"
    ui.ready_touch("S01", t0 + timedelta(minutes=11))
    assert store.load_ready("S01")["state"]["last_active_at"] == "2026-11-17T09:11:00"


def test_flag_off_keeps_old_consent_request(monkeypatch):
    import config
    from conftest import open_app
    monkeypatch.setattr(config, "READY_CRITERIA", False)
    at = open_app(MARKET)
    assert not any(b.key == "inv-ready-go" for b in at.button)
    at = press(at, "부모님께 동의 요청하기")
    assert "부모님께 보낼 연습 리포트" in texts(at)


def test_mock_mode_is_not_gated():
    from conftest import open_app
    at = open_app(MARKET, query={"mock": "1"})
    assert not at.exception and not any(b.key == "inv-ready-go" for b in at.button)


def test_no_criteria_settings_on_parent_page():
    src = (Path(__file__).resolve().parent.parent / "pages" / "13_보호자_투자_동의.py").read_text(encoding="utf-8")
    for name in ("PRACTICE_MIN_DAYS", "TRADES_MIN", "JOURNALS_MIN", "QUIZ_PASS", "RECHECK_AFTER_DAYS"):
        assert name not in src
