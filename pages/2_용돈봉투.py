"""용돈봉투 화면. 입출금 형식은 우리은행 청소년 마이데이터를 가정한다."""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import envelope, store
from ui_common import won

ENVELOPE_LABELS = {"SPEND": "쓰기", "SAVE": "모으기", "INVEST": "투자연습"}
CATEGORY_LABELS = {"CONVENIENCE": "편의점", "CAFE": "카페", "FOOD": "음식",
                   "SHOPPING": "쇼핑", "TRANSPORT": "교통", "OTHER": "기타"}

student = ui.setup("용돈봉투", "✉️", active="envelope")
student_id = student["student_id"]
ratio = student["envelope_ratio"]
goal = student["saving_goal"]

allowance = store.load_allowance()
today = envelope.latest_date(allowance)
balance = envelope.balances(allowance, student_id)

ui.app_bar("용돈봉투", badge="청소년 마이데이터 연결")
ui.muted(f"{today} 기준 · 데모용 가상 내역이에요.")

if "envelope_message" in st.session_state:
    st.success(st.session_state.pop("envelope_message"))

with ui.card("balances"):
    for column, name in zip(ui.columns(3, key="balances"), envelope.ENVELOPES):
        column.metric(f"{ENVELOPE_LABELS[name]} 봉투", won(balance[name]))

ui.section(f"모으기 목표: {goal['item']}")
with ui.card("goal"):
    st.progress(envelope.goal_progress_pct(balance["SAVE"], goal["amount"]) / 100)
    st.write(f"{won(goal['amount'])} 중 **{won(balance['SAVE'])}** 모았어요.")

ui.section("용돈 받기")
with ui.card("deposit"):
    weekly = student["weekly_allowance"]
    split = envelope.split_allowance(weekly, ratio)
    ui.muted("이번 용돈은 이렇게 나뉘어요: "
             + " · ".join(f"{ENVELOPE_LABELS[name]} {won(split[name])}" for name in envelope.ENVELOPES))
    if st.button(f"용돈 {won(weekly)} 받기", type="primary", width="stretch"):
        store.append_allowance(student_id, today, envelope.deposit_entries(weekly, ratio))
        st.session_state["envelope_message"] = f"용돈 {won(weekly)}을 봉투에 나눠 담았어요."
        st.rerun()

ui.section("용돈 나누는 비율")
with ui.card("ratio"):
    with st.form("ratio", border=False):
        inputs = {}
        for column, name in zip(ui.columns(3, key="ratio"), envelope.ENVELOPES):
            inputs[name] = column.number_input(f"{ENVELOPE_LABELS[name]} (%)", min_value=0,
                                               max_value=100, value=ratio[name], step=5)
        ratio_submitted = st.form_submit_button("비율 저장", width="stretch")

if ratio_submitted:
    new_ratio = {name: int(value) for name, value in inputs.items()}
    error = envelope.check_ratio(new_ratio)
    if error:
        st.error(error)
    else:
        store.save_envelope_ratio(student_id, new_ratio)
        st.session_state["envelope_message"] = "비율을 저장했어요. 다음 용돈부터 이렇게 나눠요."
        st.rerun()

ui.section("이번 달 가장 많이 쓴 곳은?")
with ui.card("spending"):
    spent = envelope.spending(allowance, student_id)
    if len(spent):
        by_category = envelope.spending_by_category(allowance, student_id)
        st.bar_chart(pd.Series({CATEGORY_LABELS[c]: total for c, total in by_category.items()},
                               name="쓴 돈(원)"), height=220)
        st.dataframe(
            pd.DataFrame({
                "날짜": [d[5:] for d in spent["date"]],
                "분류": spent["category"].map(CATEGORY_LABELS),
                "내용": spent["memo"],
                "금액": [won(-a) for a in spent["amount"]],
            }),
            hide_index=True, width="stretch")
    else:
        st.info("아직 지출 내역이 없어요.")

    with st.expander("전체 입출금 내역 보기"):
        mine = allowance[allowance["student_id"] == student_id].iloc[::-1]
        st.dataframe(
            pd.DataFrame({
                "날짜": [d[5:] for d in mine["date"]],
                "봉투": mine["envelope"].map(ENVELOPE_LABELS),
                "내용": mine["memo"],
                "금액": [f"{a:+,}원" for a in mine["amount"]],
            }),
            hide_index=True, width="stretch")
