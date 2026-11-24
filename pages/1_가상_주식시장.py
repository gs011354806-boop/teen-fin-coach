"""투자 탭: 동의 기반 2트랙 (2026-11-13, 시뮬레이션 · invest/tintin_invest_handoff/INVEST_TAB_SPEC.md).

- 연습 모드(누구나): 기존 가상 주식시장 그대로 (가상 머니 · 시나리오/실제 종가 · 주문 전 1분 점검 · 투자 일지).
  홈 ① → 종목 상세 · 연습 주문 ② (사기 전 체크리스트 3개) → 부모님께 동의 요청 ③.
- 실전 모드(부모 동의 ACTIVE + 계좌 연결): 실전 홈 ⑤ → 실전 주문 ⑥ (급등주 확인 → 근거 → validate_order → Mock 체결).
  부모 화면 ④는 pages/13_보호자_투자_동의.py (앱 안 보호자 모드).
- 레벨(실전 준비 단계)은 투자 진입·한도·범위와 연결하지 않는다. 실제 증권사 주문은 연결하지 않는다 (MockBrokerAdapter).
- ?mock=1 → 명세 7장 연습 시안, ?mock=real → 실전 시안. 둘 다 저장하지 않는다.
- 2026-11-16 NEWS_MARKET_SPEC.md: 종목 상세에 [연습 · 가상 머니 | 실전 · 부모님 동의] 전환, 전날 종가 기준일 문구,
  20일 차트, 이 종목이 나온 뉴스, 뉴스 근거 칩. 실전 시세도 지금은 공공데이터 전날 종가 (config.REAL_QUOTE_SOURCE="eod"):
  종목 상세(09) → 주문 확인(10a, '실제 돈이 나가요' 체크) → validate_order → Mock 체결 → 완료(10b), 막히면 차단 안내(11).
- 2026-11-16 REAL_SAFETY_SPEC.md: 실전으로 들어가는 입구(투자 홈 '실전 계좌', 종목 상세 '실전')는 모두 tap_real() 하나를 거친다.
  전환 확인 시트 → (오늘 처음 · 설정/동의가 바뀐 뒤면) 안전 체크리스트 6개 → 실전. 실전 → 연습은 바로.
  실전 화면은 맨 위 남색 띠 + 노란 '실전' 배지, 10분 동안 조작이 없으면 연습으로 돌아간다 (engine/real_safety.py).
  ?mock=safety → 동의는 됐지만 오늘 안전 체크 전인 시안.
- 2026-11-17 READY_SPEC.md (criteria/teengrow_ready): 수익률이 아니라 과정 5가지(연습 기간 · 연습 거래 · 근거 쓴 일지 ·
  돌아보기 · 준비 퀴즈)를 채워야 부모님께 동의를 요청할 수 있다. 실전 입구 순서: 준비 기준 → 6개월 재확인 → 부모 동의 →
  전환 확인 시트 → 안전 체크리스트. 판단은 engine/ready.py, 화면 조각은 ready_view.py. 시안(?mock)에는 걸지 않는다.
config.INVEST_CONSENT_TRACK = False → 예전 화면 (legacy/market_v1_page.py, 레벨 기반).
"""

import runpy
from pathlib import Path

import streamlit as st

import config

if not config.INVEST_CONSENT_TRACK:
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "legacy" / "market_v1_page.py"))
    st.stop()

import copy  # noqa: E402
from datetime import date  # noqa: E402
from html import escape  # noqa: E402

import pandas as pd  # noqa: E402

import growby  # noqa: E402
import ready_view as rv  # noqa: E402
import ui_common as ui  # noqa: E402
from engine import (broker, detect, envelope, invest_track as it, invest_view as iv, news_daily as nd,  # noqa: E402
                    portfolio, price_history, quotes, real_safety as rs, store, updater)
from datetime import datetime  # noqa: E402
from ui_common import won  # noqa: E402

SIDE_LABELS = {"BUY": "매수", "SELL": "매도"}
MOCK_KEY = "invest-mock-state"
CHECK_ITEMS = [("news", "오늘 공시·뉴스를 읽었어요"), ("chart", "최근 한 달 가격 흐름을 봤어요"),
               ("journal", "사는 이유를 투자일지에 한 줄 썼어요")]

market = ui.market_context(ui.setup("투자", "📈", active="market"))
student = market["student"]  # 실제 시세 모드면 가상 투자금이 REAL_VIRTUAL_CASH
student_id = student["student_id"]
mock = st.query_params.get("mock")
st.session_state["invest-mock"] = mock  # 보호자 화면이 같은 시안 상태를 보게


# ---------- 상태 ----------

def mock_state(kind):
    demo = broker.load_demo()
    state = it.new_state(demo["student"]["id"])
    state["watch"] = copy.deepcopy([w for w in demo["watch"] if kind == "real" or w["account"] == "PRACTICE"])
    if kind == "real":
        g = demo["guardrails"]
        state["consent"].update(status=it.ACTIVE, requested_at="2026-10-30T19:00:00",
                                decided_at="2026-10-31T09:00:00", broker_account_id=demo["real"]["account_id"])
        state["guardrails"] = it.make_guardrails(g["monthlyLimit"], g["scope"], g["notifyParentOnTrade"],
                                                 g["fomoCheck"], "2026-10-31T09:00:00")
        state["real"] = copy.deepcopy(demo["real"])
    return state


if mock:
    demo = broker.load_demo()
    kind = "real" if mock in ("real", "safety") else "practice"
    if st.session_state.get(MOCK_KEY, {}).get("kind") != mock:
        st.session_state[MOCK_KEY] = {"kind": mock, "state": mock_state(kind)}
        st.session_state.pop("inv-stage-owner", None)  # 시안이 바뀌면 실전 진입 단계도 새로
    state = st.session_state[MOCK_KEY]["state"]
    today = demo["today"]
    clock = datetime.fromisoformat(demo["now"])  # 시안 시각 고정 (전날 종가 기준일 판단)
    practice_provider = real_provider = broker.MockMarketDataProvider(demo)
    invest_envelope = demo["investEnvelope"]
else:
    demo = None
    state = it.migrate(store.load_invest(student_id) or it.new_state(student_id), student_id)
    today = date.today().isoformat()
    clock = updater.now_kst()
    practice_provider = real_provider = broker.PriceTableProvider(market["names"], market["prices"], market["mode"])
    invest_envelope = envelope.balances(store.load_allowance(), student_id)["INVEST"]


def save():
    if not mock:  # 시안 상태는 저장하지 않는다
        store.save_invest(student_id, state)


track = it.resolve_invest_track(config.INVEST_CONSENT_TRACK, state["consent"], it.account_linked(state))
status = state["consent"]["status"]
real_open = it.can_view_real(state)  # 실전 계좌를 볼 수 있음 (ACTIVE, 또는 철회됐어도 계좌가 있으면)
REAL_UI = config.NEWS_MARKET_FLAGS["realTrading"]
if not mock and REAL_UI and real_open:
    # 실전 시세 = 공공데이터 전날 종가 (영업일 13:30 자동 업데이트). 설정 하나로 증권사 실시간으로 바꾼다 (8-5)
    quotes.load_quotes()
    real_provider = broker.get_quote_provider(broker.EodQuoteProvider(quotes.latest_rows(), quotes.load_watchlist()))


# ---------- 실전 준비 기준 (READY_SPEC.md) ----------
READY = config.READY_CRITERIA and not mock
ready_ctx = rv.load(student_id, state["consent"], rv.practice_tables(), updater.now_kst()) if READY else None
can_request = (not READY) or ready_ctx["r"].can_request_consent


def ticker_names():
    names = dict(store.load_ticker_names())
    names.update(market["names"])
    names.update(quotes.load_watchlist())
    return names


# ---------- 화면 이동 ----------

def go(screen, symbol=None):
    st.session_state["inv-screen"] = {"screen": screen, "symbol": symbol}


def toast(text):
    st.session_state["inv-toast"] = text


# ---------- 실전 진입 안전장치 (REAL_SAFETY_SPEC.md) ----------
SAFETY = config.REAL_SAFETY and REAL_UI
REAL_SCREENS = ("order", "change", "confirm", "done")
CHECK_KEYS = [f"safe-chk-{i}" for i in range(rs.ITEM_COUNT)]
safety_now = updater.now_kst()
owner = f"{student_id}:{mock or ''}"
if st.session_state.get("inv-stage-owner") != owner:  # 학생이나 시안이 바뀌면 연습에서 다시 시작
    st.session_state["inv-stage-owner"] = owner
    st.session_state["inv-stage"] = "practice"
    st.session_state["inv-safety"] = {}
    st.session_state.pop("inv-mode", None)
    if mock == "real":  # 실전 시안: 오늘 안전 체크를 마치고 실전 화면에 있는 상태
        rs.to_saved(state, rs.record_check(rs.SafetyState(), safety_now))
        st.session_state["inv-stage"] = "real"
        st.session_state["inv-safety"] = {"in_real_mode": True, "last_real_activity_at": safety_now}
        st.session_state["inv-mode"] = "REAL"
stage = st.session_state.get("inv-stage", "practice")


def safety_state():
    return rs.from_saved(state, st.session_state.setdefault("inv-safety", {}))


def keep_safety(sst, persist=False):
    st.session_state["inv-safety"] = {"in_real_mode": sst.in_real_mode,
                                      "last_real_activity_at": sst.last_real_activity_at}
    if persist:
        rs.to_saved(state, sst)
        save()


def reset_checks():
    for k in CHECK_KEYS:
        st.session_state.pop(k, None)


def tap_real(target_screen="home", symbol=None):
    """실전으로 들어가는 모든 입구가 부르는 하나 (투자 홈 '실전 계좌', 종목 상세 '실전')."""
    if READY:  # 준비 기준 → 6개월 재확인을 먼저 (READY_SPEC 4장). 동의가 멈춘 뒤 가진 종목 보기·팔기는 막지 않는다
        code = rv.gate(ready_ctx, status)
        if code in ("NOT_READY", "RECHECK_QUIZ") and not (status == it.REVOKED and real_open):
            go("ready")
            return
    if not SAFETY:  # 안전장치를 끄면 예전처럼 바로
        if real_open:
            st.session_state["inv-mode"] = "REAL"
            go(target_screen, symbol)
        else:
            st.session_state["inv-block"] = {"code": "NO_CONSENT", "symbol": symbol}
            go("blocked", symbol)
        return
    route = rs.entry_route(status, safety_state(), safety_now, rs.settings_changed_at(state),
                           rs.consent_activated_at(state))
    if route[0] == rs.LOCKED or not real_open:
        st.session_state["inv-block"] = {"code": "NO_CONSENT", "symbol": symbol}
        go("blocked", symbol)
        return
    st.session_state["inv-route"] = route
    st.session_state["inv-real-target"] = (target_screen, symbol)
    reset_checks()
    st.session_state["inv-stage"] = "switch"


def next_stage(current):
    route = st.session_state.get("inv-route", [])
    return route[route.index(current) + 1] if current in route and route.index(current) + 1 < len(route) else rs.REAL


def open_real(stage_name):
    """시트·체크리스트를 지나 실전 화면으로."""
    st.session_state["inv-stage"] = "real_view_sell" if stage_name == rs.REAL_VIEW_SELL else "real"
    st.session_state["inv-mode"] = "REAL"
    target, symbol = st.session_state.pop("inv-real-target", ("home", None))
    go(target, symbol)


def back_to_practice(message=None, symbol=None):
    """실전 → 연습: 확인 없이 바로. 오늘 체크 기록은 남긴다. 체크 중이던 것은 지운다."""
    if SAFETY:
        keep_safety(rs.exit_to_practice(safety_state()))
        st.session_state["inv-stage"] = "practice"
        reset_checks()
    st.session_state["inv-mode"] = "PRACTICE"
    if message:
        st.session_state["inv-toast"] = message
    if symbol and symbol in practice_provider.names():
        go("stock", symbol)
    else:
        go("home")


screen = st.session_state.get("inv-screen", {"screen": "home", "symbol": None})
if SAFETY:
    in_real = stage in ("real", "real_view_sell") and real_open
    if in_real and rs.should_auto_exit(safety_state(), safety_now):  # 10분 무조작 → 연습으로
        back_to_practice(f"{config.REAL_SAFETY_IDLE_MIN}분 동안 쉬어서 연습으로 돌아왔어요")
        stage, in_real = "practice", False
        screen = st.session_state["inv-screen"]
    elif in_real:
        keep_safety(rs.touch(safety_state(), safety_now))  # 실전 화면에서 무언가 할 때마다 마지막 조작 시각
    if not in_real and screen["screen"] in REAL_SCREENS:  # 다른 길로 실전 화면이 바로 열리지 않게
        screen = {"screen": "home", "symbol": None}
    mode = "REAL" if in_real else "PRACTICE"
else:
    if screen["screen"] in REAL_SCREENS and not real_open:
        screen = {"screen": "home", "symbol": None}
    mode = st.session_state.get("inv-mode", "REAL" if real_open else "PRACTICE")
    if not real_open:
        mode = "PRACTICE"
if "inv-toast" in st.session_state:
    st.toast(st.session_state.pop("inv-toast"))


def back_home():
    go("home")


# ---------- ① 연습 모드 홈 ----------

def mode_switch():
    """실전 계좌 | 연습 모드 (실전 계좌가 있을 때만)."""
    if not real_open:
        return
    labels = {"REAL": "실전 계좌", "PRACTICE": "연습 모드"}

    def changed():
        picked = {v: k for k, v in labels.items()}.get(st.session_state.get("inv-mode-widget"))
        st.session_state.pop("inv-mode-widget", None)
        if picked == "REAL" and mode != "REAL":
            tap_real("home")
        elif picked == "PRACTICE" and mode != "PRACTICE":
            back_to_practice()

    with st.container(key="inv-mode"):
        st.segmented_control("계좌 고르기", list(labels.values()), default=labels[mode], key="inv-mode-widget",
                             on_change=changed, label_visibility="collapsed")


def practice_banner():
    if mock:
        ui.navy_card("실제 시장으로 연습해요", "시세 · 뉴스 · 공시는 <b class='hl'>진짜</b>, 돈만 가상이에요",
                     "실제 상장 종목 시세 연동 (15분 지연) · 수수료와 세금도 실제처럼 계산 (시안)")
    elif market["mode"] == "real":
        ui.navy_card("실제 시장으로 연습해요", "시세는 <b class='hl'>진짜</b>, 돈만 가상이에요",
                     f"실제 상장 종목 종가 (하루 늦게 갱신) · 출처: {quotes.SOURCE} · "
                     "종목별 공시·뉴스는 아직 연결 전이에요")
    else:
        ui.navy_card("잠시 연습용 시세로 보여 줘요", "실제 시세를 불러오지 못해 <b class='hl'>연습용</b> 시세를 보여 줘요",
                     "시세 연결이 돌아오면 다시 실제 종목의 종가로 연습해요. 돈은 언제나 가상이에요")


def consent_card():
    """실전 유도 카드: 동의 상태(NONE / PENDING / REJECTED / REVOKED)에 따라 문구와 버튼이 바뀐다."""
    if status == it.ACTIVE:
        return
    with ui.card("inv-consent"):
        if status == it.NONE:
            st.markdown("**실전 투자를 해보고 싶다면?**")
            if READY:
                ui.muted("수익률이 아니라 연습 과정 5가지를 채우면 부모님께 동의를 요청할 수 있어요. "
                         "그동안 연습 모드는 계속 쓸 수 있어요.")
                label = "부모님께 동의 요청하기" if can_request else f"실전 준비 {ready_ctx['r'].done_count} / 5 · 남은 것 보기"
                st.button(label, key="inv-ask", width="stretch", on_click=go, args=("consent" if can_request else "ready",))
            else:
                ui.muted("부모님 동의를 받으면 레벨 조건 없이 바로 실제 주식을 소액으로 살 수 있어요. "
                         "동의 전에도 연습 모드는 계속 쓸 수 있어요.")
                st.button("부모님께 동의 요청하기", key="inv-ask", width="stretch", on_click=go, args=("consent",))
        elif status == it.PENDING:
            st.markdown("**부모님 확인을 기다리고 있어요**")
            ui.muted("부모님이 연습 리포트를 보고 안전장치를 정하면 실전 계좌가 열려요. 그동안 연습 모드는 그대로 쓸 수 있어요.")
            st.button("다시 알림 보내기", key="inv-remind", width="stretch", on_click=remind)
            st.page_link(ui.PARENT_INVEST, label="보호자 화면 열기 (시연용)", icon=":material/family_restroom:")
        else:
            left = it.cooldown_left(state["consent"], today)
            if status == it.REJECTED:
                st.markdown("**부모님이 이번에는 동의하지 않았어요**")
                if state["consent"].get("parent_note"):
                    st.markdown(f"부모님 한마디: “{escape(state['consent']['parent_note'])}”")
                ui.muted("연습 모드에서 계속 기록을 쌓고, 부모님과 이야기한 뒤 다시 요청할 수 있어요."
                         + (" 실전 준비 기준은 그대로 채운 상태예요." if READY and can_request else ""))
            else:
                st.markdown("**부모님이 실전 모드를 멈췄어요**")
                ui.muted("새로 사기는 막혀 있고, 가진 종목 보기와 팔기는 실전 계좌에서 할 수 있어요.")
            st.button("다시 요청하기" if not left else f"{left}일 뒤에 다시 요청할 수 있어요", key="inv-reask",
                      width="stretch", disabled=bool(left), on_click=go, args=("consent" if can_request else "ready",))


def ready_row():
    """투자 탭의 '실전 준비' 메뉴: 채운 기준 n / 5 (수익률·종목은 기준이 아니다)."""
    r = ready_ctx["r"]
    with ui.card("inv-ready"):
        st.markdown(f"**실전 준비 {r.done_count} / 5**" + (" · 다시 확인" if r.needs_recheck else ""))
        ui.muted("연습 기간 · 연습 거래 · 근거 쓴 일지 · 돌아보기 · 준비 퀴즈를 채우면 실전 동의를 요청할 수 있어요.")
        st.button("실전 준비 보기", key="inv-ready-go", width="stretch", on_click=go, args=("ready",))


def ready_action(kind):
    if kind == "practice":
        go("home")
    elif kind == "reflect":
        go("reflect")
    else:
        st.session_state.pop(rv.QKEY, None)
        go("ready_quiz")


def ready_screen():
    ui.app_bar("실전 준비", on_back=back_home, pill=ui.mode_pill("PRACTICE"))
    rv.progress_view(ready_ctx, status, ready_action, lambda: go("consent"), lambda: go("ready_report"))


def reflect_screen():
    ui.app_bar("돌아보기 리포트", on_back=lambda: go("ready"))
    rv.reflect_view(ready_ctx, ticker_names(), lambda text: (toast(text), go("ready")))


def ready_quiz_screen():
    ui.app_bar("실전 준비 퀴즈", on_back=lambda: go("ready"))
    rv.quiz_view(ready_ctx, lambda: go("ready"))


def ready_report_screen():
    ui.app_bar("부모님께 갈 리포트", on_back=lambda: go("ready"))
    ui.muted("부모님 화면에 이렇게 보여요. 수익률과 종목은 들어가지 않아요.")
    st.markdown(rv.report_html(rv.make_report(ready_ctx), student["name"]), unsafe_allow_html=True)
    st.markdown(rv.plan_html(it.make_guardrails()), unsafe_allow_html=True)
    st.markdown(rv.not_in_report_html(), unsafe_allow_html=True)
    st.button("부모님께 동의 요청하기", type="primary", width="stretch", key="rd-report-request", on_click=go,
              args=("consent",))


def remind():
    if any(n["to"] == "PARENT" and n["at"][:10] == today and "다시" in n["text"] for n in state["notifications"]):
        toast("오늘은 이미 알림을 다시 보냈어요. 내일 다시 보낼 수 있어요.")
        return
    it.notify(state, "PARENT", "아이가 실전 투자 동의 요청을 다시 알렸어요.")
    save()
    toast("부모님께 다시 알림을 보냈어요.")


def practice_home():
    ui.app_bar("투자", pill=ui.mode_pill("PRACTICE"))
    mode_switch()
    practice_banner()
    if not mock:
        quote = market["quote"]
        if quote and quote["message"]:
            st.warning(quote["message"])
        if market["mode"] == "real":
            state_word = "장중" if quote["market_open"] else "장 마감"
            ui.muted(f"{practice_provider.as_of} 종가 기준 (마지막 가격) · 지금은 {state_word} · 시세 확인 "
                     f"{quote['fetched_at'].strftime('%m/%d %H:%M')} · 하루 늦게 갱신돼요. 거래는 가상 투자금으로만 해요.")
        view = iv.practice_home(student, market, practice_provider, state)
    else:
        view = iv.practice_home_mock(demo, state)
    top = view["maxWeight"]
    with ui.card("inv-account"):
        st.markdown(ui.account_html(
            "가상 계좌 평가금액", f"시작 {view['start']:,}원", view["value"], view["returnPct"], bar=view["segments"],
            foot=(f"투자 {view['investPct']}% · 현금 {100 - view['investPct']}%",
                  f"최대 비중 {top[0]}% ({top[1]})" if top else "아직 가진 종목이 없어요")), unsafe_allow_html=True)
    with ui.card("inv-list"):
        if not view["rows"]:
            ui.muted("아직 가진 종목이나 관심 종목이 없어요. 아래에서 종목을 골라 보세요.")
        for row in view["rows"]:
            if ui.stock_row(row, f"p-{row['symbol']}", action="보기" if row["kind"] == "watch" else None):
                go("stock", row["symbol"])
                st.rerun()
    with ui.card("inv-pick"):
        names = view["names"]
        ticker = st.selectbox("다른 종목 보기", list(names), format_func=lambda t: f"{names[t]} ({t})")
        st.button("이 종목 보기", key="inv-pick-go", width="stretch", on_click=go, args=("stock", ticker))
    if READY:
        ready_row()
    consent_card()
    if not mock:
        journal_table()


def journal_table():
    ui.section("내 거래와 일지")
    trades, names = market["trades"], market["names"]
    with ui.card("journal"):
        mine = trades[trades["student_id"] == student_id].iloc[::-1]
        if len(mine):
            st.dataframe(pd.DataFrame({
                "날짜": [d[5:] for d in mine["date"]],
                "종목": [names[t] for t in mine["ticker"]],
                "구분": mine["side"].map(SIDE_LABELS),
                "수량": [f"{q}주" for q in mine["qty"]],
                "일지": [j if j else "(안 적음)" for j in mine["journal"]],
            }), hide_index=True, width="stretch")
        else:
            st.info("아직 거래가 없어요.")
    with ui.card("lesson-link"):
        ui.service_row(ui.LESSON, "🔍", "실수에서 배우기", "AI 코치와 그때의 판단 돌아보기", key="lesson")


# ---------- ② 종목 상세 · 연습 주문 ----------

def checklist(symbol):
    with ui.card("inv-check"):
        marks = {k: st.session_state.get(f"chk-{symbol}-{k}", False) for k, _ in CHECK_ITEMS}
        st.markdown(f"<div class='chk-head'><span>사기 전 체크리스트</span><span>{sum(marks.values())}/3</span></div>",
                    unsafe_allow_html=True)
        for k, label in CHECK_ITEMS:
            st.checkbox(label, key=f"chk-{symbol}-{k}")
    return {k: st.session_state.get(f"chk-{symbol}-{k}", False) for k, _ in CHECK_ITEMS}


def record_checklist(symbol, marks, surge, trade_id, side="BUY"):
    state["checklists"].append({"date": today, "symbol": symbol, "side": side, "trade_id": trade_id,
                                "surge": surge, **marks})


def stock_mode_switch(symbol, current):
    """종목 상세 맨 위 [연습 · 가상 머니 | 실전 · 부모님 동의]. 동의 전에 실전을 누르면 동의 요청 안내(NO_CONSENT)."""
    if not REAL_UI:
        return
    labels = {"PRACTICE": "● 연습 · 가상 머니", "REAL": "● 실전 · 부모님 동의"}

    def changed():
        picked = {v: k for k, v in labels.items()}.get(st.session_state.get(f"stock-mode-{symbol}"))
        if picked == "REAL" and current != "REAL":
            tap_real("order", symbol)
        elif picked == "PRACTICE" and current != "PRACTICE":
            back_to_practice(symbol=symbol)
        st.session_state.pop(f"stock-mode-{symbol}", None)

    with st.container(key="stock-mode"):
        st.segmented_control("모드", list(labels.values()), default=labels[current], key=f"stock-mode-{symbol}",
                             on_change=changed, label_visibility="collapsed")


def price_block(provider, symbol, quote, real=False):
    """가격 · ▲ 전날보다 · 기준일 문구 · 20일 차트 · 시가/고가/저가/거래량 (있으면)."""
    surge = quote["changePct"] >= detect.SURGE_PCT
    head = ui.change_arrow_html(quote["changePct"], quote.get("change"))
    tag = "<span class='acc-tag'>전날 종가</span>" if real else ""
    caption = quote["label"]
    chart = ui.spark_svg(provider.history(symbol, 20), surge)
    ohlv = ""
    if all(k in quote for k in ("open", "high", "low")):
        vol = quote.get("volume")
        ohlv = (f"<div class='ohlv'><span>시가</span><b>{quote['open']:,}원</b><span>고가</span><b>{quote['high']:,}원</b>"
                f"<span>저가</span><b>{quote['low']:,}원</b><span>거래량</span>"
                f"<b>{'-' if vol is None else f'{vol:,}주'}</b></div>")
    note = ("<div class='muted'>실전도 지금은 연습과 같은 전날 종가로 사고팔아요. 실시간 시세는 나중에 증권사와 연결하면 바뀌어요.</div>"
            if real else "")
    if config.CHART_V2:  # 새 차트가 그래프·시고저·거래량을 함께 보여 준다 (CHART_SPEC 2장)
        chart, ohlv = "", ""
    st.markdown(f"<div class='price'><div class='price-row'><span class='price-value'>{quote['price']:,}원</span>{tag}</div>"
                f"<div>{head} <span class='muted'>전날보다</span></div><div class='eodcap'>🕐 {caption}</div>"
                f"{note}{chart}{ohlv}</div>", unsafe_allow_html=True)
    if config.CHART_V2:
        stock_chart(provider, symbol, quote, real)


def stock_chart(provider, symbol, quote, real):
    """종목 차트 (연습·실전이 같은 함수). 데이터: 시안 → 가상 3년 / 실제 종목 → 저장한 3년 일봉(없으면 받는 중) /
    연습용 가상 시세 → 종가만 (선 그래프)."""
    end = date.fromisoformat(quote["basDt"][:10]) if quote.get("basDt") else date.fromisoformat(quote["asOf"][:10])
    avg, qty_text, note = None, None, None
    if mock:
        daily, events = price_history.demo_bars(symbol, quote["price"], end), []
        note = "그래프 값은 시안용 예시예요"
        pct, close_only = 1.0, False
    elif symbol in quotes.load_watchlist() and (real or market["mode"] == "real"):
        watch = quotes.load_watchlist()
        price_history.start_backfill(list(watch), watch, end)  # 3년치가 없으면 뒤에서 받는다 (화면은 기다리지 않음)
        daily, events = price_history.chart_bars(symbol, end)
        if not daily:  # 아직 저장 전이면 최근 시세(자동 업데이트 저장값)로
            rows = quotes.latest_rows().get(symbol, [])
            daily = price_history.to_bars([{"d": r["date"], "o": r.get("open") or r["close"], "h": r.get("high") or r["close"],
                                            "l": r.get("low") or r["close"], "c": r["close"], "v": r.get("volume", 0)}
                                           for r in rows])
        pct, _ = price_history.state(symbol, end)
        close_only = bool(daily) and all(b.v == 0 and b.o == b.c == b.h for b in daily[-5:])
    else:
        daily, events = price_history.close_only_bars(provider.history(symbol, 400)), []
        pct, close_only = 1.0, True
    if real:
        h = state["real"]["holdings"].get(symbol)
        if h and h.get("qty"):
            avg, qty_text = round(h["avgPrice"]), it.qty_label(h["qty"])
    elif not mock:
        a, q = iv.avg_cost(market["trades"], student_id, symbol)
        if a:
            avg, qty_text = a, f"{q}주"
    ui.render_stock_chart(symbol, daily, end, events, avg, pct, "real" if real else "practice",
                          close_only=close_only, note=note, avg_qty=qty_text)


def stock_news_card(symbol):
    """이 종목이 나온 뉴스 (최근 7일, 오늘의 뉴스에서 기사에 이름이 나온 경우만)."""
    if not config.NEWS_MARKET_FLAGS["newsStockLink"]:
        return []
    rows = nd.stock_news(symbol, today)
    with ui.card("stock-news"):
        st.markdown(f"**이 종목이 나온 뉴스** <span class='muted'>최근 7일 · {len(rows)}개</span>", unsafe_allow_html=True)
        if not rows:
            ui.muted("최근 7일 오늘의 뉴스에는 이 종목이 나오지 않았어요.")
        for day, item in rows:
            d = date.fromisoformat(day)
            st.markdown(f"- **{item['cards'][0]['title']}** · {d.month}월 {d.day}일")
        if rows:
            ui.muted("뉴스와 주가가 같은 날 움직였다고 꼭 뉴스 때문은 아니에요. 다른 이유도 함께 찾아봐요.")
    return rows


def news_reason_chips(symbol, rows, key):
    """매매 이유 칩 '뉴스 근거: 제목' → 일지 앞에 [뉴스] 말머리."""
    if not rows:
        return ""
    titles = [item["cards"][0]["title"] for _, item in rows]
    with st.container(key="news-chips"):
        picked = st.pills("뉴스 근거 (고르면 일지 앞에 붙어요)", [f"뉴스 근거: {t}" for t in titles], key=key)
    return nd.news_reason_prefix(picked.removeprefix("뉴스 근거: ")) if picked else ""


def stock_detail(symbol):
    provider = practice_provider
    name = provider.names()[symbol]
    quote = provider.quote(symbol)
    surge = quote["changePct"] >= detect.SURGE_PCT
    ui.app_bar(name, on_back=back_home, pill=ui.mode_pill("PRACTICE", "연습 모드"), badge=symbol)
    stock_mode_switch(symbol, "PRACTICE")
    with ui.card("inv-price"):
        price_block(provider, symbol, quote)
    if provider.headlines(symbol):
        with ui.card("inv-news"):
            st.markdown("**오늘의 공시 · 뉴스 (시안 · 가상 제목)**" if mock else "**오늘의 공시 · 뉴스**")
            st.markdown(ui.headlines_html(provider.headlines(symbol)), unsafe_allow_html=True)
    st.session_state["inv-stock-news"] = stock_news_card(symbol)
    if not any(w["symbol"] == symbol and w["account"] == "PRACTICE" for w in state["watch"]):
        st.button("관심 종목에 담기", key="inv-watch", width="stretch", on_click=watch_practice,
                  args=(symbol, quote["price"]))
    marks = checklist(symbol)
    count = sum(marks.values())
    if mock:
        mock_practice_order(symbol, marks, surge)
    else:
        practice_order(symbol, marks, surge, count)


def watch_practice(symbol, price):
    it.add_watch(state, symbol, price, "USER", "PRACTICE", today)
    save()
    toast("관심 종목에 담았어요.")


def mock_practice_order(symbol, marks, surge):
    label, strong = it.checklist_cta(sum(marks.values()))
    ui.muted("체크리스트를 건너뛰고 급등 직후 사면, 결과와 상관없이 AI 코치가 다음 날 Replay로 함께 돌아봐요.")
    with st.container(key="inv-buy-blue" if strong else "inv-buy-gray"):
        with st.form("inv-mock-order", border=False):
            if st.form_submit_button(label.replace("사기", "1주 사기"), type="primary", width="stretch"):
                record_checklist(symbol, marks, surge, "")
                toast("시안 화면이라 주문은 저장하지 않았어요.")
                st.rerun()


def practice_order(symbol, marks, surge, count):
    """기존 연습 주문 그대로 (가상 투자금 · 주문 전 1분 점검 · 투자 일지). 체크리스트만 앞에 붙었다."""
    prices, trades, names = market["prices"], market["trades"], market["names"]
    day = portfolio.latest_date(prices)
    closes = portfolio.close_on(prices, day)
    held = portfolio.holdings(trades, student_id)
    cash = portfolio.cash_balance(student["virtual_cash"], trades, student_id)
    price = closes[symbol]

    def place_order(order, journal):
        trade_id = store.append_trade(student_id, day, order["ticker"], order["side"], order["qty"], price,
                                      journal, path=market["trades_path"], prefix=market["prefix"])
        record_checklist(order["ticker"], order["checklist"], order["surge"], trade_id, order["side"])
        save()
        st.session_state["order_message"] = (f"{names[order['ticker']]} {order['qty']}주 {SIDE_LABELS[order['side']]} "
                                             f"완료 ({won(order['qty'] * price)})")
        return trade_id

    def finish_check(decision):
        """버튼 콜백: 1분 점검 뒤 '이대로 주문' 또는 '다시 생각'. 선택을 기록으로 남긴다."""
        order = st.session_state.pop("pending_order")
        added = " ".join(st.session_state.get("precheck_reason", "").split())
        trade_id = ""
        if decision == "BUY":
            journal = " / ".join(part for part in [order["journal"].strip(), added] if part)
            trade_id = place_order(order, journal)
        else:
            st.session_state["order_message"] = "주문을 취소했어요. 충분히 생각해 보고 정하면 돼요."
        store.append_precheck({"student_id": student_id, "date": day, "mode": market["mode"],
                               "ticker": order["ticker"], "qty": order["qty"], "patterns": order["patterns"],
                               "question": order["question"], "decision": decision,
                               "added_reason": added, "trade_id": trade_id})
        st.session_state.pop("precheck_reason", None)

    pending = st.session_state.get("pending_order")
    if pending and (pending["student_id"], pending["mode"], pending["ticker"]) != (student_id, market["mode"], symbol):
        pending = None  # 학생·시세 종류·종목을 바꾸면 점검 중이던 주문은 보여 주지 않는다
    if pending:
        ui.section("주문 전 1분 점검")
        with ui.card("precheck"):
            ui.muted(f"{names[pending['ticker']]} {pending['qty']}주 매수 전에 AI 코치가 한 번만 물어볼게요")
            for sentence in pending["facts"]:
                st.write(f"- {sentence}")
            if pending.get("rule"):
                st.success(f"지난번에 정한 나만의 규칙: {pending['rule']}")
            st.info(pending["question"])
            st.text_area("생각한 이유를 더 적어 보세요 (투자 일지에 함께 저장돼요)", key="precheck_reason")
            go_col, stop_col = ui.columns(2, key="precheck-buttons")
            go_col.button("이대로 주문하기", type="primary", width="stretch", on_click=finish_check, args=("BUY",))
            stop_col.button("다시 생각할게요", width="stretch", on_click=finish_check, args=("CANCEL",))
        return

    ui.section("가상으로 주문하기")
    if "order_message" in st.session_state:  # 주문한 자리 바로 위에 결과를 보여 준다
        st.success(st.session_state.pop("order_message"))
    with ui.card("order"):
        st.write(f"지금 **{names[symbol]}** {held.get(symbol, 0)}주 · 가상 현금 {won(cash)}")
        ui.muted(f"주문은 기준일 종가({won(price)})로 바로 체결돼요. 실제 돈은 오가지 않아요.")
        prefix = news_reason_chips(symbol, st.session_state.get("inv-stock-news", []), f"news-reason-{symbol}")
        side = st.radio("무엇을 할까요?", list(SIDE_LABELS), format_func=SIDE_LABELS.get, horizontal=True,
                        key="inv-side")
        label, strong = it.checklist_cta(count) if side == "BUY" else ("가상으로 팔기", True)
        with st.container(key="inv-buy-blue" if strong else "inv-buy-gray"):
            with st.form("order", clear_on_submit=True, border=False):
                qty = st.number_input("수량 (주)", min_value=1, value=1, step=1)
                journal = st.text_area("투자 일지: 왜 이렇게 하려고 하나요?", placeholder="안 적어도 주문할 수 있어요.")
                submitted = st.form_submit_button(label, type="primary", width="stretch")
    if side == "BUY":
        ui.muted("체크리스트를 건너뛰고 급등 직후 사면, 결과와 상관없이 다음 날 '실수에서 배우기'에서 AI 코치와 함께 돌아봐요.")
    if not submitted:
        return
    journal = prefix + journal  # 뉴스 근거 칩을 골랐으면 [뉴스] 말머리
    order = {"ticker": symbol, "side": side, "qty": int(qty), "journal": journal, "checklist": marks, "surge": surge}
    error = portfolio.check_order(side, int(qty), price, cash, held.get(symbol, 0))
    if error:
        st.error(error)
        return
    if side == "BUY":
        # 15번: 저장 전에 5번과 같은 기준으로 미리 검사. 걸리면 주문을 멈추고 AI가 질문 한 개
        detection, past = detect.precheck(trades, prices, student, symbol, int(qty), price, journal, day)
        if detection["patterns"]:
            with st.spinner("AI 코치가 주문 전에 확인하고 있어요..."):
                payload = detect.question_payload(student, detection, past, names, before=True)
                rule = detect.latest_rule(store.load_rules(), student_id, detection["patterns"])  # 16번
                if rule:
                    payload["my_rule"] = rule
                question = ui.ask_ai(
                    "precheck_question", payload, student_id,
                    demo_key=detect.precheck_demo_key(detection["patterns"]),
                    default={"question": detect.precheck_default_question(detection, names[symbol])})["question"]
            st.session_state["pending_order"] = {
                **order, "student_id": student_id, "mode": market["mode"], "patterns": detection["patterns"],
                "facts": detect.fact_sentences(detection, names[symbol], before=True), "question": question,
                "rule": rule}
            st.rerun()
    place_order(order, journal)
    st.rerun()


# ---------- ③ 부모님께 동의 요청 ----------

def build_report():
    if mock:
        return copy.deepcopy(demo["report"])
    if READY:
        return rv.make_report(ready_ctx)
    return iv.practice_report(student, market["trades"], market["prices"], state, store.load_questions(),
                              store.load_news_quiz())


def consent_request():
    ui.app_bar("실전 투자 시작하기", on_back=back_home)
    with ui.card("inv-steps"):
        st.markdown(ui.steps_html([
            ("부모님께 동의 요청", "내 연습 기록 리포트가 함께 전달돼요"),
            ("부모님이 안전장치 설정", "월 투자 한도, 살 수 있는 종목 범위, 알림"),
            ("연계 증권사 미성년자 계좌 개설", "부모님 명의 확인으로 비대면 개설 · 바로 실전 시작 (이 데모는 가상 계좌)")]),
            unsafe_allow_html=True)
    report = build_report()
    if READY:
        st.markdown(rv.report_html(report, student["name"]), unsafe_allow_html=True)
        st.markdown(rv.not_in_report_html(), unsafe_allow_html=True)
    else:
        st.markdown(ui.report_html(report), unsafe_allow_html=True)
    with ui.card("inv-msg"):
        default = (f"연습 모드에서 {report['weeks']}주 동안 공부했어요. "
                   "한 달 5만 원 안에서 ETF랑 큰 회사 주식부터 조금씩 해보고 싶어요!")
        message = st.text_area("부모님께 한마디", value=default, key="inv-consent-msg")
    left = it.cooldown_left(state["consent"], today)
    if status == it.PENDING:
        st.info("이미 요청을 보냈어요. 부모님 확인을 기다리고 있어요.")
    elif left:
        st.info(f"{left}일 뒤에 다시 요청할 수 있어요.")
    elif st.button("부모님께 요청 보내기", type="primary", width="stretch", key="inv-send"):
        it.transition(state, "REQUEST", message=" ".join(message.split()), report=report)
        state["consent"].pop("parent_note", None)  # 지난번 거절 때 남긴 한마디는 새 요청에서 지운다
        save()
        toast("부모님께 요청을 보냈어요. 확인을 기다리는 동안 연습 모드는 그대로 쓸 수 있어요.")
        go("home")
        st.rerun()


# ---------- ⑤ 실전 모드 홈 ----------

def available_cash():
    """지금 이체할 수 있는 돈 = 투자 봉투 남은 돈(이미 이체한 만큼 뺀) + 실전 계좌 현금."""
    real = state["real"]
    return max(0, invest_envelope - real.get("funded", 0)) + real.get("cash", 0)


def real_home():
    real_band()
    ui.app_bar("투자", pill=ui.mode_pill("REAL"))
    mode_switch()
    if status == it.REVOKED:
        st.warning("부모님이 실전 모드를 멈췄어요. 새로 사기는 막혀 있고, 가진 종목 보기와 팔기는 할 수 있어요.")
    view = iv.real_home(state, real_provider, today)
    g, s = view["guardrails"], view["summary"]
    with ui.card("inv-real-account"):
        st.markdown(ui.account_html("연계 증권 계좌 (미성년자)", "실제 돈", s["value"], s["changePct"], real=True)
                    + ui.limit_html(view["usage"]["buys"], g["monthlyLimit"],
                                    f"부모님 설정 · {it.SCOPES[g['scope']][0]} · 1회 {g['perOrderLimit']:,}원까지"),
                    unsafe_allow_html=True)
        ui.muted(f"용돈 계좌 투자 봉투에서 이체할 수 있는 돈: {won(available_cash())}")
    with ui.card("inv-list"):
        if not view["rows"]:
            ui.muted("아직 가진 종목이 없어요. 아래에서 종목을 골라 보세요.")
        for row in view["rows"]:
            action = "더 사기" if status == it.ACTIVE and row["surge"] else None
            if ui.stock_row(row, f"r-{row['symbol']}", action=action):
                go("order", row["symbol"])
                st.rerun()
    with ui.card("inv-real-pick"):
        names = view["names"]
        ticker = st.selectbox("다른 종목", list(names), format_func=lambda t: f"{names[t]} ({t})", key="inv-real-pick")
        st.button("이 종목 주문하기", key="inv-real-pick-go", width="stretch", on_click=go, args=("order", ticker))
    for w in view["waits"]:
        ui.muted(f"지켜보기 결과 · {w['name']}: 담은 날보다 다음 거래일({w['date'][5:].replace('-', '/')}) 종가가 {w['diff_pct']:+.1f}% "
                 "달랐어요. 결과보다 그때 기다린 이유를 떠올려 봐요.")
    r = view["record"]
    items = [("투자일지", f"{r['journalCount']}회"), ("급등주 지켜보기", f"{r['fomoWaitCount']}회"),
             ("근거 쓰고 산 비율", "-" if r["reasonRate"] is None else f"{round(r['reasonRate'] * 100)}%"),
             ("최대 비중", "-" if r["maxWeightPct"] is None else f"{r['maxWeightPct']}%")]
    with st.container(key="navy-record"):
        st.markdown(ui.record_html(items, note="한도와 종목 범위는 레벨로 바뀌지 않아요. 필요하면 내가 요청하고, "
                                               "부모님과 이야기해서 정해요."), unsafe_allow_html=True)
        st.button("부모님께 한도·범위 변경 요청하기", key="inv-change", width="stretch", on_click=go,
                  args=("change",), disabled=status != it.ACTIVE)
    notes = [n for n in state["notifications"] if n["to"] == "STUDENT"][-3:]
    if notes:
        ui.section("알림")
        with ui.card("inv-notes"):
            for n in reversed(notes):
                ui.muted(f"{n['at'][5:10].replace('-', '/')} · {n['text']}")


# ---------- ⑥ 실전 종목 상세 · 주문 (NEWS_MARKET_SPEC.md 8장 · images/09·10a·10b·11) ----------

def block(code, symbol):
    """막힌 이유 화면으로 (처음 걸린 코드 하나)."""
    st.session_state["inv-block"] = {"code": code, "symbol": symbol}
    go("blocked", symbol)


def guard_card(symbol, g, usage, instrument):
    left = g["monthlyLimit"] - usage["buys"]
    ok = it.in_scope(g["scope"], instrument)
    with ui.card("real-guard"):
        st.markdown("**부모님이 정한 안전장치**")
        st.markdown(
            f"<div class='guard'><div class='guard-row'><span>이번 달 투자 한도</span><b>{left:,}원 남음 / {g['monthlyLimit']:,}원</b></div>"
            f"<div class='lim-bar'><i style='--w:{min(100, round(usage['buys'] / g['monthlyLimit'] * 100))}%'></i></div>"
            f"<div class='guard-row'><span>한 번에 살 수 있는 돈</span><b>{g['perOrderLimit']:,}원까지</b></div>"
            f"<div class='guard-row'><span>살 수 있는 범위</span><b>{it.SCOPES[g['scope']][0]} · "
            f"<span class='{'guard-ok' if ok else 'chg-up'}'>{'이 종목 가능' if ok else '이 종목은 범위 밖'}</span></b></div>"
            f"<div class='guard-row'><span>급등주 확인 단계</span><b>{'켜짐 (+%d%% 이상)' % g['fomoThresholdPct'] if g['fomoCheck'] else '꺼짐'}</b></div>"
            f"<div class='guard-row'><span>미수·신용거래</span><b>항상 막혀 있어요</b></div></div>",
            unsafe_allow_html=True)
        if status == it.ACTIVE:
            st.button("한도·범위를 바꾸고 싶으면 부모님께 요청하기", key="real-guard-change", on_click=go, args=("change",))


def real_order(symbol):
    """실전 종목 상세 (09): 실전 배지 · '실제 돈' 배너 · 전날 종가 · 안전장치 · 뉴스 · 금액 칩 · 이유(필수) · 요약."""
    provider = real_provider
    name = provider.names()[symbol]
    quote = provider.quote(symbol)
    real, g = state["real"], state["guardrails"]
    held = real["holdings"].get(symbol, {}).get("qty", 0.0)
    real_band()
    ui.app_bar(name, on_back=back_home, pill=ui.mode_pill("REAL", "실전"), badge=symbol)
    stock_mode_switch(symbol, "REAL")
    if status == it.REVOKED:
        st.warning(it.BLOCK_MESSAGES["REVOKED"])
    if quote is None:
        st.warning(it.BLOCK_MESSAGES["QUOTE_STALE"])
        return
    with ui.card("real-price"):
        price_block(provider, symbol, quote, real=True)
    usage = it.month_usage(real["orders"], it.month_key(today))
    guard_card(symbol, g, usage, provider.instrument(symbol))
    rows = stock_news_card(symbol)
    if status == it.ACTIVE:
        if it.needs_fomo_check(g, quote) and st.session_state.get(f"inv-step-{symbol}") != "reason":
            fomo_step(symbol, quote)
        else:
            buy_card(symbol, quote, usage, rows, held)
    if held > 0:
        sell_step(symbol, held, quote)
    ui.muted("실전 시세: 지금은 공공데이터 전날 종가 (설정 하나로 증권사 실시간 전환) · 주문: 학교 프로젝트라 Mock 체결 · "
             "원금 손실이 날 수 있어요" + (" · 가격·수량은 시안용 예시예요" if mock else ""))


def fomo_step(symbol, quote):
    memory = demo["fomoMemory"] if mock else iv.fomo_memory(market["trades"], market["prices"], student)
    head, body = iv.fomo_line(memory, quote["changePct"])
    with ui.card("inv-fomo"):
        st.markdown(f"<div class='fomo-title'>{escape(head)}</div>", unsafe_allow_html=True)
        st.write(body)
        st.markdown("<div class='fomo-note'>부모님이 켜 둔 '급등주 확인 단계'예요</div>", unsafe_allow_html=True)
        if st.button("오늘은 지켜보기 (관심 종목에 담기)", type="primary", width="stretch", key="inv-wait"):
            watch_real(symbol, quote)
            st.rerun()
        if st.button("근거 쓰고 계속하기", width="stretch", key="inv-reason"):
            st.session_state[f"inv-step-{symbol}"] = "reason"
            st.rerun()


def watch_real(symbol, quote):
    it.add_watch(state, symbol, quote["price"], "FOMO_WAIT", "REAL", today)
    save()
    toast("관심 종목에 담았어요. 다음 거래일 종가로 '기다렸다면' 차이를 알려 줄게요.")
    go("home")


def buy_card(symbol, quote, usage, rows, held):
    real, g = state["real"], state["guardrails"]
    fomo = it.needs_fomo_check(g, quote)
    chips = it.chip_states(g, usage)
    amount_key = f"inv-amount-{symbol}"
    if st.session_state.get(amount_key) not in [a for a, ok in chips if ok]:
        st.session_state[amount_key] = next((a for a, ok in chips if ok), None)
    amount = st.session_state[amount_key]
    with ui.card("real-buy"):
        st.markdown(f"**실제로 사기** <span class='muted'>내 실전 계좌 · 보유 {it.qty_label(held)}</span>",
                    unsafe_allow_html=True)
        with st.container(key="inv-chips", horizontal=True):
            for a, ok in chips:
                st.button(f"{a:,}원", key=f"inv-chip-{a}", disabled=not ok, width="stretch",
                          type="primary" if a == amount else "secondary",
                          on_click=st.session_state.__setitem__, args=(amount_key, a))
        if amount is None:
            ui.muted("이번 달 남은 한도나 1회 상한 안에서 고를 수 있는 금액이 없어요.")
        prefix = news_reason_chips(symbol, rows, f"real-news-reason-{symbol}")
        reason = st.text_area(f"사는 이유 (꼭 써야 해요 · {it.MIN_REASON_CHARS}자 이상)", key=f"inv-why-{symbol}",
                              placeholder="예: 3분기 실적 발표에서 영업이익이 늘었다는 공시를 확인했어요.")
        left = g["monthlyLimit"] - usage["buys"]
        if amount:
            st.markdown(ui.summary_html([
                ("예상 수량", f"약 {it.qty_label(it.estimate_qty(amount, quote['price']))}"),
                ("수수료(예상)", f"약 {it.fee_of(amount):,}원"),
                ("이번 달 남은 한도", f"{left:,} → {left - amount:,}원"),
                ("부모님 알림", "주문하면 바로" if g["notifyParentOnTrade"] else "꺼져 있어요")]),
                unsafe_allow_html=True)
        if amount is None:
            return
        with st.container(key="inv-buy-real"):
            clicked = st.button(f"실제로 {amount:,}원 사기", width="stretch", key="inv-buy")
    if not clicked:
        return
    full_reason = (prefix + reason).strip()
    req = {"side": "BUY", "symbol": symbol, "amount": amount, "reason": full_reason, "fomoAcknowledged": fomo}
    code = precheck(req, quote)
    if code == "REASON_REQUIRED":
        st.error(it.BLOCK_MESSAGES["REASON_REQUIRED"])  # 입력란 강조 (화면을 바꾸지 않는다)
        return
    if code:
        block(code, symbol)
        st.rerun()
    st.session_state["inv-pending"] = {"symbol": symbol, "amount": amount, "reason": full_reason, "fomo": fomo}
    go("confirm", symbol)
    st.rerun()


def precheck(req, quote):
    """주문 확인 화면으로 가기 전에 같은 validate_order로 미리 본다 (실제 주문은 확인 뒤 submit_real_order에서 다시 검사)."""
    real = state["real"]
    usage = it.month_usage(real["orders"], it.month_key(today))
    held = real["holdings"].get(req["symbol"], {}).get("qty", 0.0)
    fresh = real_provider.is_fresh(quote, clock) if hasattr(real_provider, "is_fresh") else True
    return it.validate_order(req, state["guardrails"], state["consent"], usage, quote,
                             real_provider.instrument(req["symbol"]), available_cash(), held, fresh=fresh,
                             market_open=updater.market_open(clock), source=getattr(real_provider, "source", "eod"))


def confirm_view():
    """주문 확인 (10a): 요약 + 일지 미리보기 + '실제 돈이 나가요' 체크 전에는 버튼이 회색·비활성."""
    p = st.session_state["inv-pending"]
    symbol, amount = p["symbol"], p["amount"]
    quote = real_provider.quote(symbol)
    name = real_provider.names()[symbol]
    g = state["guardrails"]
    left = g["monthlyLimit"] - it.month_usage(state["real"]["orders"], it.month_key(today))["buys"]
    real_band()
    ui.app_bar("주문 확인", on_back=lambda: go("order", symbol), pill=ui.mode_pill("REAL", "실전"))
    d = date.fromisoformat(quote["basDt"])
    with ui.card("confirm"):
        ui.muted(f"{name} · 전날 종가로 체결 · 소수점 주문")
        st.markdown(f"<div class='done-big'>{amount:,}원 사기</div>", unsafe_allow_html=True)
        st.markdown(ui.summary_html([
            ("예상 수량", f"약 {it.qty_label(it.estimate_qty(amount, quote['price']))}"),
            (f"기준가 ({d.month}월 {d.day}일 종가)", f"{quote['price']:,}원"),
            ("수수료(예상)", f"약 {it.fee_of(amount):,}원"),
            ("이번 달 남은 한도", f"{left:,} → {left - amount:,}원")]), unsafe_allow_html=True)
        st.markdown(f"<div class='wnote'><small>사는 이유 · 투자일지에 저장</small><span>{escape(p['reason'])}</span></div>",
                    unsafe_allow_html=True)
    with ui.card("risk"):
        agreed = st.checkbox("실제 돈이 나가요. 주가가 내려가면 넣은 돈보다 적게 돌려받을 수 있다는 걸 알고 있어요.",
                             key=f"inv-risk-{symbol}-{amount}")
    with st.container(key="inv-buy-real"):
        go_buy = st.button(f"실제로 {amount:,}원 사기", width="stretch", key="inv-confirm", disabled=not agreed)
    st.button("다시 생각해 볼래요", width="stretch", key="inv-cancel", on_click=go, args=("order", symbol))
    if not go_buy:
        return
    req = {"side": "BUY", "symbol": symbol, "amount": amount, "reason": p["reason"], "fomoAcknowledged": p["fomo"]}
    result = broker.submit_real_order(state, broker.MockBrokerAdapter(), real_provider, req, today, available_cash(),
                                      now=clock)
    if not result["ok"]:
        block(result["code"], symbol)
        st.rerun()
    save()
    st.session_state.pop("inv-pending", None)
    st.session_state.pop(f"inv-step-{symbol}", None)
    st.session_state["inv-done"] = {**result["order"], "name": name, "at": clock.strftime("%H:%M")}
    go("done", symbol)
    st.rerun()


def done_view():
    """주문 완료 (10b): 체결 수량·가격(기준일 종가)·시각, 부모 알림 / 일지 저장(+20P) / 내일 Replay 안내."""
    o = st.session_state["inv-done"]
    d = date.fromisoformat(o["basDt"])
    real_band()
    ui.app_bar("주문 완료", back=False, pill=ui.mode_pill("REAL", "실전"))
    with ui.card("done"):
        st.markdown(f"<div class='done-big'>{o['name']} {it.qty_label(o['qty'])} 샀어요</div>", unsafe_allow_html=True)
        ui.muted(f"{o['price']:,}원({d.month}월 {d.day}일 종가)에 체결 · {o['at']} · 수수료 {o.get('fee', 0):,}원")
        journal_pts = (f" (+{config_journal_points()}P)" if len(o.get("reason", "")) >= it.MIN_REASON_CHARS else "")
        st.markdown(f"- 부모님께 알림을 보냈어요 (종목 · 금액 · 쓴 이유)\n"
                    f"- 사는 이유를 투자일지에 저장했어요{journal_pts}\n"
                    "- 내일 '실수에서 배우기'와 미션 탭에서 이 주문을 함께 돌아봐요 (결과와 상관없이)")
    st.button("실전 계좌로", type="primary", width="stretch", on_click=lambda: (go("home"), st.session_state.pop("inv-done", None)))


def config_journal_points():
    from engine import rewards
    return rewards.JOURNAL_POINTS


def blocked_view():
    """막힐 때 (11): 코드별 제목 · 설명 · 다음 행동 버튼 하나."""
    b = st.session_state["inv-block"]
    code, symbol = b["code"], b["symbol"]
    title, body, label, action = it.BLOCK_SCREENS.get(code, ("주문할 수 없어요", it.BLOCK_MESSAGES.get(code, ""), "돌아가기", "holdings"))
    if code == "OVER_PER_ORDER" and state.get("guardrails"):
        title = f"한 번에 {state['guardrails']['perOrderLimit']:,}원까지 살 수 있어요"
    if mode == "REAL":
        real_band()
    ui.app_bar("실전 주문", on_back=lambda: go("order", symbol) if mode == "REAL" else back_to_practice(symbol=symbol),
               pill=ui.mode_pill("REAL", "실전"))
    with ui.card("blocked"):
        st.markdown(f"<span class='block-code'>{code}</span>", unsafe_allow_html=True)
        st.markdown(f"### {title}")
        st.write(body)

        def act():
            st.session_state.pop("inv-block", None)
            if action == "consent":
                go("consent")
            elif action in ("practice", "practice_view"):
                back_to_practice(symbol=symbol)
            elif action == "watch":
                quote = real_provider.quote(symbol)
                if quote:
                    watch_real(symbol, quote)
            elif action == "holdings":
                go("home")
            elif action == "reload":
                updater.save_state("stock_eod", {**updater.load_state("stock_eod"), "last_attempt": None})
                go("order", symbol)
            else:  # amount · reserve
                go("order", symbol)
        st.button(label, key="inv-block-act", width="stretch", on_click=act)


def show_block(code, symbol):
    st.error(it.BLOCK_MESSAGES[code])
    if code == "OUT_OF_SCOPE" and symbol in practice_provider.names():
        def to_practice():
            back_to_practice(symbol=symbol)
        st.button("연습 모드에서 보기", key="inv-to-practice", on_click=to_practice)


def sell_step(symbol, held, quote):
    with ui.card("inv-sell"):
        st.markdown(f"**가진 주식 팔기** · 지금 {it.qty_label(held)} 가지고 있어요")
        part = st.radio("얼마나 팔까요?", ["전부", "절반"], horizontal=True, key=f"inv-sell-part-{symbol}")
        qty = held if part == "전부" else round(held / 2, 4)
        reason = st.text_input("파는 이유 (투자일지에 저장)", key=f"inv-sell-why-{symbol}")
        if st.button(f"실제로 {it.qty_label(qty)} 팔기", width="stretch", key="inv-sell"):
            req = {"side": "SELL", "symbol": symbol, "qty": qty, "reason": reason}
            result = broker.submit_real_order(state, broker.MockBrokerAdapter(), real_provider, req, today, 0, now=clock)
            if not result["ok"]:
                show_block(result["code"], symbol)
                return
            save()
            toast(f"{it.qty_label(qty)} 팔았어요. 판 돈은 실전 계좌에 남아요 (한도는 회복되지 않아요).")
            go("home")
            st.rerun()


# ---------- 6-6 한도·범위 변경 요청 ----------

def change_request():
    g = state["guardrails"]
    real_band()
    ui.app_bar("한도·범위 변경 요청", on_back=back_home, pill=ui.mode_pill("REAL", "실전"))
    ui.muted(f"지금 설정: {it.guardrail_summary(g)}")
    ui.muted("레벨이나 점수로 자동으로 바뀌지 않아요. 바꾸고 싶은 이유를 내가 직접 쓰고, 부모님이 정해요.")
    with ui.card("inv-change"):
        same = "그대로"
        limit = st.radio("한 달 투자 한도", [same] + [f"{v // 10_000}만 원" for v in it.MONTHLY_LIMITS], horizontal=True,
                         key="inv-ch-limit")
        scope = st.radio("살 수 있는 범위", [same] + [v[0] for v in it.SCOPES.values()], key="inv-ch-scope")
        message = st.text_area("왜 바꾸고 싶나요?", key="inv-ch-msg")
        attach = st.checkbox("이번 달 내 투자 기록을 함께 보내기", key="inv-ch-attach")
        if st.button("부모님께 요청 보내기", type="primary", width="stretch", key="inv-ch-send"):
            wanted_limit = None if limit == same else it.MONTHLY_LIMITS[[f"{v // 10_000}만 원" for v in it.MONTHLY_LIMITS].index(limit)]
            wanted_scope = None if scope == same else next(k for k, v in it.SCOPES.items() if v[0] == scope)
            try:
                it.request_change(state, message, wanted_limit, wanted_scope, attach)
            except ValueError as e:
                st.error(str(e))
                return
            save()
            toast("부모님께 변경 요청을 보냈어요.")
            go("home")
            st.rerun()
    if state["change_requests"]:
        ui.section("보낸 요청")
        words = {"SENT": "부모님 확인 중", "APPROVED": "승인", "DECLINED": "그대로 두기", "ADJUSTED": "조정해서 승인"}
        with ui.card("inv-change-list"):
            for r in reversed(state["change_requests"]):
                note = f" · 부모님 메모: {r['parentNote']}" if r.get("parentNote") else ""
                ui.muted(f"{r['at'][5:10].replace('-', '/')} · {it.change_label(r)} · {words[r['status']]}{note}")


# ---------- 실전 진입 화면: 전환 확인 시트 · 안전 체크리스트 · 실전 띠 · 자동 복귀 ----------

def real_band():
    """모든 실전 화면 맨 위 남색 띠 + 노란 '실전' 배지 (위에 붙어 있어 내려도 보인다). 10분 무조작 확인도 여기서."""
    if not SAFETY:
        return
    st.markdown("<div class='real-band' role='note'><span class='real-band-badge'><i></i>실전</span>"
                "<span>실제 돈으로 거래해요 · 부모님이 정한 한도·범위 안에서만</span></div>", unsafe_allow_html=True)
    idle_guard()


@st.fragment(run_every=config.REAL_SAFETY_IDLE_CHECK_SEC)
def idle_guard():
    """실전 화면에 한 번. 30초마다 확인해 10분 동안 조작이 없으면 연습으로 돌려보낸다 (조작이 없으면 화면이 다시 그려지지 않으므로)."""
    if st.session_state.get("inv-stage") in ("real", "real_view_sell") and \
            rs.should_auto_exit(safety_state(), updater.now_kst()):
        back_to_practice(f"{config.REAL_SAFETY_IDLE_MIN}분 동안 쉬어서 연습으로 돌아왔어요")
        st.rerun(scope="app")


def switch_view():
    """전환 확인 시트: '실전으로 바꿀까요?' — 지금(연습·가상 머니) → 바뀌면(실전·잃을 수 있어요)."""
    copy = rs.switch_sheet_copy(safety_state(), safety_now, settings_changed_at=rs.settings_changed_at(state),
                                consent_activated_at=rs.consent_activated_at(state))
    target = st.session_state.get("inv-real-target", ("home", None))
    name = practice_provider.names().get(target[1]) or real_provider.names().get(target[1]) or "투자"
    st.markdown(f"<div class='sheet-dim' aria-hidden='true'><b>{escape(name)}</b><span>연습 · 가상 머니 화면</span></div>",
                unsafe_allow_html=True)
    with st.container(key="switch-sheet"):
        notice = f"<b>{escape(copy['notice_b'])}</b> {escape(copy['notice'])}".strip()
        st.markdown(
            "<div role='dialog' aria-modal='true' aria-labelledby='switch-title' class='sheet'>"
            "<i class='sheet-grip'></i><span class='real-band-badge'><i></i>실전</span>"
            "<h2 id='switch-title' class='sheet-title'>실전으로 바꿀까요?</h2>"
            "<div class='sheet-sub'>지금부터는 연습 머니가 아니라 <b>진짜 돈</b>이 쓰여요.</div>"
            "<div class='sheet-compare'><div class='sc-p'><b><i></i>지금 · 연습</b><span>가상 머니<br>잃어도 괜찮아요</span></div>"
            "<span class='sc-arrow' aria-hidden='true'>→</span>"
            "<div class='sc-r'><b><i></i>바뀌면 · 실전</b><span>내 실전 계좌의 돈<br>잃을 수 있어요</span></div></div>"
            f"<div class='sheet-notice'>☑ {notice}</div></div>", unsafe_allow_html=True)

        def go_on():
            nxt = next_stage(rs.SWITCH)
            if nxt == rs.CHECKLIST:
                reset_checks()
                st.session_state["inv-stage"] = "checklist"
            else:
                keep_safety(rs.enter_real(safety_state(), updater.now_kst()))
                open_real(nxt)

        with st.container(key="sheet-go"):
            st.button(f"● {copy['cta']}", key="switch-go", width="stretch", on_click=go_on)
        with st.container(key="sheet-stay"):
            st.button("연습에 그대로 있기", key="switch-stay", width="stretch",
                      on_click=back_to_practice, kwargs={"symbol": target[1]})
        ui.muted("오늘 이미 체크했다면 체크리스트 없이 이 확인만 나오고, 버튼이 \"실전으로 들어가기\"로 바뀌어요.")


def checklist_view():
    """실전투자 안전 체크리스트 6개: 하나씩 직접 눌러야 열린다 ('모두 확인' 버튼은 없다)."""
    real, g = state["real"], state["guardrails"]
    usage = it.month_usage(real["orders"], it.month_key(today))
    bas = None
    for code in list(real["holdings"]) + list(real_provider.names()):
        q = real_provider.quote(code) if code in real_provider.names() else None
        if q and q.get("basDt"):
            bas = date.fromisoformat(q["basDt"][:10])
            break
    items = rs.render_items(g["monthlyLimit"] - usage["buys"], g["monthlyLimit"], g["perOrderLimit"],
                            getattr(real_provider, "source", config.REAL_QUOTE_SOURCE), bas)
    checked = [bool(st.session_state.get(k, False)) for k in CHECK_KEYS]
    target = st.session_state.get("inv-real-target", ("home", None))
    ui.app_bar("실전 들어가기 전", on_back=lambda: back_to_practice(symbol=target[1]))
    st.markdown(
        "<div class='check-band'><span class='real-band-badge'><i></i>실전 들어가기 전</span>"
        + (f"<div class='check-head'>{growby.img_html('real_checklist', 'bubble', 72, decorative=True)}"
           "<h2 class='check-title'>실전투자 안전 체크리스트</h2></div>" if config.GROWBY_MASCOT else
           "<div class='check-shield' aria-hidden='true'>🛡</div><h2 class='check-title'>실전투자 안전 체크리스트</h2>")
        + "<div class='check-sub'>여기부터는 연습이 아니에요. 6가지를 하나씩 눌러 확인해야 실전 화면이 열려요.</div>"
        f"<div class='check-prog'><span>확인한 항목</span><b>{sum(checked)} / {rs.ITEM_COUNT}</b></div>"
        f"<div class='check-bar'><i style='--w:{round(sum(checked) / rs.ITEM_COUNT * 100)}%'></i></div></div>",
        unsafe_allow_html=True)
    for i, (item, key) in enumerate(zip(items, CHECK_KEYS)):
        on = st.session_state.get(key, False)
        with st.container(key=f"safe-item-{'on-' if on else ''}{i}"):
            st.checkbox(f"{item['no']}. {item['title']}", key=key)
            extra = ""
            if item["id"] == "real_money":
                extra = ("<div class='sheet-compare mini'><div class='sc-p'><b><i></i>연습</b><span>가상 머니 · 밝은 화면</span></div>"
                         "<div class='sc-r'><b><i></i>실전</b><span>진짜 돈 · 남색 화면</span></div></div>")
            if item.get("limit"):
                lim = item["limit"]
                used = 0 if not lim["monthly"] else round((lim["monthly"] - lim["left"]) / lim["monthly"] * 100)
                extra = (f"<div class='lim-bar'><i style='--w:{min(100, max(0, used))}%'></i></div>"
                         f"<div class='lim-foot'>남은 한도 <b>{lim['left']:,}원</b> / {lim['monthly']:,}원 · "
                         f"한 번에 {lim['per_order']:,}원까지</div>")
            st.markdown(f"<div class='safe-body'>{escape(item['body'])}</div>{extra}", unsafe_allow_html=True)
    ui.muted("확인한 시각은 기록돼 부모님 화면에도 \"오늘 안전 체크 완료\"로 보여요. 오늘 다시 실전에 들어올 땐 짧은 확인만 나와요.")
    checked = [bool(st.session_state.get(k, False)) for k in CHECK_KEYS]

    def enter():
        if not rs.can_enter([bool(st.session_state.get(k, False)) for k in CHECK_KEYS]):
            return
        keep_safety(rs.record_check(safety_state(), updater.now_kst()), persist=True)
        reset_checks()
        open_real(next_stage(rs.CHECKLIST))

    with st.container(key="sheet-go" if rs.can_enter(checked) else "check-wait"):
        st.button(f"● {rs.cta_label(checked)}", key="check-go", width="stretch", disabled=not rs.can_enter(checked),
                  on_click=enter)
    st.button("오늘은 연습만 할래요", key="check-stay", width="stretch", on_click=back_to_practice,
              kwargs={"symbol": target[1]})


# ---------- 화면 고르기 ----------

if SAFETY and stage == "switch":
    switch_view()
elif SAFETY and stage == "checklist":
    checklist_view()
elif screen["screen"] == "stock" and screen["symbol"] in practice_provider.names():
    stock_detail(screen["symbol"])
elif READY and screen["screen"] == "ready":
    ready_screen()
elif READY and screen["screen"] == "reflect":
    reflect_screen()
elif READY and screen["screen"] == "ready_quiz":
    ready_quiz_screen()
elif READY and screen["screen"] == "ready_report" and ready_ctx["r"].can_request_consent:
    ready_report_screen()
elif screen["screen"] == "consent" and status != it.ACTIVE and not can_request:
    ready_screen()  # 기준을 다 채우기 전에는 동의 요청 화면 대신 진행 화면 (남은 것이 보이게)
elif screen["screen"] == "consent" and status != it.ACTIVE:
    consent_request()
elif screen["screen"] == "order" and screen["symbol"] in real_provider.names():
    real_order(screen["symbol"])
elif screen["screen"] == "confirm" and st.session_state.get("inv-pending"):
    confirm_view()
elif screen["screen"] == "done" and st.session_state.get("inv-done"):
    done_view()
elif screen["screen"] == "blocked" and st.session_state.get("inv-block"):
    blocked_view()
elif screen["screen"] == "change" and status == it.ACTIVE:
    change_request()
elif mode == "REAL":
    real_home()
else:
    practice_home()
