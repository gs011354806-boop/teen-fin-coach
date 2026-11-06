"""engine/envelope.py와 용돈 관련 store 함수 검증."""

import shutil

import pandas as pd
import pytest

from engine import envelope, store

ALLOWANCE = pd.DataFrame(
    [
        ("S01", "2026-09-07", "SPEND", 10000, "OTHER", "용돈 입금"),
        ("S01", "2026-09-07", "SAVE", 6000, "OTHER", "용돈 입금"),
        ("S01", "2026-09-07", "INVEST", 4000, "OTHER", "용돈 입금"),
        ("S01", "2026-09-08", "SPEND", -3000, "CAFE_DESSERT", "카페"),
        ("S01", "2026-09-10", "SAVE", -2000, "OTHER", "모으기에서 꺼냄"),
        ("S01", "2026-09-10", "SPEND", 2000, "OTHER", "모으기에서 옮김"),
        ("S01", "2026-09-11", "SPEND", -1500, "CONVENIENCE", "편의점"),
        ("S01", "2026-09-12", "SPEND", -2500, "CAFE_DESSERT", "베이커리"),
        ("S02", "2026-09-08", "SPEND", -9000, "MEAL", "분식집"),
    ],
    columns=["student_id", "date", "envelope", "amount", "category", "memo"],
)


def test_check_ratio():
    assert envelope.check_ratio({"SPEND": 50, "SAVE": 30, "INVEST": 20}) is None
    assert envelope.check_ratio({"SPEND": 50, "SAVE": 30, "INVEST": 30}) is not None
    assert envelope.check_ratio({"SPEND": 120, "SAVE": -20, "INVEST": 0}) is not None


@pytest.mark.parametrize("amount, ratio", [
    (20000, {"SPEND": 50, "SAVE": 30, "INVEST": 20}),
    (15000, {"SPEND": 33, "SAVE": 33, "INVEST": 34}),
    (9999, {"SPEND": 45, "SAVE": 45, "INVEST": 10}),
    (20000, {"SPEND": 100, "SAVE": 0, "INVEST": 0}),
])
def test_split_allowance_sums_to_amount(amount, ratio):
    split = envelope.split_allowance(amount, ratio)
    assert sum(split.values()) == amount
    assert all(isinstance(v, int) and v >= 0 for v in split.values())


def test_split_allowance_values():
    assert envelope.split_allowance(20000, {"SPEND": 50, "SAVE": 30, "INVEST": 20}) == {
        "SPEND": 10000, "SAVE": 6000, "INVEST": 4000}


def test_deposit_entries_skip_zero_envelopes():
    entries = envelope.deposit_entries(20000, {"SPEND": 100, "SAVE": 0, "INVEST": 0})
    assert entries == [("SPEND", 20000, "OTHER", "용돈 입금")]


def test_balances():
    assert envelope.balances(ALLOWANCE, "S01") == {"SPEND": 5000, "SAVE": 4000, "INVEST": 4000}
    assert envelope.balances(ALLOWANCE, "S03") == {"SPEND": 0, "SAVE": 0, "INVEST": 0}


def test_spending_excludes_deposits_and_transfers():
    spent = envelope.spending(ALLOWANCE, "S01")
    assert list(spent["memo"]) == ["베이커리", "편의점", "카페"]
    assert envelope.spending_by_category(ALLOWANCE, "S01") == {"CAFE_DESSERT": 5500, "CONVENIENCE": 1500}


def test_goal_progress_pct():
    assert envelope.goal_progress_pct(25000, 250000) == pytest.approx(10.0)
    assert envelope.goal_progress_pct(300000, 250000) == 100.0
    assert envelope.goal_progress_pct(-100, 250000) == 0.0


def test_append_allowance(tmp_path):
    path = tmp_path / "allowance.csv"
    shutil.copy(store.ALLOWANCE_PATH, path)
    before = store.load_allowance(path)
    ratio = {"SPEND": 50, "SAVE": 30, "INVEST": 20}

    tx_ids = store.append_allowance("S01", "2026-10-04",
                                    envelope.deposit_entries(20000, ratio), path=path)

    after = store.load_allowance(path)
    assert len(after) == len(before) + 3
    assert after["tx_id"].is_unique
    assert list(after["tx_id"].tail(3)) == tx_ids
    assert int(after["amount"].tail(3).sum()) == 20000
    assert envelope.balances(after, "S01")["SAVE"] == envelope.balances(before, "S01")["SAVE"] + 6000


def test_save_envelope_ratio_changes_only_one_student(tmp_path):
    path = tmp_path / "students.json"
    shutil.copy(store.STUDENTS_PATH, path)
    before = {s["student_id"]: s for s in store.load_students(path)}
    new_ratio = {"SPEND": 40, "SAVE": 40, "INVEST": 20}

    store.save_envelope_ratio("S02", new_ratio, path=path)

    after = {s["student_id"]: s for s in store.load_students(path)}
    assert after["S02"]["envelope_ratio"] == new_ratio
    assert after["S01"] == before["S01"] and after["S03"] == before["S03"]
    assert {k: v for k, v in after["S02"].items() if k != "envelope_ratio"} == \
           {k: v for k, v in before["S02"].items() if k != "envelope_ratio"}


def test_deposit_only_once_per_week():
    import pandas as pd
    allowance = pd.DataFrame([
        {"tx_id": "A0001", "student_id": "S01", "date": "2026-09-28", "envelope": "SPEND",
         "amount": 20000, "category": "OTHER", "memo": envelope.DEPOSIT_MEMO},
        {"tx_id": "A0002", "student_id": "S01", "date": "2026-10-01", "envelope": "SPEND",
         "amount": -3000, "category": "MEAL", "memo": "분식"},
    ])
    # 같은 주(월 09-28 ~ 일 10-04)에는 이미 받음
    assert envelope.deposit_date_this_week(allowance, "S01", "2026-10-03") == "2026-09-28"
    # 다음 주, 다른 학생은 받을 수 있음
    assert envelope.deposit_date_this_week(allowance, "S01", "2026-10-05") is None
    assert envelope.deposit_date_this_week(allowance, "S02", "2026-10-03") is None
