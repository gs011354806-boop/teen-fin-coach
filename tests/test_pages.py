"""화면이 오류 없이 그려지는지만 확인한다. (주문은 넣지 않아 data/를 바꾸지 않는다.)"""

from pathlib import Path

import pytest

from conftest import open_app

ROOT = Path(__file__).resolve().parent.parent


def test_start_page_renders():
    at = open_app()
    assert not at.exception


def test_market_page_shows_names_before_codes():
    at = open_app("pages/1_가상_주식시장.py")
    assert not at.exception
    assert at.main.selectbox[0].options[0] == "삼성전자 (005930)"


def test_envelope_page_renders():
    at = open_app("pages/2_용돈봉투.py")
    assert not at.exception
    assert [m.label for m in at.metric][:3] == ["쓰기 봉투", "모으기 봉투", "투자연습 봉투"]


def test_lesson_page_renders_without_calling_llm():
    at = open_app("pages/3_실수에서_배우기.py")
    assert not at.exception
    assert at.main.selectbox[0].options  # 민지(몰빵형)는 돌아볼 매수가 있다
    assert at.button[0].label == "AI 코치에게 질문 받기"


PAGES = ["pages/1_가상_주식시장.py", "pages/2_용돈봉투.py", "pages/3_실수에서_배우기.py",
         "pages/4_이번_주_미션.py", "pages/5_포인트와_캐릭터.py", "pages/6_부모_리포트.py"]


def back_links(at):
    return [link for link in at.get("page_link") if link.proto.label == "홈으로"]


def test_every_page_has_back_to_home():
    for page in PAGES:
        at = open_app(page)
        assert not at.exception, page
        links = back_links(at)
        assert len(links) == 1, page
        assert links[0].proto.page == ""  # 빈 경로 = 홈(app.py)


def test_home_has_no_back_button():
    assert back_links(open_app()) == []


@pytest.mark.parametrize("page", [None] + PAGES)
def test_disclaimer_on_top(page):
    """공식 명칭은 써도 되지만(2026-10-16), 맨 위 안내 문구는 모든 화면에 남긴다."""
    import ui_common

    at = open_app(page)
    assert not at.exception, page
    assert ui_common.DISCLAIMER in at.markdown[0].value  # 화면의 첫 글 = 안내 문구
