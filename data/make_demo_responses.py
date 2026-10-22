"""시연 모드용 저장 응답을 만든다 (민지 시나리오, 5번·6번). 실제 Gemini를 부른다.

실행: python data/make_demo_responses.py              (전부 새로 만듦, 손으로 고친 응답도 덮어씀)
      python data/make_demo_responses.py --only precheck  (15번 응답만 기존 파일에 추가·교체)
      python data/make_demo_responses.py --only followup  (16번 꼬리 질문만 기존 파일에 추가·교체)
      python data/make_demo_responses.py --only growth    (17번 성장 회고만 기존 파일에 추가·교체)
      python data/make_demo_responses.py --only concept   (18번 예시 질문 답만 기존 파일에 추가·교체, 학생 3명)
결과: data/students/demo_responses.json

- 5번: 민지의 실수 매수마다 AI 질문, 시연용 예시 답에 대한 분류·개념 설명
- 6번: 화면과 같은 규칙으로 1~3주차를 진행한 기본 경로(추천 저축 대안 선택)의 진단·미션 문장·Replay 해석
- AI 응답과 똑같은 규칙(존댓말·금지 표현·목표 숫자·후보 키워드) 검사를 통과한 것만 저장한다.
- 15번: 학생 3명 × 패턴 조합 7개의 주문 전 질문. 수량마다 숫자가 달라지므로 숫자·종목명 없는 질문만 저장한다
  (사실 숫자는 화면 카드가 코드로 따로 보여 준다).
- 숫자는 모두 engine/이 계산한다. AI는 문장만 쓴다.
"""

import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import MODEL_NAME  # noqa: E402
from engine import concept_qa, detect, growth, mission, replay, simulate, store  # noqa: E402
from llm import client as llm  # noqa: E402

STUDENT_ID = "S01"
# 16번: 꼬리 질문에 미리 채워 둘 예시 답 (매수별, 위 ANSWERS와 이어지는 말)
FOLLOWUP_ANSWERS = {
    "T0002": "회사 소식이나 다른 종목은 찾아보지 않았어요. 하나만 확인했다면 왜 오르는지였을 것 같아요.",
    "T0005": "이미 많이 갖고 있다는 걸 생각 못 했어요. 비중을 먼저 봤으면 좋았을 것 같아요.",
    "T0009": "왜 올랐는지는 몰랐어요. 하루 기다려 보고 이유를 찾아봤으면 좋았을 것 같아요.",
    "T0010": "친구가 왜 샀는지는 안 물어봤어요. 제 이유를 따로 적어 봤어야 했어요.",
    "T0014": "회사 크기만 봤어요. 다음엔 한 종목에 얼마나 담는지도 먼저 볼래요.",
}

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


# 숫자 없는 사실 문장 (저장 질문이 어떤 수량에도 맞도록)
PRECHECK_FACTS = {detect.SURGE: "오늘 가격이 전 거래일보다 많이 올라 있어요.",
                  detect.CONCENTRATION: "이번에 사면 이 종목 비중이 총자산의 절반을 훌쩍 넘어요.",
                  detect.NO_REASON: "투자 일지가 비어 있어요."}


def precheck_responses(student, names):
    def check(result):
        q = result["question"]
        if any(c.isdigit() for c in q) or any(n in q for n in names.values()):
            raise ValueError("저장 질문에 숫자나 종목명이 있음")

    saved = {}
    combos = [c for r in (1, 2, 3) for c in itertools.combinations(detect.PATTERNS, r)]
    for combo in combos:
        payload = {"student": {"name": student["name"], "grade": student["grade"]},
                   "trade": {"stock": "이 종목", "journal": ""}, "patterns": list(combo),
                   "facts": [PRECHECK_FACTS[p] for p in combo], "past_same_pattern": []}
        result = ask("precheck_question", payload, check)
        if result:
            saved[detect.precheck_demo_key(combo)] = result
        print(f"15번 {student['student_id']} {detect.precheck_demo_key(combo)}: {'저장' if result else '실패'}")
    return saved


def add_followup():
    """기존 저장 응답은 그대로 두고 16번 꼬리 질문과 예시 답만 넣는다 (민지)."""
    data = store.load_demo()
    entry = data["students"][STUDENT_ID]
    student = {s["student_id"]: s for s in store.load_students()}[STUDENT_ID]
    names, trades, prices = store.load_ticker_names(), store.load_trades(), store.load_prices()
    by_id = {d["trade_id"]: d for d in detect.detect(trades, prices, student)}
    saved = {}
    for trade_id, answer in entry["answers"].items():
        question = entry["responses"]["mistake_question"].get(trade_id)
        if not question or trade_id not in FOLLOWUP_ANSWERS:
            continue
        result = ask("followup_question",
                     detect.followup_payload(student, by_id[trade_id], question["question"], answer, names))
        if result:
            saved[trade_id] = result
        print(f"16번 {trade_id}: {result['question'] if result else '실패'}")
    entry["responses"]["followup_question"] = saved
    entry["followup_answers"] = {t: FOLLOWUP_ANSWERS[t] for t in saved}
    store.DEMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {store.DEMO_PATH}")


def add_growth():
    """17번 성장 회고 (민지, 1주차와 2~4주차 비교). 미션 기록은 시연마다 달라서 행동 사실만으로 만든다.
    화면의 facts에는 미션 문장이 더 붙지만, 저장 문장의 숫자는 모두 그 안에 있어 숫자 검사를 통과한다."""
    data = store.load_demo()
    entry = data["students"][STUDENT_ID]
    student = {s["student_id"]: s for s in store.load_students()}[STUDENT_ID]
    trades, allowance, prices = store.load_trades(), store.load_allowance(), store.load_prices()
    weeks = replay.week_starts(allowance)
    saved = {}
    for last in weeks[1:]:
        facts, trend = growth.behavior_facts(student, trades, allowance, prices, weeks[0], last, weeks,
                                             with_changes=True)
        result = ask("growth_review", growth.review_payload(student, weeks[0], last, weeks, facts, trend, []),
                     growth.numbers_check(facts))
        if result:
            saved[last] = result
        print(f"17번 {last}: {result if result else '실패'}")
    entry["responses"]["growth_review"] = saved
    store.DEMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {store.DEMO_PATH}")


def add_concept():
    """18번 예시 질문 3개의 답. 학생과 상관없는 답이라 한 번 만들어 3명 모두에 넣는다."""
    data = store.load_demo()
    concepts = store.load_concepts()
    saved = {}
    for question in concept_qa.EXAMPLES:
        result = ask("concept_answer", concept_qa.payload(question, concepts), concept_qa.answer_check(concepts))
        if result:
            saved[question] = result
        print(f"18번 {question}: {result if result else '실패'}")
    for student in store.load_students():
        entry = data["students"].setdefault(student["student_id"], {"answers": {}, "responses": {}})
        entry["responses"]["concept_answer"] = dict(saved)
    store.DEMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {store.DEMO_PATH}")


def add_precheck():
    """기존 저장 응답은 그대로 두고 15번 응답만 넣는다."""
    data = store.load_demo()
    names = store.load_ticker_names()
    for student in store.load_students():
        entry = data["students"].setdefault(student["student_id"], {"answers": {}, "responses": {}})
        entry["responses"]["precheck_question"] = precheck_responses(student, names)
    store.DEMO_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {store.DEMO_PATH}")


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
    if sys.argv[1:] == ["--only", "precheck"]:
        add_precheck()
    elif sys.argv[1:] == ["--only", "followup"]:
        add_followup()
    elif sys.argv[1:] == ["--only", "growth"]:
        add_growth()
    elif sys.argv[1:] == ["--only", "concept"]:
        add_concept()
    else:
        main()
