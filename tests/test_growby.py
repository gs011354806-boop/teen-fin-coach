"""마스코트 그로비 (mascot/teengrow_mascot/MASCOT_SPEC.md 5장 + 앱 화면)."""

import pytest

import config
import growby as g
from conftest import open_app
from engine import rewards

NEWS = "pages/12_이번_주_금융_뉴스.py"
MARKET = "pages/1_가상_주식시장.py"


# ---------- 파일 · 상황 → 표정 · 단계 · 크기 ----------

def test_all_files_exist_and_are_svg():
    for name, _ in list(g.EXPRESSIONS.values()) + list(g.LEVELS.values()):
        p = g.ASSET_DIR / name
        assert p.exists(), name
        assert p.read_text(encoding="utf-8").lstrip().startswith("<svg")


def test_every_situation_has_expression():
    assert set(g.SITUATIONS.values()) <= set(g.EXPRESSIONS)
    assert g.expression_for("모르는_상황") == "default"


@pytest.mark.parametrize("situation,expr", [
    ("home_greeting", "hello"), ("quiz_correct", "cheer"), ("level_up", "cheer"),
    ("quiz_wrong", "think"), ("real_checklist", "safety"), ("real_blocked", "safety"),
    ("update_failed", "sleep"), ("idle_return", "sleep"), ("invest_tip", "default"),
])
def test_situation_map(situation, expr):
    assert g.expression_for(situation) == expr


def test_levels_clamped():
    assert g.file_for(level=1)[0] == "growby_lv1_pink.svg"
    assert g.file_for(level=5)[0] == "growby_lv5_gold.svg"
    assert g.file_for(level=9)[0] == "growby_lv5_gold.svg"
    assert g.file_for(level=0)[0] == "growby_lv1_pink.svg"


def test_size_rules():
    assert g.clamp_size("bubble", 200) == 72 and g.clamp_size("bubble", 10) == 40
    assert g.clamp_size("result", 110) == 110 and g.clamp_size("empty", 40) == 160


def test_img_html_alt_and_data_uri_without_inline_style():
    h = g.img_html("quiz_correct", "result", 110)
    assert 'alt="신난 그로비"' in h and "data:image/svg+xml;base64," in h and 'width="110"' in h
    assert "style=" not in h  # 모양은 style.css (CLAUDE.md)
    assert 'alt=""' in g.img_html("home_greeting", decorative=True)


# ---------- 말풍선 문구 검사 ----------

@pytest.mark.parametrize("line", [
    "좋은 아침이에요! 오늘 뉴스 3개가 도착했어요.",
    "3문제 다 맞혔어요! +50P",
    "괜찮아요, 해설 카드 같이 볼까요?",
    "여기부터는 진짜 돈이에요. 같이 확인해요.",
    "새 소식을 기다리는 중이에요.",
    "바구니 하나에 83%가 담겨 있어요. 나눠 담으면 어떨까요?",
    "사는 이유를 먼저 썼네요, 좋은 습관이에요!",
])
def test_good_lines_pass(line):
    assert g.check_line(line) == []


@pytest.mark.parametrize("line,why", [
    ("지금 사면 좋아요!", "매매를 재촉함"),
    ("삼성전자 사세요!", "매매를 권유함"),
    ("오늘의 추천 종목이에요.", "종목 추천"),
    ("수익률 10%라니 대단해요!", "수익으로 칭찬"),
    ("10% 벌었네요!", "수익으로 칭찬"),
    ("그것도 몰라요?", "놀리거나 깎아내림"),
    ("이러다 다 잃어요.", "겁주기"),
    ("좋아요. 정말 좋아요. 아주 좋아요.", "너무 김"),
    ("오늘은 뉴스도 읽고 퀴즈도 풀고 투자 일지도 쓰고 이번 주 미션도 해서 정말 정말 바쁜 하루였네요!", "너무 김"),
    ("좋은 아침", "해요체가 아님"),
])
def test_bad_lines_caught(line, why):
    assert why in g.check_line(line)


def test_safe_line_fallback_first_safe_and_escape():
    assert g.safe_line("지금 사세요!") == "같이 천천히 알아봐요."
    assert g.first_safe("너무 길어서 안 되는 문장이에요. 정말 너무 길어요. 아주 많이 길어요.", "짧게 말해요.") == "짧게 말해요."
    assert "&lt;b&gt;" in g.bubble_html("home_greeting", "<b>안녕</b>하세요.")  # HTML 주입 방지


def test_demo_card_tips_pass_and_ai_tip_is_checked():
    from engine import news_daily as nd, store
    for item in nd.load_demo(store.load_concepts())["items"]:
        assert g.check_line(item["cards"][2]["tip"]) == [], item["cards"][2]["tip"]


# ---------- 앱 화면 ----------

def texts(at):
    return " ".join(m.value for m in at.markdown)


def test_home_greets_with_hello_growby_once():
    at = open_app()
    assert not at.exception, at.exception
    t = texts(at)
    assert t.count("class=\"growby ") == 1 and "growby-hello" in t and "tini" not in t


def test_quiz_result_shows_cheer_or_think():
    at = open_app(NEWS, query={"mock": "1"})
    at.session_state["news-view"] = {"screen": "quiz", "idx": 2, "slide": 0}
    at = at.run()
    next(b for b in at.button if b.label.startswith("C  ")).click()
    at = at.run()
    assert 'alt="신난 그로비"' in texts(at) and texts(at).count("class=\"growby ") == 1


def test_card_me_bubble_and_progress_use_growby():
    at = open_app(NEWS, query={"mock": "1"})
    assert "growby-default" in texts(at)  # 진행 카드
    at.session_state["news-view"] = {"screen": "card", "idx": 2, "slide": 2}
    at = at.run()
    t = texts(at)
    assert "growby-default" in t and "모르는 링크는 누르지 않아요." in t


def test_checklist_header_shows_safety_growby_only_in_real_entry():
    at = open_app(MARKET, query={"mock": "safety"})
    assert "growby-safety" not in texts(at)  # 연습 화면에는 안전요원 표정이 없다
    at.segmented_control(key="inv-mode-widget").set_value("실전 계좌")
    at = at.run()
    next(b for b in at.button if b.key == "switch-go").click()
    at = at.run()
    assert "growby-safety" in texts(at)


@pytest.mark.parametrize("balance,alt", [(0, "분홍 그로비 · 씨앗"), (800, "하늘 그로비 · 떡잎"), (1650, "민트 그로비 · 두 잎"),
                                         (2600, "보라 그로비 · 꽃봉오리"), (3600, "황금 그로비 · 황금 잎")])
def test_rewards_piggy_is_growby_by_level(monkeypatch, balance, alt):
    monkeypatch.setattr(rewards, "balance", lambda *args: balance)
    at = open_app("pages/5_포인트와_캐릭터.py")
    assert not at.exception, at.exception
    assert f'alt="{alt}"' in texts(at)


def test_flag_off_brings_back_tini(monkeypatch):
    monkeypatch.setattr(config, "GROWBY_MASCOT", False)
    at = open_app()
    t = texts(at)
    assert "tini" in t and "class=\"growby " not in t
