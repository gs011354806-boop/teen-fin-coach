"""11번 효과 측정 대시보드 (교사·운영자용). 사이드바 '데모 설정'에서 들어온다.

보여 주는 것: 학생 전체의 주차별 행동 변화, 앱 활동, 콘텐츠 추가 후보, 학생별 행동 횟수.
보여 주지 않는 것: 수익률·이익·손실, 역량 점수, 학생 답·일지 원문.
"""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import detect, effect, replay, store

ui.setup("효과 측정 대시보드", "📊")
students = store.load_students()
trades, prices, allowance = store.load_trades(), store.load_prices(), store.load_allowance()
missions, lessons, rules = store.load_missions(), store.load_lessons(), store.load_rules()
questions, unlocks = store.load_questions(), store.load_unlocks()
weeks = replay.week_starts(allowance)

patterns = effect.weekly_patterns(students, trades, prices, weeks)
mission_rows = effect.weekly_missions(missions, weeks)
money = effect.weekly_money(students, trades, allowance, prices, weeks)
act = effect.activity(lessons, rules, store.load_prechecks(), questions, unlocks, students)


def week_name(week):
    return replay.week_label(week, weeks).split(" ")[0]


def show_change(column, title, rows, key, lower_is_better=False):
    result = effect.first_last(rows, key)
    if result is None:
        column.metric(title, "-")
        column.caption("비교할 기록이 아직 없어요.")
        return
    column.metric(title, f"{result['last']}%", delta=f"{result['last'] - result['first']:+d}%p",
                  delta_color="inverse" if lower_is_better else "normal")
    column.caption(f"{week_name(result['first_week'])} {result['first']}% → "
                   f"{week_name(result['last_week'])} {result['last']}%")


ui.app_bar("효과 측정 대시보드", badge="교사·운영자용")
ui.muted(f"가상 학생 {len(students)}명 데모 데이터예요. 통계적 효과가 아니라 측정 방식을 보여 주는 시안이에요. "
         "기본 4주 기록은 코칭 전 행동이고, 시연에서 학생이 한 활동이 쌓이면 숫자가 바뀌어요. "
         "수익률과 역량 점수는 보지 않아요.")

ui.section("한눈에 보기")
with ui.card("summary"):
    left, right = ui.columns(2, key="summary-1", align="top")
    show_change(left, "실수 패턴 매수 비율", patterns, "mistake_pct", lower_is_better=True)
    show_change(right, "미션 달성률", mission_rows, "done_pct")
    left, right = ui.columns(2, key="summary-2", align="top")
    show_change(left, "저축률", money, "save_pct")
    show_change(right, "원함 지출 비율", money, "impulse_pct", lower_is_better=True)
    st.caption("실수 패턴 매수 = 급등 추격·몰빵·근거 없음 중 하나라도 걸린 매수. "
               "저축률 = 모으기 봉투 순증가 ÷ 용돈 입금. 원함 지출 = 편의점·카페·디저트 ÷ 전체 지출.")

ui.section("주차별 변화")
with ui.card("weekly"):
    chart = pd.DataFrame({
        "주차": [week_name(w) for w in weeks],
        "실수 패턴 매수(%)": [r["mistake_pct"] for r in patterns],
        "미션 달성률(%)": [r["done_pct"] for r in mission_rows],
        "저축률(%)": [r["save_pct"] for r in money],
        "원함 지출(%)": [r["impulse_pct"] for r in money],
    }).set_index("주차")
    st.line_chart(chart, height=240)
    table = {"주차": [week_name(w) for w in weeks], "매수": [r["buys"] for r in patterns]}
    table.update({p: [r[p] for r in patterns] for p in detect.PATTERNS})
    table["결과 나온 미션"] = [r["graded"] for r in mission_rows]
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")

ui.section("앱 활동")
with ui.card("activity"):
    left, right = ui.columns(2, key="activity-1", align="top")
    left.metric("실수 돌아보기", f"{act['lessons']}건")
    left.caption(f"학생 {act['lesson_students']}명")
    right.metric("나만의 규칙", f"{act['rules']}개")
    left, right = ui.columns(2, key="activity-2", align="top")
    left.metric("사기 전 1분 점검", f"{act['prechecks']}번")
    added = "-" if act["precheck_added_pct"] is None else f"{act['precheck_added_pct']}%"
    left.caption(f"다시 생각 {act['precheck_cancel']}번 · 이유 더 적음 {added}")
    right.metric("개념 질문", f"{act['questions']}개")
    right.caption(f"카드 없음 {act['questions_none']}개 · 종목 질문 {act['questions_advice']}개")
    st.markdown("**실전 준비 단계** · " + " · ".join(f"{n}단계 {c}명" for n, c in act["stages"].items()))

ui.section("콘텐츠 추가 후보")
with ui.card("missing"):
    missing = effect.missing_concepts(questions)
    if missing:
        ui.muted("개념 카드가 없어 AI가 답하지 못한 질문이에요. content/concepts에 카드를 추가할 후보예요.")
        for q in missing:
            st.write(f"- {q}")
    else:
        st.info("아직 답하지 못한 질문이 없어요.")

ui.section("학생별 행동")
with ui.card("students"):
    rows = effect.per_student(students, trades, prices, lessons, rules, missions, unlocks)
    st.dataframe(pd.DataFrame({
        "학생": [r["name"] for r in rows],
        "단계": [f"{r['stage']}단계" for r in rows],
        "매수": [r["buys"] for r in rows],
        "다시 볼 매수": [r["mistakes"] for r in rows],
        "돌아보기": [r["lessons"] for r in rows],
        "규칙": [r["rules"] for r in rows],
        "해낸 미션": [r["missions_done"] for r in rows],
    }), hide_index=True, width="stretch")
    ui.muted("행동 횟수만 보여 줘요. 학생 답과 투자 일지 원문, 점수는 보여 주지 않아요.")
