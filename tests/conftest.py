import sys
from pathlib import Path

# 프로젝트 루트의 engine, ui_common 등을 테스트에서 import할 수 있게 한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def open_app(page=None, timeout=10):
    """실제 앱처럼 app.py로 열고 page로 이동한다 (아래 탭 바의 page_link가 페이지를 찾을 수 있게)."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=timeout)
    if page:
        at.switch_page(page)
    return at.run()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_news_api(monkeypatch):
    """뉴스 화면은 열기만 해도 이번 주 카드뉴스를 만든다. 테스트에서는 실제 네이버·OpenAI를 부르지 않게 키를 '없음'으로."""
    from engine import news

    def no_keys():
        raise news.NewsError("테스트에서는 뉴스 API를 부르지 않아요")
    monkeypatch.setattr(news, "get_keys", no_keys)
