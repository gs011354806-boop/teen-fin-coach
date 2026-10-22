"""② AI 행동 미션 루프: 진단 → 미션 → 대안 선택 → 주말 Replay → 재조정. 맨 아래 17번 성장 회고.

데모는 data/의 4주 기록을 한 주씩 재생한다 (docs/DATA.md의 coaching_weeks.csv).
"""

import pandas as pd
import streamlit as st

import ui_common as ui
from engine import growth, mission, replay, simulate, store
from ui_common import won

student = ui.setup("이번 주 미션", "🎯", active="mission")
student_id = student["student_id"]
goal = student["saving_goal"]
trades, allowance, prices = store.load_trades(), store.load_allowance(), store.load_prices()
weeks = replay.week_starts(allowance)
coaching = store.load_coaching()
missions = store.load_missions()
mine = coaching[coaching["student_id"] == student_id]
latest = mine.iloc[-1] if len(mine) else None


def metrics_of(week):
    return replay.week_metrics(student, trades, allowance, prices, week)


def label(week):
    return replay.week_label(week, weeks)


def week_missions(week):
    return missions[(missions["student_id"] == student_id) & (missions["week_start"] == week)]


def when(finish):
    return "지금 기록으로는 닿기 어려워요" if not finish else f"{finish[:4]}년 {int(finish[5:7])}월쯤"


def student_info():
    return {"name": student["name"], "grade": student["grade"]}


def mission_text(goal_spec, summary):
    """목표 숫자는 코드가 정하고, LLM은 그 숫자가 들어간 문장만 쓴다."""
    def check(result):
        missing = [w for w in goal_spec["must_include"] if w not in result["text"]]
        if missing:
            raise ValueError(f"목표 숫자 빠짐: {missing}")

    payload = {"student": student_info(), "skill": goal_spec["skill"], "level": goal_spec["level"],
               "goal": {"phrase": goal_spec["phrase"], "must_include": goal_spec["must_include"]},
               "diagnosis_summary": summary}
    default = {"text": f"{goal_spec['phrase']}에 도전해 보세요."}
    return ui.ask_ai("weekly_mission", payload, student_id, demo_key=goal_spec["phrase"],
                     default=default, check=check)["text"]


def show_diagnosis(good, practice, summary, key):
    with ui.card(f"diagnosis-{key}"):
        ui.muted("잘하고 있는 것")
        ui.chips(good, "good")
        ui.muted("이번 주 연습할 것")
        ui.chips(practice, "practice")
        st.write(summary)
    concept_name = mission.concept_for(practice[0])
    if concept_name:
        with ui.card(f"concept-{key}"):
            ui.concept_card(store.load_concepts()[concept_name], key=f"mission-{key}",
                            intro=f"이번 주 연습할 것 '{practice[0]}'에 도움이 되는 개념이에요")


def show_missions(rows, metrics=None):
    for m in rows.itertuples():
        st.success(m.text)
        if metrics is not None:
            mark = "✅ 해냈어요" if m.done == "TRUE" else "🔁 다음 주에 다시 해 봐요"
            ui.muted(f"{mark} · {replay.result_sentence(m.target_metric, metrics)}")


def show_replay(row, with_title=True):
    rows = week_missions(row["week_start"])
    done = int((rows["done"] == "TRUE").sum())
    if with_title:
        ui.section(f"{label(row['week_start'])} 주말 Replay")
    with ui.card(f"replay-{row['week_start']}"):
        st.write(f"미션 {len(rows)}개 중 **{done}개**를 해냈어요.")
        show_missions(rows, metrics_of(row["week_start"]))
        st.write(f"{goal['item']} 목표 달성 예상: {when(row['goal_date_before'])} → "
                 f"**{when(row['goal_date_after'])}**")
        st.info(row["replay_comment"])


def show_growth():
    """17번 나의 성장 회고: 1주차와 Replay까지 끝낸 최근 주 비교. 숫자는 코드, 이야기는 AI."""
    ui.section("나의 성장 회고")
    reached = growth.reached_weeks(coaching, weeks, student_id)
    if len(reached) < 2:
        ui.card("growth").write("한 주 이상 미션을 하고 주말 Replay까지 마치면, 처음과 비교한 회고를 볼 수 있어요.")
        return
    first, last = reached[0], reached[-1]
    facts, trend = growth.behavior_facts(student, trades, allowance, prices, first, last, weeks,
                                         with_changes=True)
    facts = facts + growth.activity_facts(student_id, missions, store.load_lessons(), store.load_rules(), reached)
    with ui.card("growth"):
        ui.muted(f"{growth.short_label(first, weeks)}와 {growth.short_label(last, weeks)}를 비교했어요")
        for sentence in facts:
            st.write(f"- {sentence}")
        reviews = st.session_state.setdefault("growth_reviews", {})
        key = (student_id, last, tuple(facts))
        if key not in reviews:
            if st.button("AI 코치와 돌아보기", type="primary", width="stretch"):
                practice = latest["practice"].split("|") if latest is not None and latest["practice"] else []
                reviews[key] = ui.ask_ai(
                    "growth_review", growth.review_payload(student, first, last, weeks, facts, trend, practice),
                    student_id, demo_key=last, default=growth.default_review(facts),
                    check=growth.numbers_check(facts))
                st.rerun()
            return
        st.info(reviews[key]["story"])
        st.success(f"다음에 이어 갈 것: {reviews[key]['next']}")


def finish():
    """흐름이 중간에 멈춰도 성장 회고는 맨 아래에 보이게 한다."""
    show_growth()
    st.stop()


ui.app_bar("이번 주 미션", badge="AI 코치")
ui.muted("데모: 9/7~10/4 기록을 한 주씩 넘기며 진단 → 미션 → Replay를 연습해요.")

if len(mine) and st.sidebar.button("미션 기록 처음부터 다시"):
    store.save_missions(missions[missions["student_id"] != student_id])
    store.save_coaching(coaching[coaching["student_id"] != student_id])
    st.session_state.get("mission_draft", {}).clear()
    st.rerun()

if len(mine) > 1:
    with st.expander("지난 주 기록"):
        for _, row in mine.iloc[:-1].iloc[::-1].iterrows():
            show_replay(row, with_title=False)

if latest is not None and latest["replay_comment"] == "":
    stage = "running"
else:
    diag_week = weeks[0] if latest is None else latest["week_start"]
    mission_week = replay.next_week(diag_week)
    stage = "plan" if mission_week in weeks else "end"

if latest is not None and stage != "running":
    show_replay(latest)

if stage == "end":
    st.success("데모 기록의 마지막 주까지 왔어요. 아래에서 처음부터 다시 해 볼 수 있어요.")

elif stage == "running":
    week = latest["week_start"]
    ui.section(f"{label(week)} 진단")
    show_diagnosis(latest["good"].split("|"), latest["practice"].split("|"), latest["summary"],
                   key="running")
    ui.section(f"{label(week)} 미션 진행 중")
    with ui.card("running"):
        show_missions(week_missions(week))
        ui.muted(f"고른 방법: 매주 {won(int(latest['plan_weekly_save']))} 모으기 · "
                 f"{goal['item']} 목표 달성 예상 {when(latest['goal_date_before'])}")

    ui.muted(f"데모에서는 이미 있는 {label(week)} 기록으로 결과를 계산해요.")
    if st.button(f"{label(week)} 주말 Replay", type="primary", width="stretch"):
        metrics = metrics_of(week)
        graded = replay.grade_missions(week_missions(week), metrics)
        remaining = goal["amount"] - metrics["save_balance"]
        after = simulate.finish_date(
            replay.next_week(week),
            simulate.weeks_needed(remaining, int(latest["plan_weekly_save"])))
        done_count = sum(g["done"] for g in graded)
        texts = dict(zip(missions["mission_id"], missions["text"]))
        payload = {
            "student": student_info(),
            "missions": [{"text": texts[g["mission_id"]], "result": g["result"],
                          "done": g["done"]} for g in graded],
            "goal_date": {"item": goal["item"], "before": when(latest["goal_date_before"]),
                          "after": when(after)},
        }
        default = {"comment": f"미션 {len(graded)}개 중 {done_count}개를 해냈어요. "
                              "다음 주 미션은 이번 결과에 맞춰 다시 잡아 볼게요."}
        done_flags = "".join("T" if g["done"] else "F" for g in graded)
        comment = ui.ask_ai("replay_comment", payload, student_id, demo_key=f"{week}|{done_flags}",
                            default=default)["comment"]

        for g in graded:
            missions.loc[missions["mission_id"] == g["mission_id"], ["result_value", "done"]] = [
                str(g["result_value"]), "TRUE" if g["done"] else "FALSE"]
        coaching.loc[mine.index[-1], ["replay_comment", "goal_date_after"]] = [comment, after or ""]
        store.save_missions(missions)
        store.save_coaching(coaching)
        st.rerun()

else:  # plan: diag_week 기록으로 진단 → mission_week 미션
    draft = st.session_state.setdefault("mission_draft", {}).setdefault(
        (student_id, diag_week), {})
    diag_metrics = metrics_of(diag_week)

    prev_rows = week_missions(latest["week_start"]) if latest is not None else missions.iloc[0:0]
    prev_behavior = prev_rows[prev_rows["skill"] != mission.SAVING]
    prev_saving = prev_rows[prev_rows["skill"] == mission.SAVING]
    if len(prev_behavior):
        last = prev_behavior.iloc[-1]
        level = mission.next_level(last["level"], last["done"] == "TRUE")
        level_note = ("지난주 미션을 해내서 한 단계 더 도전해요." if last["done"] == "TRUE"
                      else "지난주보다 조금 쉽게 잡았어요.")
    else:
        level, level_note = mission.START_LEVEL, ""
    last_saving_done = (prev_saving.iloc[-1]["done"] == "TRUE") if len(prev_saving) else None

    ui.section(f"1. {label(diag_week)} 진단")
    cands = mission.candidates(diag_metrics)
    facts = mission.fact_sentences(diag_metrics)
    if "diagnosis" not in draft:
        if st.button(f"{label(diag_week)} 기록으로 진단 받기", type="primary", width="stretch"):
            def check(result):
                if not (set(result["good"]) <= set(cands["good"])
                        and set(result["practice"]) <= set(cands["practice"])):
                    raise ValueError("후보에 없는 키워드")

            payload = {"student": student_info(), "facts": facts,
                       "good_candidates": cands["good"], "practice_candidates": cands["practice"]}
            default = {"good": cands["good"][:2], "practice": cands["practice"][:2],
                       "summary": " ".join(facts)}
            draft["diagnosis"] = ui.ask_ai("diagnose_week", payload, student_id,
                                           demo_key=diag_week, default=default, check=check)
            st.rerun()
        finish()
    diagnosis = draft["diagnosis"]
    show_diagnosis(diagnosis["good"], diagnosis["practice"], diagnosis["summary"], key="plan")

    ui.section(f"2. {label(mission_week)} 미션")
    skill = mission.skill_of(diagnosis["practice"][0])
    if skill == mission.SAVING:
        ui.card("saving-only").write("이번 주에는 모으기 미션에 집중해요. 아래에서 모으는 방법을 골라 주세요.")
    else:
        if "behavior" not in draft:
            if st.button("미션 받기", type="primary", width="stretch"):
                goal_spec = mission.behavior_goal(skill, level, diag_metrics)
                draft["behavior"] = {**goal_spec,
                                     "text": mission_text(goal_spec, diagnosis["summary"])}
                st.rerun()
            finish()
        with ui.card("behavior"):
            st.success(draft["behavior"]["text"])
            ui.muted(f"난이도: {draft['behavior']['level']}" + (f" · {level_note}" if level_note else ""))

    ui.section(f"3. {goal['item']}까지 어떻게 모을까요?")
    past_nets = [metrics_of(w)["save_net"] for w in weeks if w <= diag_week]
    options = simulate.alternatives(student, diag_metrics["save_balance"], past_nets, mission_week)
    recommended = mission.recommended_plan(options, last_saving_done)
    with ui.card("plan"):
        st.write(f"목표 {won(goal['amount'])} 중 {won(diag_metrics['save_balance'])} 모았어요.")
        st.dataframe(pd.DataFrame({
            "방법": [f"{o['key']}. {o['label']}" + (" (추천)" if o["key"] == recommended else "")
                   for o in options],
            "매주": [won(o["weekly"]) for o in options],
            "남은 기간": ["-" if o["weeks"] is None else f"{o['weeks']}주" for o in options],
            "예상 시기": [when(o["finish"]) for o in options],
        }), hide_index=True, width="stretch")

        usable = {o["key"]: o for o in options if o["weekly"] > 0}
        if not usable:
            st.warning("모으기 비율이 0%예요. 용돈봉투 화면에서 모으기 비율을 먼저 정해 주세요.")
            finish()
        choice_labels = {f"{k}. {o['label']} (매주 {won(o['weekly'])})": k for k, o in usable.items()}
        keys = list(choice_labels.values())
        choice = choice_labels[st.radio(
            "이번 주에 해 볼 방법", list(choice_labels),
            index=keys.index(recommended) if recommended in keys else 0)]
    if st.button("이 계획으로 이번 주 시작", type="primary", width="stretch"):
        chosen = usable[choice]
        saving_spec = mission.saving_goal(chosen["weekly"])
        saving_spec["text"] = mission_text(saving_spec, diagnosis["summary"])
        specs = ([draft["behavior"]] if "behavior" in draft else []) + [saving_spec]
        ids = store.next_mission_ids(missions, len(specs))
        new_missions = pd.DataFrame([{
            "mission_id": mission_id, "student_id": student_id, "week_start": mission_week,
            "skill": spec["skill"], "text": spec["text"], "target_metric": spec["target_metric"],
            "target_value": str(spec["target_value"]), "result_value": "", "done": "",
            "level": spec["level"]} for mission_id, spec in zip(ids, specs)])
        new_coaching = pd.DataFrame([{
            "student_id": student_id, "week_start": mission_week, "diag_week_start": diag_week,
            "good": "|".join(diagnosis["good"]), "practice": "|".join(diagnosis["practice"]),
            "summary": diagnosis["summary"], "plan": choice,
            "plan_weekly_save": str(chosen["weekly"]), "goal_date_before": chosen["finish"] or "",
            "replay_comment": "", "goal_date_after": ""}])
        store.save_missions(pd.concat([missions, new_missions], ignore_index=True))
        store.save_coaching(pd.concat([coaching, new_coaching], ignore_index=True))
        st.session_state["mission_draft"].pop((student_id, diag_week), None)
        st.rerun()

show_growth()
