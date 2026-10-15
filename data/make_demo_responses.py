"""시연 모드용 저장 응답을 만든다 (민지 시나리오, 5번·6번). 실제 Gemini를 부른다.

실행: python data/make_demo_responses.py
결과: data/students/demo_responses.json

- 5번: 민지의 실수 매수마다 AI 질문, 시연용 예시 답에 대한 분류·개념 설명
- 6번: 화면과 같은 규칙으로 1~3주차를 진행한 기본 경로(추천 저축 대안 선택)의 진단·미션 문장·Replay 해석
- AI 응답과 똑같은 규칙(존댓말·금지 표현·목표 숫자·후보 키워드) 검사를 통과한 것만 저장한다.
- 숫자는 모두 engine/이 계산한다. AI는 문장만 쓴다.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import MODEL_NAME  # noqa: E402
from engine import detect, mission, replay, simulate, store  # noqa: E402
from llm import client as llm  # noqa: E402

STUDENT_ID = "S01"
# 시연 때 학생 답 칸에 미리 채워 둘 예시 답 (매수별)
ANSWERS = {
    "T0002": "계속 오를 것 같아서 샀어요. 다른 이유는 딱히 없었어요.",
    "T0005": "그냥 사고 싶어서 더 샀어요.",
    "T0009": "하루 만에 엄청 올라서 지금 안 사면 놓칠 것 같았어요.",
    "T0010": "친구가 샀다고 해서 저도 더 샀어요.",
    "T0014": "삼성전자는 큰 회사라서 계속 오를 것 같았어요. 다른 건 잘 몰라서 그냥 샀어요.",
}


CALL_GAP_SECONDS = 5      # 무료 한도(분당 요청 수)에 걸리지 않게 호출 사이에 쉰다
QUOTA_WAIT_SECONDS = 65   # 그래도 429가 나면 1분 기다렸다가 이어 간다 (앱이 아닌 한 번 쓰는 도구라서 허용)


def ask(name, payload, check=None):
    """규칙을 통과한 응답만 돌려준다. 세 번 다 실패하면 None."""
    for attempt in range(3):
        time.sleep(CALL_GAP_SECONDS)
        try:
            return llm.ask(name, payload, check=check, raise_on_fail=True)
        except llm.QuotaExceededError:
            print(f"  {name}: 분당 한도 초과, {QUOTA_WAIT_SECONDS}초 기다림")
            time.sleep(QUOTA_WAIT_SECONDS)
        except llm.LLMError as e:
            print(f"  {name} 실패({attempt + 1}/3): {e}")
    return None


def when(finish):
    return "지금 기록으로는 닿기 어려워요" if not finish else f"{finish[:4]}년 {int(finish[5:7])}월쯤"


def lesson_responses(student, names, trades, prices, responses, answers):
    detections = detect.detect(trades, prices, student)
    concepts = store.load_concepts()
    for moment in detect.mistakes(detections):
        trade_id = moment["trade_id"]
        if trade_id not in ANSWERS:
            continue
        past = detect.past_same_pattern(detections, trade_id)
        question = ask("mistake_question", detect.question_payload(student, moment, past, names))
        if not question:
            continue
        responses["mistake_question"][trade_id] = question
        answer = ANSWERS[trade_id]
        classified = ask("classify_mistake",
                         detect.classify_payload(moment, question["question"], answer))
        if not classified:
            continue
        answers[trade_id] = answer
        responses["classify_mistake"][trade_id] = classified
        concept = concepts[detect.pick_concept(classified["error_type"], moment["patterns"])]
        explained = ask("explain_concept", detect.explain_payload(
            student, moment, classified["error_type"], answer, concept))
        if explained:
            responses["explain_concept"][f"{trade_id}|{classified['error_type']}"] = explained
        print(f"5번 {trade_id}: {classified['error_type']}")


def mission_text(student, goal_spec, summary, responses):
    def check(result):
        missing = [w for w in goal_spec["must_include"] if w not in result["text"]]
        if missing:
            raise ValueError(f"목표 숫자 빠짐: {missing}")

    payload = {"student": {"name": student["name"], "grade": student["grade"]},
               "skill": goal_spec["skill"], "level": goal_spec["level"],
               "goal": {"phrase": goal_spec["phrase"], "must_include": goal_spec["must_include"]},
               "diagnosis_summary": summary}
    result = ask("weekly_mission", payload, check)
    text = result["text"] if result else f"{goal_spec['phrase']}에 도전해 보세요."
    if result:
        responses["weekly_mission"][goal_spec["phrase"]] = result
    return text


def mission_responses(student, trades, allowance, prices, responses):
    """pages/4_이번_주_미션.py와 같은 규칙으로 1~3주차 기본 경로를 진행한다."""
    weeks = replay.week_starts(allowance)
    info = {"name": student["name"], "grade": student["grade"]}
    goal = student["saving_goal"]
    level, last_saving_done = mission.START_LEVEL, None

    def metrics_of(week):
        return replay.week_metrics(student, trades, allowance, prices, week)

    for diag_week, mission_week in zip(weeks, weeks[1:]):
        metrics = metrics_of(diag_week)
        cands = mission.candidates(metrics)
        facts = mission.fact_sentences(metrics)

        def check(result, cands=cands):
            if not (set(result["good"]) <= set(cands["good"])
                    and set(result["practice"]) <= set(cands["practice"])):
                raise ValueError("후보에 없는 키워드")

        diagnosis = ask("diagnose_week", {"student": info, "facts": facts,
                                          "good_candidates": cands["good"],
                                          "practice_candidates": cands["practice"]}, check)
        if not diagnosis:
            print(f"6번 {diag_week}: 진단 실패, 여기서 멈춤")
            return
        responses["diagnose_week"][diag_week] = diagnosis

        specs = []
        skill = mission.skill_of(diagnosis["practice"][0])
        if skill != mission.SAVING:
            behavior = mission.behavior_goal(skill, level, metrics)
            behavior["text"] = mission_text(student, behavior, diagnosis["summary"], responses)
            specs.append(behavior)

        past_nets = [metrics_of(w)["save_net"] for w in weeks if w <= diag_week]
        options = simulate.alternatives(student, metrics["save_balance"], past_nets, mission_week)
        chosen = next(o for o in options
                      if o["key"] == mission.recommended_plan(options, last_saving_done))
        saving = mission.saving_goal(chosen["weekly"])
        saving["text"] = mission_text(student, saving, diagnosis["summary"], responses)
        specs.append(saving)

        result_metrics = metrics_of(mission_week)
        done = [replay.is_done(s["target_metric"], s["target_value"],
                               replay.mission_result(s["target_metric"], result_metrics))
                for s in specs]
        after = simulate.finish_date(
            replay.next_week(mission_week),
            simulate.weeks_needed(goal["amount"] - result_metrics["save_balance"], chosen["weekly"]))
        payload = {
            "student": info,
            "missions": [{"text": s["text"], "done": d,
                          "result": replay.result_sentence(s["target_metric"], result_metrics)}
                         for s, d in zip(specs, done)],
            "goal_date": {"item": goal["item"], "before": when(chosen["finish"]),
                          "after": when(after)},
        }
        flags = "".join("T" if d else "F" for d in done)
        comment = ask("replay_comment", payload)
        if comment:
            responses["replay_comment"][f"{mission_week}|{flags}"] = comment
        print(f"6번 {diag_week} 진단 → {mission_week} 미션 {len(specs)}개, 결과 {flags}")

        behavior_done = [d for s, d in zip(specs, done) if s["skill"] != mission.SAVING]
        level = (mission.next_level(level, behavior_done[0]) if behavior_done
                 else mission.START_LEVEL)
        last_saving_done = done[-1]


def main():
    students = {s["student_id"]: s for s in store.load_students()}
    student = students[STUDENT_ID]
    trades, allowance, prices = store.load_trades(), store.load_allowance(), store.load_prices()
    responses = {name: {} for name in ["mistake_question", "classify_mistake", "explain_concept",
                                       "diagnose_week", "weekly_mission", "replay_comment"]}
    answers = {}
    lesson_responses(student, store.load_ticker_names(), trades, prices, responses, answers)
    mission_responses(student, trades, allowance, prices, responses)
    data = {"model": MODEL_NAME, "students": {STUDENT_ID: {"answers": answers,
                                                           "responses": responses}}}
    store.DEMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    print(f"저장: {store.DEMO_PATH} ({sum(len(v) for v in responses.values())}개 응답)")


if __name__ == "__main__":
    main()
