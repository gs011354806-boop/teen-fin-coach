"""11번 효과 측정 대시보드 (교사·운영자용) 계산. LLM 호출 금지.

- 학생 전체의 주차별 행동 변화와 앱 활동을 센다. 수익률·이익·손실은 계산하지 않는다.
- 학생 화면이 아니라서 학생별 행동 횟수는 보여 줄 수 있다. 그래도 역량 점수는 만들지 않는다.
- 가상 학생 데모 데이터라 통계적 효과가 아니다 (화면에 함께 적는다).
"""

from engine import detect, portfolio, replay, unlock


def pct(part, whole):
    return None if whole == 0 else round(part / whole * 100)


def weekly_patterns(students, trades, prices, weeks, until=None):
    """주마다 전체 학생의 매수 수, 실수 패턴(하나라도)이 있는 매수 비율, 패턴별 매수 수.
    until: 이 날짜 전 매수만 센다 (기본 4주 = 코칭 전 기록만 주차별로 보려고)."""
    detections = [d for s in students for d in detect.detect(trades, prices, s)
                  if until is None or d["date"] < until]
    rows = []
    for week in weeks:
        in_week = [d for d in detections if week <= d["date"] <= replay.week_end(week)]
        row = {"week_start": week, "buys": len(in_week),
               "mistake_pct": pct(sum(bool(d["patterns"]) for d in in_week), len(in_week))}
        row.update({p: sum(p in d["patterns"] for d in in_week) for p in detect.PATTERNS})
        rows.append(row)
    return rows


def weekly_missions(missions, weeks):
    """주마다 전체 미션 달성률 (결과가 나온 미션 중 해낸 비율)."""
    graded = missions[missions["done"].isin(["TRUE", "FALSE"])]
    rows = []
    for week in weeks:
        mine = graded[graded["week_start"] == week]
        rows.append({"week_start": week, "graded": len(mine),
                     "done_pct": pct(int((mine["done"] == "TRUE").sum()), len(mine))})
    return rows


def weekly_money(students, trades, allowance, prices, weeks):
    """주마다 전체 저축률(모으기 순증가 ÷ 용돈 입금)과 원함 지출 비율(편의점·카페·디저트 ÷ 전체 지출)."""
    rows = []
    for week in weeks:
        end = replay.week_end(week)
        in_week = allowance[(allowance["date"] >= week) & (allowance["date"] <= end)]
        deposit = int(in_week.loc[in_week["memo"] == "용돈 입금", "amount"].sum())
        metrics = [replay.week_metrics(s, trades, allowance, prices, week) for s in students]
        rows.append({"week_start": week,
                     "save_pct": pct(sum(m["save_net"] for m in metrics), deposit),
                     "impulse_pct": pct(sum(m["impulse_spend"] for m in metrics),
                                        sum(m["spend_total"] for m in metrics))})
    return rows


def buy_summary(detections):
    return {"buys": len(detections),
            "mistake_pct": pct(sum(bool(d["patterns"]) for d in detections), len(detections)),
            "no_reason_pct": pct(sum(detect.NO_REASON in d["patterns"] for d in detections), len(detections))}


def before_after(students, trades, prices, today, app_detections=None):
    """코칭 전(기본 데이터, today 전) 매수와 앱에서 한 매수(today 이후)를 나눠 비교한다.
    데모에서 앱으로 하는 매수는 모두 '오늘'(마지막 시세일)로 기록되고, 기본 4주 기록은 그 전 날짜다.
    app_detections: 투자 탭에서 실제 시세로 한 매수의 감지 결과 (모두 '앱에서 한 매수'로 센다)."""
    detections = [d for s in students for d in detect.detect(trades, prices, s)]
    after = [d for d in detections if d["date"] >= today] + list(app_detections or [])
    return {"before": buy_summary([d for d in detections if d["date"] < today]),
            "after": buy_summary(after)}


def latest_value(rows, key):
    """값이 있는 마지막 주 (하나도 없으면 None). 비교할 주가 하나뿐일 때 보여 주려고."""
    values = [r for r in rows if r[key] is not None]
    return {"week": values[-1]["week_start"], "value": values[-1][key], "count": len(values)} if values else None


def first_last(rows, key):
    """값이 있는 처음 주와 마지막 주. 값이 둘 미만이면 None."""
    values = [r for r in rows if r[key] is not None]
    if len(values) < 2:
        return None
    return {"first_week": values[0]["week_start"], "first": values[0][key],
            "last_week": values[-1]["week_start"], "last": values[-1][key]}


def activity(lessons, rules, prechecks, questions, unlocks, students):
    """앱 안에서 학생들이 한 일 (기록 파일에서 센다)."""
    added = sum(bool(r.strip()) for r in prechecks["added_reason"])
    stages = [unlock.stage(unlocks, s["student_id"]) for s in students]
    return {
        "lessons": len(lessons), "lesson_students": lessons["student_id"].nunique(),
        "rules": len(rules),
        "prechecks": len(prechecks), "precheck_cancel": int((prechecks["decision"] == "CANCEL").sum()),
        "precheck_added_pct": pct(added, len(prechecks)),
        "questions": len(questions),
        "questions_none": int((questions["concept"] == "NONE").sum()),
        "questions_advice": int((questions["concept"] == "ADVICE").sum()),
        "stages": {n: stages.count(n) for n in unlock.STAGES},
    }


def missing_concepts(questions):
    """준비된 개념 카드가 없어 답하지 못한 질문 (콘텐츠 추가 후보). 같은 질문은 한 번만."""
    asked = questions[questions["concept"] == "NONE"]["question"]
    return list(dict.fromkeys(q for q in asked if q))


def per_student(students, trades, prices, lessons, rules, missions, unlocks):
    """학생별 행동 횟수 (교사용). 점수는 만들지 않는다."""
    rows = []
    for s in students:
        sid = s["student_id"]
        detections = detect.detect(trades, prices, s)
        rows.append({"name": s["name"], "stage": unlock.stage(unlocks, sid),
                     "buys": len(detections), "mistakes": len(detect.mistakes(detections)),
                     "lessons": int((lessons["student_id"] == sid).sum()),
                     "rules": int((rules["student_id"] == sid).sum()),
                     "missions_done": int(((missions["student_id"] == sid) & (missions["done"] == "TRUE")).sum())})
    return rows
