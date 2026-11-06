"""목표 달성 시뮬레이션: 저축 대안 A/B/C별 예상 기간. LLM 호출 금지."""

import math
from datetime import date, timedelta

RATIO_STEP = 10  # 대안 C: 모으기 비율을 몇 %p 올릴지


def weeks_needed(remaining, weekly):
    """남은 금액을 매주 weekly씩 모을 때 걸리는 주 수. 모을 수 없으면 None."""
    if remaining <= 0:
        return 0
    if weekly <= 0:
        return None
    return math.ceil(remaining / weekly)


def finish_date(start_week, weeks):
    """start_week(월요일)부터 weeks주 뒤 그 주의 일요일. weeks가 None이면 None."""
    if weeks is None:
        return None
    if weeks == 0:
        return start_week
    return (date.fromisoformat(start_week) + timedelta(days=7 * weeks - 1)).isoformat()


def alternatives(student, save_balance, past_weekly_nets, start_week):
    """
    A: 지금처럼 (지난 주들 모으기 봉투 순증가의 평균)
    B: 모으기 봉투 꺼내지 않기 (용돈 × 현재 모으기 비율)
    C: 모으기 비율 10%p 올리기 (쓰기 비율이 남는 만큼만)
    A와 B가 같으면(이미 꺼내지 않고 모으는 중) B 한 줄로 합친다.
    """
    remaining = max(0, student["saving_goal"]["amount"] - save_balance)
    ratio = student["envelope_ratio"]
    weekly = student["weekly_allowance"]
    average = max(0, sum(past_weekly_nets) // len(past_weekly_nets)) if past_weekly_nets else 0
    raised = ratio["SAVE"] + min(RATIO_STEP, ratio["SPEND"])
    options = [
        ("A", "지금처럼 모으기", average),
        ("B", "모으기 봉투 꺼내지 않기", weekly * ratio["SAVE"] // 100),
        ("C", f"모으기 비율 {raised - ratio['SAVE']}%p 올리기", weekly * raised // 100),
    ]
    if options[0][2] == options[1][2]:  # 지금도 꺼내지 않고 모으는 중이면 A와 B가 같다 → 한 줄로
        options = [("B", "지금처럼 꺼내지 않고 모으기", options[1][2]), options[2]]
    results = []
    for key, label, amount in options:
        weeks = weeks_needed(remaining, amount)
        results.append({"key": key, "label": label, "weekly": amount, "remaining": remaining,
                        "weeks": weeks, "finish": finish_date(start_week, weeks)})
    return results
