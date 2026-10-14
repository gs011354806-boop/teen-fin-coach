"""content/concepts/ 형식과 내용 규칙 검증."""

import math
import re

import pytest

from engine import store

REQUIRED = {"FOMO", "DIVERSIFICATION", "OVERCONFIDENCE", "GOAL_SAVING", "NEEDS_VS_WANTS",
            "COMPOUND_INTEREST", "INVESTMENT_JOURNAL"}
MISTAKES = {"급등 추격", "몰빵", "근거 없음", "저축 인출", "충동 지출"}
SECTIONS = ["한 줄 정의", "이런 행동이었어요", "다음엔 이렇게 확인해 보세요", "확인 문제"]
ANSWER_MARKS = "①②③④⑤"
TICKER_NAMES = set(store.load_ticker_names().values())

CONCEPTS = store.load_concepts()


def test_required_concepts_exist():
    assert REQUIRED <= set(CONCEPTS)


def test_template_is_not_loaded():
    assert all(c["name_ko"] for c in CONCEPTS.values())
    assert len(CONCEPTS) == len(list(store.CONCEPTS_DIR.glob("[!_]*.md")))


@pytest.mark.parametrize("name", sorted(CONCEPTS))
def test_concept_format(name):
    c = CONCEPTS[name]
    assert set(c) == {"concept", "name_ko", "related_mistakes", "level", "sections", "quiz"}
    assert c["level"] in {"초등", "중등", "고등"}
    assert c["related_mistakes"] and set(c["related_mistakes"]) <= MISTAKES
    assert list(c["sections"]) == SECTIONS
    assert all(c["sections"][s] and "(" not in c["sections"][s][:1] for s in SECTIONS)
    checks = re.findall(r"^\d+\. .+", c["sections"]["다음엔 이렇게 확인해 보세요"], flags=re.M)
    assert len(checks) >= 2


@pytest.mark.parametrize("name", sorted(CONCEPTS))
def test_quiz_answer_is_one_of_options(name):
    quiz = CONCEPTS[name]["quiz"]
    assert quiz["질문"]
    assert len(quiz["보기"]) >= 3
    assert len(quiz["정답"]) == 1 and quiz["정답"] in ANSWER_MARKS[:len(quiz["보기"])]


@pytest.mark.parametrize("name", sorted(CONCEPTS))
def test_no_stock_recommendation(name):
    """규칙 3: 특정 종목 이름을 넣지 않는다."""
    text = str(CONCEPTS[name])
    assert not any(ticker_name in text for ticker_name in TICKER_NAMES)


def test_example_numbers_match_python():
    """규칙 1: 콘텐츠의 예시 숫자를 코드로 다시 계산해 맞춰 본다."""
    assert math.ceil(250000 / 10000) == 25  # goal_saving 확인 문제 정답 ②
    assert 4500 * 4 == 18000 and 4500 * 4 * 4 == 72000  # needs_vs_wants
    assert math.floor(100000 * 1.05 ** 3) == 115762  # compound_interest
    assert "25주" in CONCEPTS["GOAL_SAVING"]["quiz"]["보기"][1]
    assert "18,000원" in CONCEPTS["NEEDS_VS_WANTS"]["sections"]["이런 행동이었어요"]
    assert "72,000원" in CONCEPTS["NEEDS_VS_WANTS"]["sections"]["이런 행동이었어요"]
    assert "115,762원" in CONCEPTS["COMPOUND_INTEREST"]["sections"]["이런 행동이었어요"]
