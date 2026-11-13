"""20번 마이데이터 연결 예시 화면.

팀이 카드 소비 통계로 만든 가상 마이데이터(19세 제외)를 불러와, 첫 주 연습할 것과 목표까지의 계산을 보여 준다.
계산은 engine/mydata.py, AI는 첫 인사 문장만 쓴다. 실제 마이데이터 연결은 하지 않는다.
"""

import streamlit as st

import ui_common as ui
from engine import mydata, store

student = ui.setup("마이데이터 연결", "🔗")
profiles = mydata.load_profiles()
concepts = store.load_concepts()

ui.app_bar("마이데이터 연결", badge="연결 예시 화면")
ui.muted(f"출처: {mydata.SOURCE} · 청소년 {len(profiles)}명 (19세 제외)")

ui.section("예시 고르기")
with ui.card("mydata-pick"):
    skill = st.selectbox("어떤 친구의 데이터를 불러올까요?", mydata.SKILL_ORDER,
                         format_func=lambda s: f"{mydata.START[s][0]}가 필요한 친구", key="mydata_skill")
    index_key = f"mydata_index_{skill}"
    if st.button("다른 친구 예시", width="stretch"):
        st.session_state[index_key] = st.session_state.get(index_key, 0) + 1
    profile = mydata.pick(profiles, skill, st.session_state.get(index_key, 0))

connected_key = ("mydata_connected", profile["user_id"])
ui.section("우리은행 마이데이터")
with ui.card("mydata-connect"):
    st.write("용돈 계좌와 카드 사용 내역을 불러와 나에게 맞는 코칭을 시작해요.")
    consent = mydata.consent_status(profile)
    if consent == "done":
        st.success(f"✅ 보호자 동의 완료 (만 {mydata.CONSENT_AGE}세 미만이라 보호자 동의가 필요해요)")
    elif consent == "needed":
        st.warning(f"만 {mydata.CONSENT_AGE}세 미만이라 보호자 동의를 받은 뒤 연결해요 (시안).")
    if not st.session_state.get(connected_key):
        label = "보호자 동의 받고 불러오기 (예시)" if consent == "needed" else "마이데이터 불러오기 (예시)"
        if st.button(label, type="primary", width="stretch"):
            st.session_state[connected_key] = True
            st.rerun()
        ui.muted("예시 화면이라 실제 계좌와 연결하지 않아요.")
        st.stop()
    st.success("불러왔어요 (예시 데이터)")

plan = mydata.goal_plan(profile)
sentences = mydata.facts(profile, plan)
practice, concept_id, mission_text = mydata.START[profile["weak_skill"]]

ui.section("1. 불러온 정보")
with ui.card("mydata-info"):
    left, right = ui.columns(2, key="mydata-info-1", align="top")
    left.metric("학년", f"{mydata.school_label(profile)} · {int(profile['age'])}세")
    right.metric("용돈", ui.won(int(profile["monthly_allowance"])))
    right.caption(f"한 달 기준 · {profile['allowance_cycle']}")
    left, right = ui.columns(2, key="mydata-info-2", align="top")
    left.metric("월평균 지출", ui.won(int(profile["avg_monthly_spend"])))
    right.metric("목표", f"{profile['goal_item']}")
    right.caption(f"{plan['goal']:,}원 · {plan['months']}개월")

ui.section("2. 이번 주 연습할 것")
with ui.card("mydata-practice"):
    st.markdown(f"**{practice}**")
    st.write(mission_text)
    if concept_id in concepts:
        ui.concept_card(concepts[concept_id], key=f"mydata-{profile['user_id']}", intro="함께 보면 좋은 개념")
    else:
        st.info(f"콘텐츠 없음: {concept_id}")

ui.section("3. 목표까지")
with ui.card("mydata-goal"):
    for s in sentences:
        st.write(f"- {s}")

ui.section("AI 코치 첫 인사")
welcome_key = ("mydata_welcome", profile["user_id"])
with ui.card("mydata-welcome"):
    if welcome_key not in st.session_state:
        if st.button("AI 코치에게 첫 인사 받기", type="primary", width="stretch"):
            st.session_state[welcome_key] = ui.ask_ai(
                "mydata_welcome", mydata.payload(profile, plan, sentences), student["student_id"],
                demo_key=profile["user_id"], default=mydata.default_message(profile),
                check=mydata.message_check(sentences))["message"]
            st.rerun()
    else:
        st.info(st.session_state[welcome_key])
