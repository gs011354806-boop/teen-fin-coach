"""부모 리포트 계산. LLM 호출 금지.

부모에게는 저축률 변화, 미션 수행률 변화, 이번 달 부모 미션만 보여 준다.
아이의 투자 일지 원문, 5번 학생 답 원문, 내부 점수(진단 판정값·난이도·포인트)는 여기서 다루지 않는다.
"""

from collections import Counter

from engine.replay import week_end

# 아이의 연습 거리 → 부모 미션 (목록에서만 고른다. AI는 말투만 다듬는다)
PARENT_MISSIONS = {
    "한 종목 쏠림": "이번 달에 아이와 '바구니 하나에 달걀을 다 담으면 어떻게 될까?'를 주제로 10분 이야기해 보세요. "
               "정답을 알려 주기보다 아이 생각을 먼저 들어 주세요.",
    "근거 부족": "아이가 가상투자에서 무언가를 골랐다면 '왜 그걸 골랐어?'라고 한 번 물어봐 주세요. "
              "이유를 말로 해 보는 연습이 됩니다. 맞고 틀림은 평가하지 말아 주세요.",
    "FOMO": "이번 달에 '친구들이 다 산다고 할 때 나는 어떻게 할까?'를 아이와 함께 이야기해 보세요. "
            "부모님이 비슷한 경험을 했던 이야기를 들려주셔도 좋아요.",
    "과신": "아이가 '이건 무조건 오른다'고 말하면, '만약 틀린다면 어떤 이유일까?'를 함께 떠올려 보세요. "
          "아이 의견을 꺾기보다 다른 가능성도 같이 보는 연습이에요.",
    "모으기 봉투 꺼내 쓰기": "이번 달에 아이와 함께 저축 목표와 매주 모을 금액을 다시 정해 보세요. "
                    "꺼내 쓰고 싶을 때 하루 기다려 보는 약속을 함께 만들어 보세요.",
}
DEFAULT_PARENT_MISSION = ("이번 달에는 아이가 잘하고 있는 습관을 한 가지 골라 구체적으로 칭찬해 주세요. "
                          "결과보다 과정을 말해 주는 칭찬이 좋아요.")
# 같은 뜻의 키워드를 한 미션으로 모은다 (6번 진단 키워드, 5번 분류 결과)
FOCUS_ALIASES = {"근거 없는 매수": "근거 부족"}


def weekly_saving_rates(student_id, allowance, weeks):
    """주마다 저축률(%) = 그 주 모으기 봉투 순증가 / 그 주 용돈 입금. 입금이 없으면 None."""
    mine = allowance[allowance["student_id"] == student_id]
    rates = []
    for week in weeks:
        rows = mine[(mine["date"] >= week) & (mine["date"] <= week_end(week))]
        deposit = int(rows.loc[rows["memo"] == "용돈 입금", "amount"].sum())
        save_net = int(rows.loc[rows["envelope"] == "SAVE", "amount"].sum())
        rates.append({"week_start": week,
                      "rate": None if deposit == 0 else round(save_net / deposit * 100)})
    return rates


def weekly_mission_rates(student_id, missions, weeks):
    """주마다 미션 수행률(%) = 해낸 미션 / 결과가 나온 미션. 결과가 없으면 None."""
    mine = missions[(missions["student_id"] == student_id)
                    & missions["done"].isin(["TRUE", "FALSE"])]
    rates = []
    for week in weeks:
        rows = mine[mine["week_start"] == week]
        rate = None if len(rows) == 0 else round((rows["done"] == "TRUE").sum() / len(rows) * 100)
        rates.append({"week_start": week, "rate": rate, "count": len(rows)})
    return rates


def change(rates):
    """처음과 마지막 값 (값이 있는 주만). 값이 하나도 없으면 None."""
    values = [r for r in rates if r["rate"] is not None]
    if not values:
        return None
    first, last = values[0], values[-1]
    return {"first_week": first["week_start"], "first": first["rate"],
            "last_week": last["week_start"], "last": last["rate"],
            "diff": last["rate"] - first["rate"]}


def parent_focus(student_id, coaching, lessons):
    """이번 달 가장 자주 나온 연습 거리. 6번 진단의 '연습할 것'과 5번 분류 결과를 함께 센다.
    동점이면 더 최근에 나온 것. 아무것도 없으면 None."""
    seen = []  # 시간순
    rows = coaching[coaching["student_id"] == student_id].sort_values("week_start", kind="stable")
    for practice in rows["practice"]:
        seen += [p for p in practice.split("|") if p]
    lesson_rows = lessons[lessons["student_id"] == student_id].sort_values("date", kind="stable")
    seen += [e for e in lesson_rows["error_type"] if e and e != "해당 없음"]
    seen = [FOCUS_ALIASES.get(k, k) for k in seen if FOCUS_ALIASES.get(k, k) in PARENT_MISSIONS]
    if not seen:
        return None
    counts = Counter(seen)
    best = max(counts.values())
    return next(k for k in reversed(seen) if counts[k] == best)


def parent_mission(focus):
    return PARENT_MISSIONS.get(focus, DEFAULT_PARENT_MISSION)


def mission_payload(student, base_mission, saving_change, mission_change):
    """AI에 넘길 것: 이름·학년, 목록에서 고른 미션, 두 가지 변화 숫자뿐. 일지·답 원문은 넣지 않는다."""
    return {"child": {"name": student["name"], "grade": student["grade"]},
            "base_mission": base_mission,
            "saving_rate_change": saving_change, "mission_rate_change": mission_change}
