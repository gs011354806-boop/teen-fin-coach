"""BC카드 소비 통계 기준과, 그 기준으로 만든 학생 지출 데이터 검증."""

import pandas as pd
import pytest

from engine import consumption, envelope, store

BASE = consumption.baseline()


def test_foreigners_are_excluded_and_categories_complete():
    assert set(BASE) == {1, 2}  # 3(외국인) 없음
    for by_category in BASE.values():
        assert list(by_category) == consumption.BC_CATEGORIES
        assert sum(v["count_share"] for v in by_category.values()) == pytest.approx(1.0)


def test_baseline_matches_raw_counts():
    """원본에서 직접 다시 계산해도 같은 값 (예: 여성 편의점 건수 비율)."""
    raw = consumption.load_reference()
    women = raw[raw["GENDER_CD"] == 2]
    names = women["TP_BUZ_NM"].str.replace(" ", "")
    convenience = women[names == "편의점"]["cnt"].sum() / women["cnt"].sum()
    assert BASE[2]["CONVENIENCE"]["count_share"] == pytest.approx(convenience)
    cafe = women[names.isin(["서양음식", "제과점"])]
    assert BASE[2]["CAFE_DESSERT"]["avg_amount"] == pytest.approx(cafe["amt"].sum() / cafe["cnt"].sum())


def test_unknown_business_type_is_an_error():
    raw = pd.DataFrame([{"GENDER_CD": 1, "TP_BUZ_NM": "주유소", "amt": 1, "cnt": 1}])
    with pytest.raises(ValueError):
        consumption.baseline(raw)


def test_tilt_and_allocate():
    shares = {"A": 0.5, "B": 0.3, "C": 0.2}
    tilted = consumption.tilt(shares, "A", 0.8)
    assert tilted["A"] == 0.8 and tilted["B"] == pytest.approx(0.12) and sum(tilted.values()) == pytest.approx(1)
    assert consumption.allocate_counts({"A": 0.467, "B": 0.295, "C": 0.182, "D": 0.056}, 6) == {
        "A": 3, "B": 2, "C": 1, "D": 0}


# --- 실제 학생 지출 데이터 ---

STUDENTS = {s["student_id"]: s for s in store.load_students()}
ALLOWANCE = store.load_allowance()


def bc_spending(student_id):
    spent = envelope.spending(ALLOWANCE, student_id)
    return spent[spent["category"].isin(consumption.BC_CATEGORIES)]


@pytest.mark.parametrize("student_id", ["S01", "S02", "S03"])
def test_average_amount_per_category_follows_bc(student_id):
    gender = STUDENTS[student_id]["gender"]
    spent = bc_spending(student_id)
    for category, rows in spent.groupby("category"):
        assert -rows["amount"].mean() == pytest.approx(BASE[gender][category]["avg_amount"], rel=0.10)


@pytest.mark.parametrize("student_id", ["S01", "S03"])
def test_baseline_students_follow_gender_shares(student_id):
    """적은 건수라 반올림 오차가 있다: 건수 비율이 BC 기준에서 ±10%p 안."""
    gender = STUDENTS[student_id]["gender"]
    spent = bc_spending(student_id)
    for category in consumption.BC_CATEGORIES:
        share = (spent["category"] == category).mean()
        assert share == pytest.approx(BASE[gender][category]["count_share"], abs=0.10)


def test_saving_failure_student_uses_convenience_more_than_baseline():
    spent = bc_spending("S02")
    share = (spent["category"] == "CONVENIENCE").mean()
    assert STUDENTS["S02"]["gender"] == 1
    assert share > BASE[1]["CONVENIENCE"]["count_share"] + 0.10


def test_old_category_codes_are_gone():
    assert not set(ALLOWANCE["category"]) & {"CAFE", "FOOD"}
