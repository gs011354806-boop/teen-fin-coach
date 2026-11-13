"""9번 Skill Unlock: 실전 준비 단계 화면 (투자 탭 동의 2트랙에서는 '연습 습관 단계').

연습 과정(근거 기록·비중·보유 기간·돌아보기·미션)을 보고 다음 단계를 연다. 수익률은 보지 않고 점수도 없다.
- config.INVEST_CONSENT_TRACK = True: 단계는 연습 습관 기록일 뿐, 실전 진입·한도·종목 범위와 연결하지 않는다.
  실전 투자는 투자 탭에서 부모님 동의로 시작한다 (INVEST_TAB_SPEC.md 5장). 단계와 기록은 그대로 둔다.
- False(예전): 2단계 = 실제 시세 연습, 3단계 = 보호자에게 실전 신청 보내기 (시안, 실제 주문과 연결하지 않음).
"""

import streamlit as st

import config
import ui_common as ui
from engine import portfolio, store, unlock

CONSENT = config.INVEST_CONSENT_TRACK
TITLE = "연습 습관 단계" if CONSENT else "실전 준비 단계"
student = ui.setup(TITLE, "🔓")
student_id = student["student_id"]
prices = store.load_prices()
conds = unlock.conditions(student, store.load_trades(), prices, store.load_trades(store.REAL_TRADES_PATH),
                          store.load_lessons(), store.load_rules(), store.load_missions())
current = unlock.stage(store.load_unlocks(), student_id)
names, opens = unlock.names(), unlock.opens()
if CONSENT:
    OPEN_MESSAGES = {2: "2단계를 열었어요. 근거·비중·돌아보기 습관이 자리 잡고 있어요.",
                     3: "3단계를 열었어요. 연습 습관을 스스로 점검했어요."}
else:
    OPEN_MESSAGES = {2: "2단계를 열었어요. 이제 투자연습에서 실제 시세로 연습할 수 있어요.",
                     3: "보호자에게 실전 신청을 보냈어요 (시안). 실제 주문은 연결하지 않아요."}


def open_stage(target):
    """버튼 콜백: 조건을 다시 확인하고 단계를 연 기록을 남긴다."""
    if unlock.can_open(current, target, conds):
        store.append_unlock(student_id, target, portfolio.latest_date(prices))
        st.session_state["unlock_message"] = OPEN_MESSAGES[target]


ui.app_bar(TITLE, badge="과정으로 열리는 단계")
ui.muted("수익이 아니라 연습 과정을 보고 다음 단계를 열어요. 한 번 연 단계는 다시 잠기지 않아요.")
if CONSENT:
    with ui.card("unlock-consent"):
        ui.service_row(ui.MARKET, "📈", "실전 투자는 레벨이 아니라 부모님 동의로 시작해요",
                       "단계는 투자 한도·종목 범위와 상관없어요 · 투자 탭에서 동의 요청하기", key="go-invest")
if "unlock_message" in st.session_state:
    st.success(st.session_state.pop("unlock_message"))

ui.section("지금 단계")
with ui.card("unlock-now"):
    st.markdown(f"**{current}단계 · {names[current]}**")
    ui.muted(opens[current])
    if current < 2 and ui.demo_mode() and not CONSENT:
        ui.muted("시연 모드라 실제 시세는 잠금 없이 볼 수 있어요.")

for target in (2, 3):
    ui.section(f"{target}단계 · {names[target]}")
    with ui.card(f"unlock-{target}"):
        ui.muted(opens[target])
        if current >= target:
            st.success("열렸어요")
            if target == 2 and not CONSENT:
                ui.service_row(ui.MARKET, "📈", "실제 시세로 연습하기", "투자연습에서 시세 종류를 '실제 시세'로", key="go-real")
            continue
        for i, c in enumerate(conds[target]):
            with st.container(key=f"cond-{target}-{i}"):  # 조건 제목과 그 사실을 한 묶음으로
                st.markdown(f"{'✅' if c['met'] else '⬜'} **{c['title']}**")
                ui.muted(c["fact"])
        if current < target - 1:
            ui.muted(f"{target - 1}단계를 먼저 열면 이 단계로 갈 수 있어요.")
        elif unlock.can_open(current, target, conds):
            label = (f"{target}단계 열기" if CONSENT or target == 2 else "보호자에게 실전 신청 보내기 (시안)")
            st.button(label, type="primary", width="stretch", key=f"open-{target}",
                      on_click=open_stage, args=(target,))
        else:
            ui.muted("아직 연습 중인 조건이 있어요. 하나씩 채워 봐요.")

if not CONSENT:
    ui.muted("실전 소수점 투자는 보호자 승인 아래 시작하는 제안 시안이에요. 이 데모는 실제 주문과 연결되지 않아요.")
