"""20번 마이데이터 연결 예시: 팀이 카드 소비 통계로 만든 가상 마이데이터 프로필로 코칭 시작점을 정한다. LLM 호출 금지.

- 원본: data/reference/virtual_accounts.csv (가상 1,000명). 청소년 서비스라 19세(성인)는 불러올 때 뺀다.
- 거래 내역은 없고 프로필만 있다. 그래서 '첫 주 연습할 것'과 '목표까지 계산'만 정한다.
- 금액·기간 계산은 여기서 하고, AI는 이 문장들로 첫 인사만 쓴다.
"""

import math
from pathlib import Path

import pandas as pd

PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "virtual_accounts.csv"
SOURCE = "카드 소비 통계를 바탕으로 팀이 만든 가상 마이데이터 (실제 개인 정보 아님)"
MAX_AGE = 18          # 19세(성인)는 청소년 서비스 대상이 아니라서 뺀다
CONSENT_AGE = 14      # 만 14세 미만은 보호자 동의가 있어야 연결 (guardian_consent = 동의 받음)

# 약한 역량 → (이번 주 연습할 것, 개념 카드, 첫 주 미션 문장). 문장은 코드가 고른다.
START = {
    "목표저축": ("모으기 봉투 지키기", "GOAL_SAVING",
             "이번 주에는 모으기 봉투에 넣은 돈을 꺼내 쓰지 않고 지켜 보세요."),
    "계획소비": ("사기 전에 필요·원함 따져 보기", "NEEDS_VS_WANTS",
             "이번 주에는 편의점이나 카페에서 사기 전에 필요한 건지 갖고 싶은 건지 한 번 따져 보세요."),
    "투자 위험관리": ("나눠 담기", "DIVERSIFICATION",
                "가상투자에서 한 종목에 몰아 담지 않고 두 종목 이상에 나눠 담아 보세요."),
    "금융지식": ("개념 하나씩 익히기", "COMPOUND_INTEREST",
             "이번 주에는 개념 카드 하나를 읽고 확인 문제를 풀어 보세요."),
}
SKILL_ORDER = list(START)


def load_profiles(path=None):
    """19세 이하만 남긴다 (legal_adult 또는 19세 이상은 뺀다). 원본 파일은 바꾸지 않는다."""
    df = pd.read_csv(path or PATH, encoding="utf-8-sig")
    teens = df[(df["age"] <= MAX_AGE) & (~df["legal_adult"].astype(bool))]
    return teens[teens["weak_skill"].isin(START)].reset_index(drop=True)


def pick(profiles, weak_skill, index):
    """약한 역량이 같은 프로필 중 index번째 (끝나면 처음부터 다시)."""
    group = profiles[profiles["weak_skill"] == weak_skill]
    return group.iloc[index % len(group)].to_dict()


def school_label(p):
    level = {"초등학교": "초", "중학교": "중", "고등학교": "고"}.get(p["school_level"], p["school_level"])
    return f"{level}{p['grade']}" if p["grade"] else level


def needs_consent(p):
    """만 14세 미만이면 보호자 동의가 있어야 연결할 수 있다."""
    return int(p["age"]) < CONSENT_AGE


def consent_status(p):
    """'done'(14세 미만, 보호자 동의 받음) / 'needed'(14세 미만, 아직) / None(14세 이상, 동의 필요 없음).
    guardian_consent = 보호자 동의를 '받았다'는 뜻 (팀 확인, 2026-11-13). 데이터에서는 14세 미만만 True."""
    if not needs_consent(p):
        return None
    consented = str(p.get("guardian_consent", "")).strip().lower() in ("true", "1")
    return "done" if consented else "needed"


def goal_plan(p):
    """목표까지: 매달 모아야 할 돈, 지금 남는 돈(용돈 - 월평균 지출), 지금 페이스로 걸리는 달 수."""
    goal, months = int(p["goal_amount"]), int(p["goal_months"])
    allowance, spend = int(p["monthly_allowance"]), int(p["avg_monthly_spend"])
    need = math.ceil(goal / months / 100) * 100          # 100원 단위로 올림
    left = max(0, allowance - spend)
    at_pace = None if left == 0 else math.ceil(goal / left)
    return {"goal": goal, "months": months, "need": need, "left": left, "at_pace": at_pace,
            "on_track": left >= need, "gap": max(0, need - left)}


def facts(p, plan):
    """화면과 AI에 함께 쓰는 사실 문장 (숫자는 여기서만 만든다)."""
    sentences = [f"한 달 용돈은 {int(p['monthly_allowance']):,}원이고, 한 달에 평균 {int(p['avg_monthly_spend']):,}원을 써요.",
                 f"목표는 {p['goal_item']} {plan['goal']:,}원을 {plan['months']}개월 안에 모으는 거예요.",
                 f"그러려면 한 달에 {plan['need']:,}원씩 모아야 해요."]
    if plan["at_pace"] is None:
        sentences.append("지금은 용돈을 거의 다 써서 따로 남는 돈이 없어요.")
    elif plan["on_track"]:
        sentences.append(f"지금 한 달에 남는 {plan['left']:,}원을 다 모으면 {plan['at_pace']}개월이면 돼요.")
    elif plan["need"] > int(p["monthly_allowance"]):  # 용돈을 하나도 안 써도 기간 안에는 못 모음
        sentences.append(f"지금 한 달에 남는 돈은 {plan['left']:,}원이라, 그대로면 {plan['at_pace']}개월이 걸려요. "
                         "한 달에 모아야 할 돈이 용돈보다 많아서, 목표 기간을 다시 정해 보는 게 좋아요.")
    else:
        sentences.append(f"지금 한 달에 남는 돈은 {plan['left']:,}원이라, 그대로면 {plan['at_pace']}개월이 걸려요. "
                         f"한 달에 {plan['gap']:,}원을 더 아끼면 목표 기간에 맞출 수 있어요.")
    return sentences


def payload(p, plan, sentences):
    practice, concept, mission = START[p["weak_skill"]]
    return {"student": {"grade": school_label(p)}, "facts": sentences,
            "practice_now": practice, "first_mission": mission, "on_track": plan["on_track"]}


def default_message(p):
    practice = START[p["weak_skill"]][0]
    return {"message": f"마이데이터를 연결해 줘서 고마워요. 이번 주에는 '{practice}'부터 함께 연습해 봐요."}


PERSONA_WORDS = ["충동소비형", "저축실패형", "몰빵투자형", "개념부족형", "계획형"]


def message_check(sentences):
    """AI 첫 인사 검사: facts에 없는 숫자, 성향 이름으로 부르기를 막는다 (실패면 ValueError → 재시도)."""
    from engine.growth import numbers_check

    numbers = numbers_check(sentences)

    def check(result):
        numbers({"story": result["message"], "next": ""})
        found = [w for w in PERSONA_WORDS if w in result["message"]]
        if found:
            raise ValueError(f"성향 이름 사용: {found}")
    return check
