"""5-1: Mistake-to-Lesson 기록 저장·불러오기 검증."""

from pathlib import Path

from conftest import open_app

from engine import store

ROOT = Path(__file__).resolve().parent.parent
PAGE = "pages/3_실수에서_배우기.py"


def record(**overrides):
    base = {"student_id": "S01", "trade_id": "T0014", "date": "2026-10-02",
            "patterns": ["몰빵", "근거 없음"], "question": "어떤 근거로 샀나요?",
            "answer": "큰 회사라서,\n그냥 샀어요", "error_type": "근거 부족",
            "reason": "이유가 막연했어요.", "concept": "INVESTMENT_JOURNAL",
            "explanation": "근거를 적어 두면 돌아볼 수 있어요.", "next_try": "사기 전에 이유를 적어요."}
    return {**base, **overrides}


def test_missing_file_is_empty(tmp_path):
    lessons = store.load_lessons(tmp_path / "lessons.csv")
    assert len(lessons) == 0 and list(lessons.columns) == store.LESSON_COLUMNS


def test_append_and_load_round_trip(tmp_path):
    path = tmp_path / "lessons.csv"
    first = store.append_lesson(record(), path=path)
    second = store.append_lesson(record(trade_id="T0010", patterns=["몰빵"]), path=path)

    lessons = store.load_lessons(path)
    assert (first, second) == ("L0001", "L0002")
    assert list(lessons.columns) == store.LESSON_COLUMNS
    assert lessons.iloc[0]["patterns"] == ["몰빵", "근거 없음"]
    assert lessons.iloc[1]["patterns"] == ["몰빵"]
    assert lessons.iloc[0]["answer"] == "큰 회사라서, 그냥 샀어요"  # 쉼표 유지, 줄바꿈은 공백


def test_append_to_header_only_file(tmp_path):
    path = tmp_path / "lessons.csv"
    path.write_text(",".join(store.LESSON_COLUMNS) + "\n", encoding="utf-8")
    assert store.append_lesson(record(), path=path) == "L0001"
    assert len(store.load_lessons(path)) == 1


def test_page_shows_saved_lesson_after_restart(tmp_path, monkeypatch):
    """앱을 새로 켠 것처럼 빈 세션으로 열어도 저장된 기록이 보인다."""
    path = tmp_path / "lessons.csv"
    store.append_lesson(record(), path=path)
    monkeypatch.setattr(store, "LESSONS_PATH", path)

    at = open_app(PAGE)

    assert not at.exception
    assert at.main.selectbox[0].value == "T0014"  # 가장 최근 실수 매수
    assert "돌아봄" in at.main.selectbox[0].options[0]
    assert any("어떤 근거로 샀나요?" in i.value for i in at.info)
    assert any("근거 부족" in m.value for m in at.markdown)
    assert [b.label for b in at.button] == ["다시 답해 보기"]


def test_page_without_saved_lesson_starts_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LESSONS_PATH", tmp_path / "lessons.csv")
    at = open_app(PAGE)
    assert not at.exception
    assert [b.label for b in at.button] == ["AI 코치에게 질문 받기"]
