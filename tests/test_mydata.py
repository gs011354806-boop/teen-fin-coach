"""20번 마이데이터 연결 예시: 19세 제외, 목표 계산, AI 첫 인사 검사, 화면."""

import pytest

from conftest import open_app
from engine import mydata, store

PAGE = "pages/10_마이데이터_연결.py"


@pytest.fixture(scope="module")
def profiles():
    return mydata.load_profiles()


def test_adults_are_excluded_and_original_file_kept(profiles):
    import pandas as pd
    raw = pd.read_csv(mydata.PATH, encoding="utf-8-sig")
    assert len(raw) == 1000 and (raw["age"] == 19).sum() > 0  # 원본은 그대로
    assert len(profiles) == 783
    assert profiles["age"].max() <= mydata.MAX_AGE and not profiles["legal_adult"].any()


def test_every_weak_skill_has_a_start_with_existing_concept(profiles):
    concepts = store.load_concepts()
    assert set(profiles["weak_skill"]) == set(mydata.START)
    assert all(concept in concepts for _, concept, _ in mydata.START.values())


def profile(**kw):
    base = {"age": 15, "school_level": "중학교", "grade": 2, "weak_skill": "목표저축", "goal_item": "운동화",
            "goal_amount": 150000, "goal_months": 6, "monthly_allowance": 50000, "avg_monthly_spend": 30000}
    return {**base, **kw}


def test_goal_plan_on_track():
    p = profile(goal_amount=100000, goal_months=10)  # 한 달 10,000원 필요, 20,000원 남음
    plan = mydata.goal_plan(p)
    assert (plan["need"], plan["left"], plan["at_pace"], plan["on_track"]) == (10000, 20000, 5, True)
    assert mydata.facts(p, plan)[-1] == "지금 한 달에 남는 20,000원을 다 모으면 5개월이면 돼요."


def test_goal_plan_short_and_impossible():
    p = profile()  # 한 달 25,000원 필요, 20,000원 남음 → 5,000원 더
    plan = mydata.goal_plan(p)
    assert (plan["need"], plan["gap"], plan["at_pace"]) == (25000, 5000, 8)
    assert "한 달에 5,000원을 더 아끼면" in mydata.facts(p, plan)[-1]
    p = profile(goal_amount=400000, goal_months=3)  # 133,400원 필요 > 용돈 50,000원
    assert "목표 기간을 다시 정해 보는 게 좋아요" in mydata.facts(p, mydata.goal_plan(p))[-1]
    p = profile(avg_monthly_spend=50000)
    assert mydata.goal_plan(p)["at_pace"] is None


def test_consent_under_14():
    assert mydata.needs_consent(profile(age=13)) and not mydata.needs_consent(profile(age=14))
    assert mydata.consent_status(profile(age=13, guardian_consent=True)) == "done"
    assert mydata.consent_status(profile(age=13, guardian_consent=False)) == "needed"
    assert mydata.consent_status(profile(age=15, guardian_consent=False)) is None


def test_data_under_14_all_consented(profiles):
    young = profiles[profiles["age"] < mydata.CONSENT_AGE]
    assert len(young) and young["guardian_consent"].astype(bool).all()


def test_message_check_blocks_new_numbers_and_persona():
    facts = ["목표는 운동화 150,000원을 6개월 안에 모으는 거예요."]
    check = mydata.message_check(facts)
    check({"message": "운동화 150,000원을 6개월 안에 모으는 목표가 있네요."})
    with pytest.raises(ValueError):
        check({"message": "한 달에 30,000원씩 모아 봐요."})
    with pytest.raises(ValueError):
        check({"message": "충동소비형이라 조심해야 해요."})


def test_page_connects_then_shows_plan_without_calling_ai():
    at = open_app(PAGE)
    assert not at.exception, at.exception
    assert not at.metric  # 불러오기 전에는 정보가 없다
    next(b for b in at.button if "불러오기" in b.label).click()
    at = at.run()
    assert {"학년", "용돈", "월평균 지출", "목표"} <= {m.label for m in at.metric}
    assert any(b.label == "AI 코치에게 첫 인사 받기" for b in at.button)
    assert "수익률" not in " ".join(m.value for m in at.markdown)


def test_under_14_profile_shows_consent(profiles):
    at = open_app(PAGE)
    skill = next(s for s in mydata.SKILL_ORDER
                 if mydata.needs_consent(mydata.pick(profiles, s, 0)))
    at.selectbox(key="mydata_skill").set_value(skill)
    at = at.run()
    assert any("보호자 동의 완료" in m.value for m in at.success)  # 데이터의 14세 미만은 모두 동의 받음
