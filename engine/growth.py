"""17번 성장 회고: 처음 주와 최근 주의 행동을 비교한 사실 문장. LLM 호출 금지.

- 비교 기간: 데모 1주차 ~ 주말 Replay까지 끝낸 가장 최근 주 (미션 탭을 진행할수록 늘어난다).
- 수익률·점수는 넣지 않는다. 횟수·비중·금액 같은 행동 사실만.
- AI는 이 문장들을 읽고 이야기만 쓴다. 숫자는 facts에 있는 것만 쓸 수 있다 (numbers_check).
"""

import re

from engine import detect, replay

# 숫자를 단위와 함께 본다 ("1주차"의 1과 "1만 원"의 1은 다른 숫자)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%p|%|만\s*원|천\s*원|원|번|개|주차|주|만|천)?")


def reached_weeks(coaching, weeks, student_id):
    """1주차 + Replay까지 끝낸 주들 (시간순)."""
    mine = coaching[(coaching["student_id"] == student_id) & (coaching["replay_comment"] != "")]
    done = set(mine["week_start"])
    return [weeks[0]] + [w for w in weeks[1:] if w in done]


def short_label(week, weeks):
    return f"{weeks.index(week) + 1}주차"


def pattern_counts(detections, week):
    end = replay.week_end(week)
    in_week = [d for d in detections if week <= d["date"] <= end]
    return {p: sum(p in d["patterns"] for d in in_week) for p in detect.PATTERNS}


WEIGHT_SAME_PP = 5  # 가장 큰 종목 비중이 이만큼(%p) 안에서 움직이면 그대로로 본다


def changes(a, b, sa, sb):
    """항목별 변화 판단 (코드가 정한다). AI는 이 판단만 따른다.
    나아짐 / 잘 유지(변화 없고 지금도 기준을 지킴) / 더 연습(나빠졌거나, 그대로인데 아직 기준 밖)."""
    result = {"나아짐": [], "잘 유지": [], "더 연습": []}

    def put(name, better, worse, good_now):
        result["나아짐" if better else "더 연습" if worse or not good_now else "잘 유지"].append(name)

    if a["buy_count"] and b["buy_count"]:  # 매수가 없는 주와는 비교하지 않는다
        put("매수 근거 적기", b["no_reason_buy_pct"] < a["no_reason_buy_pct"],
            b["no_reason_buy_pct"] > a["no_reason_buy_pct"], b["no_reason_count"] == 0)
    wa, wb = a["max_weight_pct"], b["max_weight_pct"]
    low = wb < detect.CONCENTRATION_PCT
    if max(wa, wb) < detect.CONCENTRATION_PCT:
        put("나눠 담기", False, False, True)  # 둘 다 쏠림 기준 아래면 잘 유지한 것
    else:
        put("나눠 담기", wb <= wa - WEIGHT_SAME_PP, wb >= wa + WEIGHT_SAME_PP, low)
    if sa or sb:
        put("급등 따라 사지 않기", sb < sa, sb > sa, sb == 0)
    put("모으기", b["save_net"] > a["save_net"], b["save_net"] < a["save_net"], b["save_net"] > 0)
    return result


def behavior_facts(student, trades, allowance, prices, first, last, weeks, with_changes=False):
    """매수 근거·쏠림·급등 추격·모으기 비교 문장 (미션 기록과 상관없이 데이터만으로).
    with_changes=True면 (문장, 항목별 변화 판단)을 돌려준다."""
    a, b = (replay.week_metrics(student, trades, allowance, prices, w) for w in (first, last))
    detections = detect.detect(trades, prices, student)
    sa, sb = (pattern_counts(detections, w)[detect.SURGE] for w in (first, last))
    la, lb = short_label(first, weeks), short_label(last, weeks)

    def reason(m):
        if m["buy_count"] == 0:
            return "매수가 없었어요"
        return f"매수 {m['buy_count']}번 중 근거가 부족한 매수가 {m['no_reason_count']}번이었어요"

    facts = [f"{la}에는 {reason(a)}. {lb}에는 {reason(b)}.",
             f"주말 기준 가장 큰 종목 비중은 {la} {a['max_weight_pct']:.0f}%, {lb} {b['max_weight_pct']:.0f}%였어요."]
    if sa or sb:
        facts.append(f"급등한 날 따라 산 매수는 {la} {sa}번, {lb} {sb}번이었어요.")
    facts.append(f"모으기 봉투에 남긴 돈은 {la} {a['save_net']:,}원, {lb} {b['save_net']:,}원이었어요.")
    return (facts, changes(a, b, sa, sb)) if with_changes else facts


def activity_facts(student_id, missions, lessons, rules, reached):
    """미션 수행·실수 돌아보기·나만의 규칙 (학생이 앱에서 한 활동)."""
    facts = []
    graded = missions[(missions["student_id"] == student_id) & missions["week_start"].isin(reached)
                      & (missions["done"] != "")]
    if len(graded):
        facts.append(f"지금까지 미션 {len(graded)}개 중 {int((graded['done'] == 'TRUE').sum())}개를 해냈어요.")
    reviewed = lessons[lessons["student_id"] == student_id]["trade_id"].nunique()
    made = int((rules["student_id"] == student_id).sum())
    if reviewed:
        facts.append(f"실수에서 배우기로 매수 {reviewed}개를 돌아봤어요."
                     + (f" 나만의 규칙도 {made}개 정했어요." if made else ""))
    return facts


def review_payload(student, first, last, weeks, facts, trend, practice):
    return {"student": {"name": student["name"], "grade": student["grade"]},
            "period": f"{short_label(first, weeks)} ~ {short_label(last, weeks)}",
            "facts": facts, "changes": trend, "practice_now": practice}


def numbers_check(facts):
    """AI 문장에 facts에 없는 숫자가 있으면 ValueError (LLM이 숫자를 만들거나 계산하지 못하게)."""
    def numbers(text):
        return {"".join(n.split()) for n in NUMBER.findall(text)}

    allowed = numbers(" ".join(facts))

    def check(result):
        extra = sorted(numbers(result["story"] + " " + result["next"]) - allowed)
        if extra:
            raise ValueError(f"facts에 없는 숫자: {extra}")
    return check


def default_review(facts):
    return {"story": " ".join(facts[:2]), "next": "다음 주에도 지금 연습하는 것을 이어 가 봐요."}
