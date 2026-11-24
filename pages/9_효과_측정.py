"""11번 효과 측정 대시보드 (교사·운영자용). 사이드바 '데모 설정'에서 들어온다.

보여 주는 것: 학생 전체의 주차별 행동 변화, 앱 활동, 콘텐츠 추가 후보, 학생별 행동 횟수.
보여 주지 않는 것: 수익률·이익·손실, 역량 점수, 학생 답·일지 원문.
"""

import pandas as pd
import streamlit as st

import config
import ui_common as ui
from engine import detect, effect, portfolio, quotes, replay, store
from config import REAL_VIRTUAL_CASH

ui.setup("효과 측정 대시보드", "📊")
students = store.load_students()
trades, prices, allowance = store.load_trades(), store.load_prices(), store.load_allowance()
missions, lessons, rules = store.load_missions(), store.load_lessons(), store.load_rules()
questions, unlocks = store.load_questions(), store.load_unlocks()
weeks = replay.week_starts(allowance)

today = portfolio.latest_date(prices)  # 데모의 '오늘': 앱에서 한 매수는 이 날짜로 기록된다
patterns = effect.weekly_patterns(students, trades, prices, weeks, until=today)  # 주차별은 코칭 전 기록만
real_trades = store.load_trades(store.REAL_TRADES_PATH)  # 투자 탭(실제 시세)에서 한 매수 = 앱에서 한 매수
real_prices = quotes.load_quotes()["prices"] if len(real_trades) else None
app_buys = [d for s in students for d in detect.detect(real_trades, real_prices, {**s, "virtual_cash": REAL_VIRTUAL_CASH})] \
    if real_prices is not None else []
compare = effect.before_after(students, trades, prices, today, app_buys)
mission_rows = effect.weekly_missions(missions, weeks)
money = effect.weekly_money(students, trades, allowance, prices, weeks)
act = effect.activity(lessons, rules, store.load_prechecks(), questions, unlocks, students)


def show_before_after(column, title, key):
    """코칭 전(기본 4주) → 앱에서 한 매수. 둘 다 낮을수록 좋은 지표."""
    before, after = compare["before"][key], compare["after"][key]
    if after is None:
        column.metric(title, "-" if before is None else f"{before}%")
        column.caption(f"코칭 전 {before}% · 앱에서 한 매수가 아직 없어요." if before is not None else "아직 매수가 없어요.")
        return
    column.metric(title, f"{after}%", delta=None if before is None else f"{after - before:+d}%p", delta_color="inverse")
    column.caption(f"코칭 전 {before}% → 앱에서 {after}% (매수 {compare['after']['buys']}번)")


def week_name(week):
    return replay.week_label(week, weeks).split(" ")[0]


def show_change(column, title, rows, key, lower_is_better=False):
    result = effect.first_last(rows, key)
    if result is None:
        latest = effect.latest_value(rows, key)
        if latest is None:
            column.metric(title, "-")
            column.caption("아직 기록이 없어요.")
        else:  # 한 주 결과만 있으면 그 값을 보여 준다
            column.metric(title, f"{latest['value']}%")
            column.caption(f"아직 {week_name(latest['week'])} 결과만 있어요.")
        return
    column.metric(title, f"{result['last']}%", delta=f"{result['last'] - result['first']:+d}%p",
                  delta_color="inverse" if lower_is_better else "normal")
    column.caption(f"{week_name(result['first_week'])} {result['first']}% → "
                   f"{week_name(result['last_week'])} {result['last']}%")


ui.app_bar("효과 측정 대시보드", badge="교사·운영자용")
ui.muted(f"가상 학생 {len(students)}명 데모 데이터예요. 통계적 효과가 아니라 측정 방식을 보여 주는 시안이에요. "
         "기본 4주 기록은 코칭 전 행동이고, 시연에서 앱으로 한 매수는 따로 모아 코칭 전과 비교해요. "
         "수익률과 역량 점수는 보지 않아요.")

ui.section("한눈에 보기")
with ui.card("summary"):
    left, right = ui.columns(2, key="summary-1", align="top")
    show_before_after(left, "근거 없는 매수 비율", "no_reason_pct")
    show_before_after(right, "실수 패턴 매수 비율", "mistake_pct")
    left, right = ui.columns(2, key="summary-2", align="top")
    show_change(left, "미션 달성률", mission_rows, "done_pct")
    show_change(right, "저축률", money, "save_pct")
    left, right = ui.columns(2, key="summary-3", align="top")
    show_change(left, "원함 지출 비율", money, "impulse_pct", lower_is_better=True)
    st.caption("매수 비율 두 칸은 기본 4주(코칭 전)와 앱에서 한 매수를 비교해요. "
               "실수 패턴 매수 = 급등 추격·몰빵·근거 없음 중 하나라도 걸린 매수. "
               "저축률 = 모으기 봉투 순증가 ÷ 용돈 입금. 원함 지출 = 편의점·카페·디저트 ÷ 전체 지출.")

ui.section("주차별 변화 (코칭 전 기본 4주)")
with ui.card("weekly"):
    chart = pd.DataFrame({
        "주차": [week_name(w) for w in weeks],
        "실수 패턴 매수(%)": [r["mistake_pct"] for r in patterns],
        "미션 달성률(%)": [r["done_pct"] for r in mission_rows],
        "저축률(%)": [r["save_pct"] for r in money],
        "원함 지출(%)": [r["impulse_pct"] for r in money],
    }).set_index("주차")
    ui.line_chart(chart, height=260)
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
    stage_title = "연습 습관 단계" if config.INVEST_CONSENT_TRACK else "실전 준비 단계"
    st.markdown(f"**{stage_title}** · " + " · ".join(f"{n}단계 {c}명" for n, c in act["stages"].items()))

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
