"""앱 시작 스플래시 (initiation/teengrow_splash/SPLASH_SPEC.md 4장)."""

from streamlit.testing.v1 import AppTest

import splash
from conftest import open_app


def test_html_contains_logo_and_disclaimer():
    html = splash.build_splash_html("data:image/png;base64,AAA")
    assert 'src="data:image/png;base64,AAA"' in html
    assert splash.DISCLAIMER in html
    assert 'for="tg-skip"' in html  # 누르면 건너뛰기
    assert 'alt="teengrow 로고 · 지금, 더 똑똑한 금융 습관"' in html


def test_timing_default_2500():
    assert "tgOut 500ms ease 2000ms forwards" in splash.build_splash_html("x")  # 2.0초부터 0.5초 페이드


def test_timing_is_configurable():
    assert "tgOut 500ms ease 2500ms forwards" in splash.build_splash_html("x", total_ms=3000, fade_ms=500)


def test_fade_never_longer_than_total():
    assert "tgOut 300ms ease 0ms forwards" in splash.build_splash_html("x", total_ms=300, fade_ms=500)


def test_reduced_motion_one_second():
    html = splash.build_splash_html("x", reduced_ms=1000)
    # 움직임 없이 1초 뒤 끝난다 (150ms 투명 전환 + 850ms 대기 = 1000ms). 1ms 애니메이션은 쓰지 않는다
    assert "prefers-reduced-motion" in html and "tgOut 150ms linear 850ms forwards" in html
    assert "tgOut 1ms" not in html


def _app():
    import streamlit as st
    from splash import render_splash
    render_splash()
    st.button("다시 그리기")


def _splash_count(at):
    return sum("tg-splash" in m.value for m in at.markdown)


def test_shows_once_per_session():
    at = AppTest.from_function(_app).run()
    assert _splash_count(at) == 1
    at.button[0].click().run()  # rerun (버튼, 탭 이동 등)
    assert _splash_count(at) == 0


def test_flag_off_renders_nothing(monkeypatch):
    import config
    monkeypatch.setattr(config, "SPLASH_ENABLED", False)
    assert splash.render_splash() is False


def test_missing_logo_skips_quietly(monkeypatch, tmp_path):
    monkeypatch.setattr(splash, "LOGO_PATH", tmp_path / "none.png")
    at = AppTest.from_function(_app).run()
    assert not at.exception and _splash_count(at) == 0


def test_real_app_shows_splash_once_then_not_after_moving_tabs():
    at = open_app()
    assert not at.exception and _splash_count(at) == 1
    at.switch_page("pages/5_포인트와_캐릭터.py")
    at = at.run()
    assert not at.exception and _splash_count(at) == 0


def test_logo_file_is_small_png():
    assert splash.LOGO_PATH.exists() and splash.LOGO_PATH.stat().st_size < 60_000
