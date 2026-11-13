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
    cards = [m.value for m in at.markdown if "env-card" in m.value]
    assert len(cards) == 3 and "쓰기" in cards[0] and "모으기" in cards[1] and "투자연습" in cards[2]
    assert [b.label for b in at.button if b.key and b.key.startswith("open-")][:3] == [
        "쓰기 봉투 열기", "모으기 봉투 열기", "투자연습 봉투 열기"]


@pytest.mark.parametrize("env, title", [("SPEND", "쓰기 봉투"), ("SAVE", "모으기 봉투"), ("INVEST", "투자연습 봉투")])
def test_envelope_detail_renders(env, title):
    at = open_app("pages/2_용돈봉투.py", query={"env": env})
    assert not at.exception
    assert at.title[0].value == title
    assert at.button(key="back-button").label == "뒤로"  # 상세의 뒤로가기 → 봉투 목록


def test_envelope_card_opens_detail_and_back():
    at = open_app("pages/2_용돈봉투.py")
    at.button(key="open-SAVE").click().run()
    assert at.query_params["env"] in ("SAVE", ["SAVE"]) and at.title[0].value == "모으기 봉투"
    at.button(key="back-button").click().run()
    assert "env" not in at.query_params and at.title[0].value == "용돈봉투"


def test_lesson_page_renders_without_calling_llm():
    at = open_app("pages/3_실수에서_배우기.py")
    assert not at.exception
    assert at.main.selectbox[0].options  # 민지(몰빵형)는 돌아볼 매수가 있다
    assert at.button[0].label == "AI 코치에게 질문 받기"


PAGES = ["pages/1_가상_주식시장.py", "pages/2_용돈봉투.py", "pages/3_실수에서_배우기.py",
         "pages/4_이번_주_미션.py", "pages/5_포인트와_캐릭터.py", "pages/6_부모_리포트.py",
         "pages/7_개념_물어보기.py", "pages/8_실전_준비_단계.py", "pages/9_효과_측정.py", "pages/10_마이데이터_연결.py", "pages/11_자산_키우기_게임.py", "pages/12_이번_주_금융_뉴스.py"]


def back_links(at):
    return [link for link in at.get("page_link") if link.proto.label == "뒤로"]


def test_every_page_has_back_button_to_home_when_opened_first():
    """처음 들어온 화면이면 뒤로가기는 홈으로 간다."""
    for page in PAGES:
        at = open_app(page)
        assert not at.exception, page
        links = back_links(at)
        assert len(links) == 1, page
        assert links[0].proto.page == ""  # 빈 경로 = 홈(app.py)


def test_back_goes_to_previous_page():
    """홈 → 용돈봉투 → 포인트로 왔으면 뒤로가기는 용돈봉투, 용돈봉투로 돌아오면 그다음 뒤로가기는 홈."""
    at = open_app("pages/2_용돈봉투.py")
    at.switch_page("pages/5_포인트와_캐릭터.py").run()
    assert not at.exception
    assert back_links(at)[0].proto.page == "용돈봉투"
    at.switch_page("pages/2_용돈봉투.py").run()  # 뒤로 간 것과 같다
    assert back_links(at)[0].proto.page == ""


def test_home_has_no_back_button():
    assert back_links(open_app()) == []


@pytest.mark.parametrize("page", [None] + PAGES)
def test_every_page_renders_without_top_disclaimer(page):
    """맨 위 안내 문구는 2026-11-13 사용자 결정으로 뺐다."""
    at = open_app(page)
    assert not at.exception, page
    # 앱 시작 로고 화면(splash.py) 맨 아래 안내 문구는 SPLASH_SPEC.md에 따라 남긴다 (화면 맨 위 문구가 아님)
    assert not any("실제 우리은행 서비스 아님" in m.value and "tg-splash" not in m.value for m in at.markdown)
