"""금융 개념 7개가 모두 화면 어딘가에 연결되어 있는지 (개념 문장은 content/concepts 파일 그대로)."""

import pandas as pd
import pytest

from conftest import open_app
from engine import detect, envelope, mission, store
from llm import client

CONCEPTS = store.load_concepts()


def test_every_concept_is_shown_somewhere():
    shown = (set(detect.CONCEPT_FOR_ERROR.values()) | set(detect.CONCEPT_FOR_PATTERN.values())
             | set(mission.CONCEPT_FOR_KEYWORD.values()) | {"NEEDS_VS_WANTS"})
    assert shown == set(CONCEPTS)


def test_every_diagnosis_keyword_has_a_concept():
    for d in mission.SKILLS.values():
        for key in ("practice", "stretch"):
            assert mission.concept_for(d[key]) in CONCEPTS
    assert mission.concept_for("모으기 봉투 꺼내 쓰기") == "GOAL_SAVING"
    assert mission.concept_for("모으기 조금 더 늘리기") == "COMPOUND_INTEREST"


def test_impulse_share_pct():
    allowance = pd.DataFrame(
        [("S01", "2026-09-07", "SPEND", 10000, "OTHER", "용돈 입금"),
         ("S01", "2026-09-08", "SPEND", -3000, "CONVENIENCE", "편의점"),
         ("S01", "2026-09-08", "SPEND", -1000, "CAFE", "카페"),
         ("S01", "2026-09-09", "SPEND", -4000, "TRANSPORT", "버스")],
        columns=["student_id", "date", "envelope", "amount", "category", "memo"])
    assert envelope.impulse_share_pct(allowance, "S01") == pytest.approx(50.0)
    assert envelope.impulse_share_pct(allowance, "S09") is None


def texts(at):
    return " ".join(m.value for m in at.markdown)


def test_envelope_page_shows_needs_vs_wants():
    at = open_app("pages/2_용돈봉투.py")
    assert not at.exception
    concept = CONCEPTS["NEEDS_VS_WANTS"]
    assert concept["sections"]["한 줄 정의"] in texts(at)
    assert "편의점·카페가" in texts(at)


@pytest.fixture
def fake_ai(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "MISSIONS_PATH", tmp_path / "missions.csv")
    monkeypatch.setattr(store, "COACHING_PATH", tmp_path / "coaching_weeks.csv")
    monkeypatch.setattr(client, "ask", lambda name, payload, default=None, check=None: dict(default))


@pytest.mark.parametrize("student, concept", [("준호 (중3)", "GOAL_SAVING"),
                                              ("서연 (고1)", "COMPOUND_INTEREST"),
                                              ("민지 (중2)", "INVESTMENT_JOURNAL")])
def test_mission_page_shows_concept_for_practice(fake_ai, student, concept):
    at = open_app("pages/4_이번_주_미션.py")
    at.sidebar.selectbox[0].select(student)
    at = at.run()
    next(b for b in at.button if b.label.endswith("기록으로 진단 받기")).click()
    at = at.run()
    assert not at.exception, at.exception
    assert CONCEPTS[concept]["sections"]["한 줄 정의"] in texts(at)
