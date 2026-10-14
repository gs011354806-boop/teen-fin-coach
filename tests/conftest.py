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
