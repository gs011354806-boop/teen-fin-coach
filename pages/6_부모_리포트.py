"""부모 AI 코칭 리포트 (보호자용).

보여 주는 것: 저축률 변화, 미션 수행률 변화, 이번 달 부모 미션.
보여 주지 않는 것: 아이의 투자 일지 원문, 학생 답 원문, 내부 점수.
"""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import parent, replay, store

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
