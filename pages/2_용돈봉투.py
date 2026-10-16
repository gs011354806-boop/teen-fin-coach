"""용돈봉투 화면. 입출금 형식은 우리은행 청소년 마이데이터를 가정한다."""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import cards, envelope, store
from ui_common import won

ENVELOPE_LABELS = {"SPEND": "쓰기", "SAVE": "모으기", "INVEST": "투자연습"}
CATEGORY_LABELS = {"CONVENIENCE": "편의점", "CAFE_DESSERT": "카페·디저트",
                   "MEAL": "식사·분식", "MART": "마트",
                   "SHOPPING": "쇼핑", "TRANSPORT": "교통", "OTHER": "기타"}

student = ui.setup("용돈봉투", "✉️", active="envelope")
student_id = student["student_id"]
ratio = student["envelope_ratio"]
goal = student["saving_goal"]

allowance = store.load_allowance()
today = envelope.latest_date(allowance)
balance = envelope.balances(allowance, student_id)

ui.app_bar("용돈봉투", badge="가상 용돈 기록")
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

    share = envelope.impulse_share_pct(allowance, student_id)
    with ui.card("needs-wants"):
        ui.concept_card(
            store.load_concepts()["NEEDS_VS_WANTS"], key="envelope",
            intro=(f"알아 두면 좋은 개념 · 이번 달 지출 중 편의점·카페·디저트가 {share:.0f}%예요"
                   if share is not None else "알아 두면 좋은 개념"))

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

ui.section("내 소비로 계산한 카드 혜택")
for card in cards.load_cards():
    result = cards.monthly_benefit(card, allowance, student_id)
    peer = cards.peer_comparison(allowance, student_id, student["gender"])
    with ui.card(f"card-{card['card_id']}"):
        st.markdown(f"**{card['issuer']} {card['name']}** · {card['kind']} · {card['eligible_age']}")
        ui.muted(f"편의점 결제 {card['benefit_rate'] * 100:.0f}% 적립 (1회 최대 {card['per_payment_cap']:,}P, "
                 f"월 최대 {card['monthly_cap']:,}P) · 전월 {won(card['min_prev_month_spend'])} 이상 이용 시 · "
                 "교통 이용액은 실적 제외")
        left, right = ui.columns(2, key=f"card-{card['card_id']}")
        left.metric("이번 달 예상 적립", f"{result['benefit']:,}P" if result["meets_condition"] else "0P")
        right.metric("실적 인정 금액", won(result["performance"]))
        if result["meets_condition"]:
            st.write(f"이번 달 편의점 결제 {result['eligible_count']}건({won(result['eligible_amount'])})으로 "
                     f"약 **{result['benefit']:,}P**를 받을 수 있었어요. 실적 조건 {won(card['min_prev_month_spend'])}도 채웠어요.")
        else:
            st.write(f"실적이 {won(card['min_prev_month_spend'])}보다 적어서 이번 달엔 적립이 없어요. "
                     f"조건을 채웠다면 약 {result['benefit']:,}P였어요.")
        if peer:
            more = "더 자주" if peer["diff"] > 0 else "덜"
            ui.muted(f"또래(같은 성별, 20세 미만) 평균보다 편의점을 {more} 이용해요: "
                     f"내 결제 중 {peer['mine']:.0f}% · 또래 {peer['peer']:.0f}%")
        st.info("혜택을 받으려고 더 쓰는 건 손해예요. 필요한 지출에서만 혜택을 챙겨요.")
        ui.muted(f"추천·가입 권유가 아니에요. 배달앱·온라인쇼핑·앱스토어 적립은 이 데이터에 없어 빠졌어요. "
                 f"혜택 정보: {card['source']} · 확인 {card['checked']}. 실제 조건은 우리카드에서 확인해 주세요.")
