"""engine/detect.py 검증. 화면 거래에 흔들리지 않게 새로 생성한 샘플 데이터로 본다."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from engine import detect, store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    out = tmp_path_factory.mktemp("sample")
    spec = importlib.util.spec_from_file_location("make_sample_data",
                                                  ROOT / "data" / "make_sample_data.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    generator.main(out)
    students = {s["type"]: s for s in store.load_students(out / "students" / "students.json")}
    trades = store.load_trades(out / "students" / "trades.csv")
    prices = store.load_prices(out / "prices")
    return {t: detect.detect(trades, prices, s) for t, s in students.items()}


def patterns_of(detections):
    return {p for d in detections for p in d["patterns"]}


def test_only_concentrated_student_gets_concentration(sample):
    assert detect.CONCENTRATION in patterns_of(sample["몰빵형"])
    assert detect.CONCENTRATION not in patterns_of(sample["저축 실패형"])
    assert detect.CONCENTRATION not in patterns_of(sample["균형형"])


def test_surge_chase_on_surge_day(sample):
    surge = [d for d in sample["몰빵형"] if detect.SURGE in d["patterns"]]
    assert [(d["date"], d["ticker"]) for d in surge] == [("2026-09-16", "035720")]
    assert surge[0]["change_pct"] >= detect.SURGE_PCT


def test_balanced_student_has_no_mistakes(sample):
    assert detect.mistakes(sample["균형형"]) == []


def test_empty_journal_is_no_reason(sample):
    empty = [d for d in sample["저축 실패형"] if d["journal"] == ""]
    assert empty and all(detect.NO_REASON in d["patterns"] for d in empty)


def test_past_same_pattern_mentions_earlier_only(sample):
    detections = sample["몰빵형"]
    last = detect.mistakes(detections)[0]
    past = detect.past_same_pattern(detections, last["trade_id"])
    assert past and all(p["date"] < last["date"] for p in past)
    assert detect.past_same_pattern(detections, detections[0]["trade_id"]) == []


def test_mistakes_are_latest_first(sample):
    dates = [d["date"] for d in detect.mistakes(sample["몰빵형"])]
    assert dates == sorted(dates, reverse=True)


def test_sell_is_not_checked():
    student = {"student_id": "S09", "virtual_cash": 1000000}
    prices = {"A": pd.DataFrame({"date": ["2026-09-07", "2026-09-08"], "close": [100, 100]})}
    trades = pd.DataFrame(
        [("T1", "S09", "2026-09-07", "A", "BUY", 1, 100, "근거를 충분히 길게 적었어요"),
         ("T2", "S09", "2026-09-08", "A", "SELL", 1, 100, "")],
        columns=store.TRADE_COLUMNS)
    assert [d["trade_id"] for d in detect.detect(trades, prices, student)] == ["T1"]


def test_journal_chars_ignores_spaces():
    assert detect.journal_chars("더 오를듯") == 4
    assert detect.journal_chars("  ") == 0


@pytest.mark.parametrize("error_type, patterns, concept", [
    ("FOMO", ["몰빵"], "FOMO"),
    ("과신", ["근거 없음"], "OVERCONFIDENCE"),
    ("근거 부족", ["급등 추격"], "INVESTMENT_JOURNAL"),
    ("해당 없음", ["몰빵", "근거 없음"], "DIVERSIFICATION"),
    ("해당 없음", ["급등 추격"], "FOMO"),
])
def test_pick_concept(error_type, patterns, concept):
    assert detect.pick_concept(error_type, patterns) == concept


def test_every_mapped_concept_has_content():
    concepts = store.load_concepts()
    mapped = set(detect.CONCEPT_FOR_ERROR.values()) | set(detect.CONCEPT_FOR_PATTERN.values())
    assert mapped <= set(concepts)


def test_fact_sentences_have_no_returns():
    d = {"patterns": detect.PATTERNS, "change_pct": 13.1, "weight_pct": 72, "journal": ""}
    text = " ".join(detect.fact_sentences(d, "카카오"))
    assert "13.1%" in text and "72%" in text and "비워" in text
    assert "수익" not in text and "손실" not in text
