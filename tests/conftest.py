import sys
from pathlib import Path

# 프로젝트 루트의 engine, ui_common 등을 테스트에서 import할 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def open_app(page=None, timeout=10, query=None):
    """실제 앱처럼 app.py로 열고 page로 이동한다 (아래 탭 바의 page_link가 페이지를 찾을 수 있게).
    query: 주소 뒤 ?키=값 (예: 용돈봉투 상세 {"env": "SPEND"})."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=timeout)
    if page:
        at.switch_page(page)
    for key, value in (query or {}).items():
        at.query_params[key] = value
    return at.run()


def open_stock(ticker="005930", timeout=10, student_label=None, state=None):
    """투자 탭 연습 모드의 종목 상세 · 연습 주문 화면(②)으로 연다 (예전 '가상 주식 연습'의 주문 칸이 여기 있다).
    student_label: 사이드바 학생 (예: "서연 (고1)"), state: 미리 넣을 세션 값."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=timeout)
    at.switch_page("pages/1_가상_주식시장.py")
    at.session_state["inv-screen"] = {"screen": "stock", "symbol": ticker}
    for key, value in (state or {}).items():
        at.session_state[key] = value
    at = at.run()
    if student_label:
        at.sidebar.selectbox[0].select(student_label)
        at = at.run()
    return at


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def invest_state_in_tmp(monkeypatch, tmp_path):
    """투자 탭 상태(data/students/invest.json)는 테스트마다 임시 파일에 (실제 데이터를 건드리지 않게)."""
    from engine import store
    monkeypatch.setattr(store, "INVEST_PATH", tmp_path / "invest.json")
    monkeypatch.setattr(store, "BADGES_PATH", tmp_path / "badges.csv")  # 혜택 탭 황금 돼지 배지
    monkeypatch.setattr(store, "READY_PATH", tmp_path / "ready.json")  # 실전 준비 기준 기록
    # 오늘의 뉴스 · 시세 자동 업데이트: 작업 상태 · 뉴스 저장본 · 학생 기록 · 시세 저장값을 임시 폴더로,
    # 실제 API 주소는 닿지 않는 곳으로 (테스트가 네트워크를 쓰지 않게)
    from engine import news, news_daily, quotes, updater
    monkeypatch.setattr(updater, "STATE_PATH", tmp_path / "job_state.json")
    monkeypatch.setattr(news_daily, "DAILY_DIR", tmp_path / "daily_news")
    monkeypatch.setattr(store, "NEWS_READS_PATH", tmp_path / "news_reads.csv")
    monkeypatch.setattr(store, "NEWS_ANSWERS_PATH", tmp_path / "news_answers.csv")
    monkeypatch.setattr(store, "NEWS_REVIEWS_PATH", tmp_path / "news_reviews.csv")
    monkeypatch.setattr(quotes, "CACHE_PATH", tmp_path / "quote_cache.json")
    monkeypatch.setattr(quotes, "API_URL", "http://127.0.0.1:9/none")
    monkeypatch.setattr(news, "API_URL", "http://127.0.0.1:9/none")
    from engine import price_history  # 차트 3년치 저장도 임시 폴더로, 백필은 스레드 없이
    monkeypatch.setattr(price_history, "HISTORY_DIR", tmp_path / "price_history")
    monkeypatch.setattr(price_history, "BACKGROUND", False)


@pytest.fixture(autouse=True)
def no_real_news_api(monkeypatch):
    """뉴스 화면은 열기만 해도 이번 주 카드뉴스를 만든다. 테스트에서는 실제 네이버·OpenAI를 부르지 않게 키를 '없음'으로."""
    from engine import news

    def no_keys():
        raise news.NewsError("테스트에서는 뉴스 API를 부르지 않아요")
    monkeypatch.setattr(news, "get_keys", no_keys)


@pytest.fixture
def legacy_mission_tab(monkeypatch):
    """예전 미션 탭(AI 코칭 루프, legacy/mission_loop_page.py)을 검사하는 테스트용: 새 미션 탭 스위치를 끈다."""
    import config
    monkeypatch.setattr(config, "MISSION_TAB_V2", False)
