"""진단 후보와 미션 목표·난이도 규칙. LLM 호출 금지.

내부 판정값(need)은 순서를 정할 때만 쓰고 학생 화면에 보여 주지 않는다 (CLAUDE.md 규칙 5).
"""

import math

SAVING = "목표저축"
SPENDING = "원함 지출"  # 19번 지출 코칭
SKILLS = {
    "위험분산": {"metric": "max_weight_pct", "good": "나눠 담기", "practice": "한 종목 쏠림",
             "stretch": "나눠 담기 이어가기"},
    "근거 적기": {"metric": "no_reason_buy_pct", "good": "근거 적기", "practice": "근거 없는 매수",
              "stretch": "근거 더 자세히 적기"},
    SAVING: {"metric": "save_net", "good": "꾸준히 모으기", "practice": "모으기 봉투 꺼내 쓰기",
             "stretch": "모으기 조금 더 늘리기"},
    SPENDING: {"metric": "impulse_spend", "good": "필요한 곳에 쓰기", "practice": "편의점·카페 지출",
               "stretch": "사기 전에 필요·원함 따져 보기"},
}
# 학생 화면에 보이는 '이번 주 연습할 것' 이름. 내부 키워드(기록·부모 미션·개념 연결에 씀)는 그대로 두고
# 화면에서만 '하지 말 것'이 아니라 '해 볼 것'으로 보여 준다.
PRACTICE_LABEL = {"한 종목 쏠림": "나눠 담기", "근거 없는 매수": "근거 적고 사기",
                  "모으기 봉투 꺼내 쓰기": "모으기 봉투 지키기", "편의점·카페 지출": "필요·원함 따져 보고 쓰기"}


def practice_label(keyword):
    return PRACTICE_LABEL.get(keyword, keyword)


FALLBACK_GOOD = "매주 돌아보기"  # 잘하는 것이 하나도 없을 때: 지금 Replay를 하고 있다는 사실

LEVELS = ["쉬움", "보통", "어려움"]
START_LEVEL = "보통"
WEIGHT_STEP = {"쉬움": 5, "보통": 10, "어려움": 20}
IMPULSE_CUT_PCT = {"쉬움": 10, "보통": 20, "어려움": 30}  # 지난주 편의점·카페 지출에서 줄일 비율
IMPULSE_FLOOR = 1000
MIN_SPEND_FOR_JUDGE = 10000  # 한 주 지출이 이보다 적으면 비중이 들쭉날쭉해서 지출은 판단하지 않는다
WEIGHT_FLOOR = 40
NO_REASON_TARGET = {"쉬움": 50, "보통": 25, "어려움": 0}
NO_REASON_PHRASE = {
    "쉬움": "이번 주 매수의 절반 이상에 이유를 10자 이상 적기",
    "보통": "이번 주 매수의 4분의 3 이상(예: 4번 사면 3번)에 이유를 10자 이상 적기",
    "어려움": "이번 주 모든 매수에 이유를 10자 이상 적기",
}


def _need(skill, metrics):
    """연습이 필요한 정도 (클수록 필요). 측정할 수 없으면 None. 0 이하 = 잘함, 1 이상 = 연습."""
    if skill == "위험분산":
        return (metrics["max_weight_pct"] - 40) / 20  # 40% 미만 잘함, 60% 이상 연습
    if skill == "근거 적기":
        pct = metrics["no_reason_buy_pct"]
        return None if pct is None else (pct - 30) / 20  # 30% 미만 잘함, 50% 이상 연습
    if skill == SPENDING:
        pct = metrics.get("impulse_share_pct")  # 지출이 적은 주(또는 예전 지표)는 판단하지 않는다
        if pct is None or metrics["spend_total"] < MIN_SPEND_FOR_JUDGE:
            return None
        return (pct - 40) / 30  # 40% 미만 잘함, 70% 이상 연습
    if metrics["save_deposit"] == 0:
        return None
    kept_pct = metrics["save_net"] / metrics["save_deposit"] * 100
    return -1.0 if kept_pct >= 100 else (100 - kept_pct) / 20  # 다 남기면 잘함, 80% 이하면 연습


def candidates(metrics):
    """{"good": [키워드], "practice": [키워드]} — LLM은 이 안에서만 고른다."""
    needs = {s: _need(s, metrics) for s in SKILLS}
    needs = {s: n for s, n in needs.items() if n is not None}
    good = [s for s, n in needs.items() if n < 0]
    practice = sorted((s for s, n in needs.items() if n >= 1), key=lambda s: -needs[s])
    practice_keywords = [SKILLS[s]["practice"] for s in practice]
    if not practice:
        # 뚜렷한 연습 거리가 없으면: 잘함이 아닌 것 중 가장 약한 것(연습 키워드),
        # 모두 잘하면 가장 여유가 적은 것을 "이어가기/늘리기"로 (없는 문제를 지어내지 않는다)
        middle = [s for s in needs if s not in good]
        if middle:
            weakest = max(middle, key=lambda s: needs[s])
            practice_keywords = [SKILLS[weakest]["practice"]]
        elif needs:
            weakest = max(needs, key=lambda s: needs[s])
            practice_keywords = [SKILLS[weakest]["stretch"]]
            good = [s for s in good if s != weakest]
    good_keywords = [SKILLS[s]["good"] for s in sorted(good, key=lambda s: needs[s])]
    return {"good": good_keywords or [FALLBACK_GOOD], "practice": practice_keywords}


# 진단 키워드 → 함께 보여 줄 개념 (content/concepts). "모으기 조금 더 늘리기"처럼 이미 잘하는
# 학생에게는 오래 둘수록 불어나는 복리를, 꺼내 쓰는 학생에게는 목표저축을 보여 준다.
CONCEPT_FOR_KEYWORD = {
    "한 종목 쏠림": "DIVERSIFICATION", "나눠 담기 이어가기": "DIVERSIFICATION",
    "근거 없는 매수": "INVESTMENT_JOURNAL", "근거 더 자세히 적기": "INVESTMENT_JOURNAL",
    "모으기 봉투 꺼내 쓰기": "GOAL_SAVING", "모으기 조금 더 늘리기": "COMPOUND_INTEREST",
    "편의점·카페 지출": "NEEDS_VS_WANTS", "사기 전에 필요·원함 따져 보기": "NEEDS_VS_WANTS",
}


def concept_for(keyword):
    return CONCEPT_FOR_KEYWORD.get(keyword)


def skill_of(keyword):
    return next(s for s, d in SKILLS.items()
                if keyword in (d["good"], d["practice"], d["stretch"]))


def fact_sentences(metrics):
    """진단에 쓸 사실 문장 (점수 없음)."""
    facts = []
    if metrics["buy_count"]:
        facts.append(f"매수 {metrics['buy_count']}번 중 근거가 10자 미만인 매수는 "
                     f"{metrics['no_reason_count']}번이었어요.")
    else:
        facts.append("이번 주에는 매수가 없었어요.")
    facts.append(f"주말 기준 가장 큰 종목 비중은 총자산의 {metrics['max_weight_pct']:.0f}%였어요.")
    facts.append(f"모으기 봉투에 {metrics['save_deposit']:,}원을 넣고 "
                 f"{metrics['save_withdraw']:,}원을 꺼냈어요.")
    if metrics.get("spend_total"):
        facts.append(f"쓰기 봉투에서 {metrics['spend_total']:,}원을 썼고, 그중 편의점·카페·디저트가 "
                     f"{metrics['impulse_count']}번, {metrics['impulse_spend']:,}원"
                     f"({metrics['impulse_share_pct']:.0f}%)이었어요.")
    return facts


def behavior_goal(skill, level, metrics):
    """위험분산·근거 적기·원함 지출 미션 목표. 목표 숫자는 여기서만 정한다."""
    if skill == SPENDING:
        cut = metrics["impulse_spend"] * (100 - IMPULSE_CUT_PCT[level]) / 100
        target = max(IMPULSE_FLOOR, 1000 * math.floor(cut / 1000))
        return {"skill": skill, "level": level, "target_metric": "impulse_spend",
                "target_value": float(target),
                "phrase": f"이번 주 편의점·카페·디저트 지출을 {target:,}원 이하로 줄이기",
                "must_include": [f"{target:,}원"]}
    if skill == "위험분산":
        target = max(WEIGHT_FLOOR,
                     5 * math.floor((metrics["max_weight_pct"] - WEIGHT_STEP[level]) / 5))
        return {"skill": skill, "level": level, "target_metric": "max_weight_pct",
                "target_value": float(target),
                "phrase": f"주말에 가장 큰 종목 비중을 총자산의 {target}% 이하로 맞추기",
                "must_include": [f"{target}%"]}
    return {"skill": skill, "level": level, "target_metric": "no_reason_buy_pct",
            "target_value": float(NO_REASON_TARGET[level]), "phrase": NO_REASON_PHRASE[level],
            "must_include": ["10자"]}


def saving_goal(weekly):
    return {"skill": SAVING, "level": "", "target_metric": "save_net",
            "target_value": float(weekly),
            "phrase": f"이번 주 모으기 봉투에 {weekly:,}원 이상 남기기",
            "must_include": [f"{weekly:,}원"]}


def next_level(level, done):
    """해내면 한 단계 어렵게, 못 하면 한 단계 쉽게."""
    i = LEVELS.index(level) + (1 if done else -1)
    return LEVELS[max(0, min(len(LEVELS) - 1, i))]


def recommended_plan(options, last_saving_done):
    """지난주 모으기 미션 결과로 추천 대안을 고른다. 처음이면 B, 해냈으면 더 큰 쪽, 못 했으면 작은 쪽."""
    usable = [o for o in options if o["weekly"] > 0]
    if not usable:
        return None
    by_amount = sorted(usable, key=lambda o: o["weekly"])
    if last_saving_done is None:
        return next((o["key"] for o in usable if o["key"] == "B"), by_amount[0]["key"])
    return (by_amount[-1] if last_saving_done else by_amount[0])["key"]
