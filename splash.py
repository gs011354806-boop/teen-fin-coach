"""teengrow 앱 시작 스플래시(로고 화면) → 홈 (2026-11-13, 시뮬레이션 · initiation/teengrow_splash/SPLASH_SPEC.md).

- ui_common.setup()이 st.set_page_config 바로 다음에 한 번 부른다. 세션당 1회 (어느 화면으로 들어와도 처음 한 번).
- JS·time.sleep·st.rerun 없이 CSS 애니메이션만으로 사라진다. 떠 있는 동안 아래에서 화면이 그대로 그려진다.
- 화면 아무 곳이나 누르면 0.2초 만에 사라진다 (숨긴 체크박스 + 덮개 전체 label).
- '동작 줄이기'를 켠 사용자는 애니메이션 없이 1초 뒤 사라진다. 로고 파일이 없으면 조용히 건너뛴다.
- 설정값(켜기·시간)은 config.py (SPLASH_*), 색은 config.toml 값(var(--이름))만 쓴다.
"""

import base64
from html import escape
from pathlib import Path

import streamlit as st

import config

SESSION_KEY = "tg_splash_shown"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "teengrow_logo.png"
LOGO_ALT = "teengrow 로고 · 지금, 더 똑똑한 금융 습관"
DISCLAIMER = "대학 수업 프로젝트 · 우리은행 적용 가정 제안 시안 · 실제 우리은행 서비스 아님"  # 명세: 빼지 않는다


@st.cache_data(show_spinner=False)
def _logo_data_uri(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def build_splash_html(logo_uri, total_ms=None, fade_ms=None, reduced_ms=None):
    """순수 함수: 스플래시 HTML(+CSS) 문자열. 페이드는 전체 시간보다 길 수 없다."""
    total_ms = config.SPLASH_TOTAL_MS if total_ms is None else total_ms
    fade_ms = config.SPLASH_FADE_MS if fade_ms is None else fade_ms
    reduced_ms = config.SPLASH_REDUCED_MS if reduced_ms is None else reduced_ms
    fade_ms = max(0, min(fade_ms, total_ms))
    hold_ms = total_ms - fade_ms
    return f"""
<style>
@keyframes tgIn {{ from {{ opacity:0; transform:translateY(8px) scale(.94); }} to {{ opacity:1; transform:none; }} }}
@keyframes tgDot {{ 0%,80%,100% {{ opacity:.25; }} 40% {{ opacity:1; }} }}
@keyframes tgOut {{ to {{ opacity:0; visibility:hidden; }} }}
.tg-splash {{
  position:fixed; inset:0; z-index:1000000; background:var(--surface, white);
  display:flex; flex-direction:column; align-items:center;
  cursor:pointer; margin:0;
  animation:tgOut {fade_ms}ms ease {hold_ms}ms forwards;
}}
.tg-skip {{ position:absolute; opacity:0; pointer-events:none; width:1px; height:1px; }}
.tg-skip:checked + .tg-splash {{ animation:tgOut 200ms ease forwards; }}
.tg-splash__center {{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:36px; }}
.tg-splash__logo {{ width:248px; max-width:64vw; height:auto; display:block; animation:tgIn 600ms ease-out both; }}
.tg-splash__dots {{ display:flex; gap:8px; }}
.tg-splash__dots span {{
  width:8px; height:8px; border-radius:4px; background:color-mix(in srgb, var(--green) 80%, white);
  animation:tgDot 1.2s ease-in-out infinite;
}}
.tg-splash__dots span:nth-child(2) {{ animation-delay:.2s; }}
.tg-splash__dots span:nth-child(3) {{ animation-delay:.4s; }}
.tg-splash__note {{ display:block; margin:0; padding:0 24px 32px; font-size:11px; line-height:1.5; color:var(--gray); text-align:center; }}
@media (prefers-reduced-motion: reduce) {{
  .tg-splash__logo, .tg-splash__dots span {{ animation:none; }}
  /* 움직임 없이 reduced_ms 뒤 사라진다. 1ms 애니메이션은 Chrome에서 visibility가 visible로 남아
     아래 화면을 누를 수 없었다 (2026-11-13 확인) → 끝 상태를 늦게 거는 짧은 투명 전환으로 바꿨다 */
  .tg-splash {{ animation:tgOut 150ms linear {max(0, reduced_ms - 150)}ms forwards; }}
}}
</style>
<input type="checkbox" id="tg-skip" class="tg-skip" aria-hidden="true" tabindex="-1">
<label class="tg-splash" for="tg-skip" aria-label="로고 화면 건너뛰고 홈으로">
  <div class="tg-splash__center">
    <img class="tg-splash__logo" src="{escape(logo_uri, quote=True)}" alt="{LOGO_ALT}">
    <div class="tg-splash__dots" aria-hidden="true"><span></span><span></span><span></span></div>
  </div>
  <span class="tg-splash__note">{DISCLAIMER}</span>
</label>
"""


def render_splash():
    """세션당 한 번만 스플래시를 띄운다. 띄웠으면 True. config.SPLASH_ENABLED가 False면 아무것도 하지 않는다."""
    if not config.SPLASH_ENABLED or st.session_state.get(SESSION_KEY):
        return False
    st.session_state[SESSION_KEY] = True
    if not LOGO_PATH.exists():  # 로고가 없으면 조용히 건너뛴다 (앱은 정상 동작)
        return False
    st.markdown(build_splash_html(_logo_data_uri(str(LOGO_PATH))), unsafe_allow_html=True)
    return True
