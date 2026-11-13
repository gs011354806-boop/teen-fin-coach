"""부모 AI 코칭 리포트 (보호자용).

보여 주는 것: 저축률 변화, 미션 수행률 변화, 실전 준비 단계(9번), 이번 달 부모 미션.
보여 주지 않는 것: 아이의 투자 일지 원문, 학생 답 원문, 내부 점수.
"""

import pandas as pd
import streamlit as st

import config
import ui_common as ui
from engine import parent, replay, store, unlock

student = ui.setup("보호자 리포트", "👪")
student_id = student["student_id"]
allowance = store.load_allowance()
weeks = replay.week_starts(allowance)
saving = parent.weekly_saving_rates(student_id, allowance, weeks)
missions = parent.weekly_mission_rates(student_id, store.load_missions(), weeks)
saving_change = parent.change(saving)
mission_change = parent.change(missions)
focus = parent.parent_focus(student_id, store.load_coaching(), store.load_lessons())
base_mission = parent.parent_mission(focus)

first, last = weeks[0], replay.week_end(weeks[-1])
ui.app_bar(f"{student['name']} 보호자 리포트", badge="보호자용")
ui.muted(f"이번 달 ({first[5:].replace('-', '/')}~{last[5:].replace('-', '/')}) · "
         "아이의 투자 일지와 답변 원문, 내부 점수는 보여 드리지 않아요.")


def week_name(week):
    return replay.week_label(week, weeks).split(" ")[0]


def show_change(column, title, result, empty_text):
    if result is None:
        column.metric(title, "-")
        column.caption(empty_text)
        return
    column.metric(title, f"{result['last']}%", delta=f"{result['diff']:+d}%p")
    column.caption(f"{week_name(result['first_week'])} {result['first']}% → "
                   f"{week_name(result['last_week'])} {result['last']}%")


ui.section("이번 달 변화")
with ui.card("changes"):
    col_saving, col_mission = ui.columns(2, key="changes", align="top")
    show_change(col_saving, "저축률", saving_change, "아직 용돈 기록이 없어요.")
    show_change(col_mission, "미션 수행률", mission_change, "아직 결과가 나온 미션이 없어요.")

    chart = pd.DataFrame({
        "주차": [week_name(w) for w in weeks],
        "저축률(%)": [r["rate"] for r in saving],
        "미션 수행률(%)": [r["rate"] for r in missions],
    }).set_index("주차")
    st.line_chart(chart, height=220)
    st.caption("저축률 = 그 주 모으기 봉투에 남은 돈 ÷ 그 주 받은 용돈. "
               "미션 수행률 = 결과가 나온 미션 중 해낸 미션의 비율.")

stage = unlock.stage(store.load_unlocks(), student_id)
if config.INVEST_CONSENT_TRACK:  # 투자 탭 동의 2트랙: 실전은 레벨이 아니라 보호자 동의로
    ui.section("실전 투자 동의")
    with ui.card("invest-consent"):
        ui.service_row(ui.PARENT_INVEST, "🛡️", "실전 투자 동의와 안전장치",
                       "아이의 동의 요청 확인 · 한도·범위·알림 설정 · 변경 요청 결정", key="parent-invest")
    ui.section("연습 습관 단계")
else:
    ui.section("실전 준비 단계")
with ui.card("unlock"):
    st.markdown(f"**{stage}단계 · {unlock.names()[stage]}**")
    if stage >= 3 and not config.INVEST_CONSENT_TRACK:
        st.info("아이가 실전 소수점 투자 신청을 보냈어요. 보호자가 승인하면 시작하는 흐름의 시안이에요.")
    ui.muted("단계는 수익이 아니라 근거 기록·비중·보유 기간·미션 같은 연습 과정으로 열려요. "
             + ("투자 한도·범위와는 연결되지 않아요." if config.INVEST_CONSENT_TRACK
                else "이 데모는 실제 주문과 연결되지 않아요."))

ui.section("이번 달 부모 미션")
key = ("parent_mission", student_id, base_mission)
with ui.card("parent-mission"):
    if key not in st.session_state:
        st.write(base_mission)
        if st.button("AI 코치에게 다듬어 받기", type="primary", width="stretch"):
            payload = parent.mission_payload(student, base_mission, saving_change, mission_change)
            st.session_state[key] = ui.ask_ai("parent_mission", payload, student_id,
                                              default={"text": base_mission})["text"]
            st.rerun()
    else:
        st.success(st.session_state[key])
