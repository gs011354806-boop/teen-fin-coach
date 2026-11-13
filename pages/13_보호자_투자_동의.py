"""④ 보호자 · 실전 투자 동의와 안전장치 (투자 탭 동의 기반 2트랙, 2026-11-13).

부모 앱이 따로 없어서 '앱 안 보호자 모드' 화면으로 만들었다 (보호자 리포트와 같은 방식).
- 요청이 오면(PENDING): 연습 리포트 확인 → 한도·범위·알림·급등주 확인 단계 설정 → 동의 + 계좌 개설(Mock) 또는 거절.
- 동의 뒤(ACTIVE): 설정 바꾸기(학생에게 알림), 학생의 한도·범위 변경 요청 결정(승인/거절/조정 + 메모), 실전 모드 멈추기.
- 미수·신용거래는 항상 막혀 있고 바꿀 수 없다.
투자 탭을 ?mock으로 연 상태면 같은 시안 상태를 보여 주고 저장하지 않는다.
"""

import streamlit as st

import ui_common as ui
from engine import broker, invest_track as it, store

student = ui.setup("보호자 · 투자 동의", "👪")
student_id = student["student_id"]
mock_box = st.session_state.get("invest-mock-state") if st.session_state.get("invest-mock") else None
if mock_box:
    state, name = mock_box["state"], broker.load_demo()["student"]["name"]
else:
    state = it.migrate(store.load_invest(student_id) or it.new_state(student_id), student_id)
    name = student["name"]
status = state["consent"]["status"]
LIMIT_LABELS = {v: f"{v // 10_000}만 원" for v in it.MONTHLY_LIMITS}


def save():
    if not mock_box:
        store.save_invest(student_id, state)


def guardrail_inputs(current, key):
    """한도 · 범위 · 알림 · 급등주 확인 단계 (미수·신용은 항상 차단). 고른 값을 돌려준다."""
    with ui.card(f"pg-limit-{key}"):
        st.markdown("**한 달 투자 한도**")
        limit_label = st.segmented_control("한 달 투자 한도", list(LIMIT_LABELS.values()),
                                           default=LIMIT_LABELS.get(current["monthlyLimit"], LIMIT_LABELS[50_000]),
                                           key=f"pg-limit-w-{key}", label_visibility="collapsed")
        ui.muted("1회 주문은 한도의 절반까지 · 용돈 계좌에서 이체")
    with ui.card(f"pg-scope-{key}"):
        scopes = list(it.SCOPES)
        scope = st.radio("살 수 있는 범위", scopes, index=scopes.index(current["scope"]),
                         format_func=lambda s: it.SCOPES[s][0], captions=[v[1] for v in it.SCOPES.values()],
                         key=f"pg-scope-w-{key}")
    with ui.card(f"pg-toggles-{key}"):
        notify = st.toggle("매수·매도 알림 받기", value=current["notifyParentOnTrade"], key=f"pg-notify-{key}",
                           help="주문할 때마다 알림 (종목, 금액, 아이가 쓴 이유)")
        fomo = st.toggle("급등주 매수 전 확인 단계", value=current["fomoCheck"], key=f"pg-fomo-{key}",
                         help=f"하루 +{it.FOMO_THRESHOLD_PCT}% 이상 오른 종목은 근거를 쓴 뒤에 주문")
        st.toggle("미수 · 신용거래 (항상 차단)", value=False, disabled=True, key=f"pg-margin-{key}")
    limit = next((v for v, label in LIMIT_LABELS.items() if label == limit_label), current["monthlyLimit"])
    return {"monthly_limit": limit, "scope": scope, "notify_parent": notify, "fomo_check": fomo}


ui.app_bar(f"{name}의 실전 투자 동의", badge="보호자 화면 (부모 앱 대신 · 시연)")
if mock_box:
    ui.muted("투자 탭 시안(?mock) 상태예요. 저장하지 않아요.")
if "pg-message" in st.session_state:
    st.success(st.session_state.pop("pg-message"))

if status == it.NONE:
    st.info("아직 실전 투자 동의 요청이 없어요. 아이가 투자 탭에서 요청하면 여기에 연습 리포트와 함께 보여요.")

elif status == it.PENDING:
    consent = state["consent"]
    if consent.get("report_snapshot"):
        st.markdown(ui.report_html(consent["report_snapshot"], title="아이의 연습 리포트"), unsafe_allow_html=True)
    if consent.get("student_message"):
        with ui.card("pg-msg"):
            st.markdown("**아이가 남긴 말**")
            st.write(consent["student_message"])
    chosen = guardrail_inputs(it.make_guardrails(), "new")
    ui.muted("실제 돈으로 거래하므로 원금 손실이 생길 수 있어요. 설정은 이 화면에서 언제든 바꾸거나 실전 모드를 멈출 수 있어요. "
             "(이 데모는 가상 증권사로 계좌를 만들고 실제 주문은 보내지 않아요)")
    if st.button("동의하고 계좌 개설로 이동", type="primary", width="stretch", key="pg-approve"):
        state["guardrails"] = it.make_guardrails(chosen["monthly_limit"], chosen["scope"], chosen["notify_parent"],
                                                 chosen["fomo_check"])
        broker.open_real_account(state, broker.MockBrokerAdapter())
        save()
        st.session_state["pg-message"] = "동의하고 미성년자 계좌(가상)를 연결했어요. 아이의 투자 탭이 실전 모드로 바뀌어요."
        st.rerun()
    if st.button("이번에는 동의하지 않기", width="stretch", key="pg-reject"):
        it.transition(state, "REJECT")
        save()
        st.session_state["pg-message"] = "이번 요청은 동의하지 않았어요. 아이는 연습 모드를 계속 쓸 수 있어요."
        st.rerun()

elif status == it.ACTIVE:
    pending = [r for r in state["change_requests"] if r["status"] == "SENT"]
    if pending:
        ui.section("아이의 변경 요청")
        for r in pending:
            with ui.card(f"pg-cr-{r['id']}"):
                st.markdown(f"**{it.change_label(r)}**")
                st.write(r["message"])
                if r["attachRecord"]:
                    real = state["real"]
                    record = it.monthly_record(real, state["watch"], it.month_key(r["at"]))
                    rate = "-" if record["reasonRate"] is None else f"{round(record['reasonRate'] * 100)}%"
                    ui.muted(f"아이가 첨부한 기록: 투자일지 {record['journalCount']}회 · 급등주 지켜보기 "
                             f"{record['fomoWaitCount']}회 · 근거 쓰고 산 비율 {rate}")
                decision = st.radio("결정", ["APPROVED", "DECLINED", "ADJUSTED"], horizontal=True,
                                    format_func={"APPROVED": "승인", "DECLINED": "거절", "ADJUSTED": "조정"}.get,
                                    key=f"pg-dec-{r['id']}")
                adjust = {}
                if decision == "ADJUSTED":
                    adjust["monthly_limit"] = st.selectbox("조정한 한도", list(LIMIT_LABELS),
                                                           format_func=LIMIT_LABELS.get, key=f"pg-adj-l-{r['id']}")
                    adjust["scope"] = st.selectbox("조정한 범위", list(it.SCOPES),
                                                   format_func=lambda s: it.SCOPES[s][0], key=f"pg-adj-s-{r['id']}")
                note = st.text_input("메모 (아이에게 보여요)", key=f"pg-note-{r['id']}")
                if st.button("결정 보내기", type="primary", width="stretch", key=f"pg-send-{r['id']}"):
                    it.decide_change(state, r["id"], decision, note, **adjust)
                    save()
                    st.session_state["pg-message"] = "결정을 아이에게 알렸어요."
                    st.rerun()

    ui.section("안전장치 설정")
    chosen = guardrail_inputs(state["guardrails"], "edit")
    if st.button("설정 저장", type="primary", width="stretch", key="pg-save"):
        it.update_guardrails(state, **chosen)
        save()
        st.session_state["pg-message"] = "설정을 저장했어요. 바뀐 내용은 아이에게 알려요."
        st.rerun()

    notes = [n for n in state["notifications"] if n["to"] == "PARENT"][-5:]
    if notes:
        ui.section("받은 알림")
        with ui.card("pg-notes"):
            for n in reversed(notes):
                ui.muted(f"{n['at'][5:16].replace('-', '/').replace('T', ' ')} · {n['text']}")

    ui.section("실전 모드 멈추기")
    with ui.card("pg-revoke"):
        ui.muted("멈추면 새로 사기만 막혀요. 아이는 가진 종목을 보거나 팔 수 있어요. 다시 시작하려면 아이가 다시 요청해요.")
        if st.button("실전 모드 멈추기", width="stretch", key="pg-revoke-btn"):
            it.transition(state, "REVOKE")
            save()
            st.session_state["pg-message"] = "실전 모드를 멈췄어요."
            st.rerun()

else:
    word = "동의하지 않았어요" if status == it.REJECTED else "실전 모드를 멈춘 상태예요"
    st.info(f"지금은 {word}. 아이가 다시 요청하면 여기에서 다시 정할 수 있어요 "
            f"(거절·멈춤 뒤 {it.REQUEST_COOLDOWN_DAYS}일 뒤부터 다시 요청 가능).")
