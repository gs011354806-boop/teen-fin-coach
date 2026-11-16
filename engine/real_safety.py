"""실전투자 진입 안전장치: 전환 확인 + 안전 체크리스트 (2026-11-16, 시뮬레이션 ·
safety/teengrow_real_safety/REAL_SAFETY_SPEC.md). 판단만 하는 순수 함수. LLM 호출 금지.

흐름: 연습 → [실전 누름] → tap_real() → 전환 확인 시트 → (필요하면) 안전 체크리스트 6개 → 실전 화면
- 동의 전(NONE·PENDING·REJECTED) → 잠금(동의 요청 안내), 동의 철회(REVOKED) → 시트 → 보기·팔기만 되는 실전 화면
- 체크리스트가 다시 나오는 때: 처음 / 마지막 체크 날짜 ≠ 오늘(KST) / 문구 버전이 바뀜 /
  체크 뒤 부모가 한도·범위·급등주 설정을 바꿈 / 체크 뒤 동의를 새로 받음
- 실전 → 연습은 확인 없이 바로 (오늘 체크 기록은 남긴다). 실전 화면에서 10분 동안 조작이 없으면 연습으로 자동 복귀.
- 설정값(켜기·버전·자동 복귀 시간)은 config.py (REAL_SAFETY_*). 학생별 기록은 invest.json의 "safety".
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

import config

# 체크리스트 문구 (시안 그대로). {중괄호}는 실제 값으로 채운다. 문구를 바꾸면 config.REAL_SAFETY_VERSION을 1 올린다.
ITEMS = [
    ("real_money", "여기는 실전이에요",
     "연습 머니가 아니라 내 실전 계좌의 진짜 돈이 쓰여요. 실전 화면은 남색이고 노란 점이 붙어 있어요."),
    ("loss", "돈을 잃을 수도 있어요",
     "주가가 내려가면 넣은 돈보다 적게 돌려받아요. 실전 투자는 원금이 보장되지 않아요."),
    ("limit", "이번 달 한도를 확인했어요",
     "부모님이 정한 한도 안에서만 살 수 있어요. 판 돈으로 한도가 다시 늘지는 않아요."),
    ("reason", "사는 이유를 먼저 써요",
     "친구가 샀다고, 많이 올랐다고 따라 사지 않아요. 이유를 10자 이상 써야 주문할 수 있어요."),
    ("parent", "부모님께 알림이 가요",
     "사고팔 때마다 종목, 금액, 이유가 부모님께 바로 전달돼요."),
    ("price", "가격은 {price_label}", "{price_body}"),
]
ITEM_COUNT = len(ITEMS)

LOCKED, SWITCH, CHECKLIST, REAL, REAL_VIEW_SELL = "LOCKED", "SWITCH", "CHECKLIST", "REAL", "REAL_VIEW_SELL"


@dataclass(frozen=True)
class SafetyState:
    """학생별로 저장하는 값(last_check_*)과 세션 값(in_real_mode, last_real_activity_at).
    체크 진행 중인 체크박스는 저장하지 않는다 (나가면 처음부터)."""
    last_check_at: datetime | None = None
    last_check_version: int = 0
    in_real_mode: bool = False
    last_real_activity_at: datetime | None = None


def version():
    return config.REAL_SAFETY_VERSION


def needs_checklist(st, now, settings_changed_at=None, consent_activated_at=None):
    if st.last_check_at is None:
        return True
    if st.last_check_at.date() != now.date():  # 매일 첫 진입 (KST 자정 기준)
        return True
    if st.last_check_version != version():  # 문구 변경
        return True
    if settings_changed_at and settings_changed_at > st.last_check_at:  # 한도·범위·급등주 설정 변경
        return True
    if consent_activated_at and consent_activated_at > st.last_check_at:  # 동의를 새로 받음
        return True
    return False


def entry_route(consent_status, st, now, settings_changed_at=None, consent_activated_at=None):
    """[실전]을 눌렀을 때 거칠 화면 순서."""
    if consent_status == "REVOKED":
        return [SWITCH, REAL_VIEW_SELL]
    if consent_status != "ACTIVE":
        return [LOCKED]
    if needs_checklist(st, now, settings_changed_at, consent_activated_at):
        return [SWITCH, CHECKLIST, REAL]
    return [SWITCH, REAL]


def switch_sheet_copy(st, now, **kw):
    """전환 확인 시트의 안내 줄 · 버튼 문구."""
    if needs_checklist(st, now, **kw):
        return {"notice_b": "오늘 안전 체크를 아직 안 했어요.", "notice": "다음 화면에서 6가지를 확인해요.",
                "cta": "안전 체크하고 들어가기"}
    return {"notice_b": f"오늘 {fmt_time(st.last_check_at)}에 안전 체크를 마쳤어요.", "notice": "",
            "cta": "실전으로 들어가기"}


def render_items(limit_left, monthly_limit, per_order, quote_source="eod", bas_dt=None):
    """항목 3(한도)·6(가격)을 실제 값으로 채운 6개 항목. 3번은 limit 값을 따로 돌려준다 (화면이 막대로 그린다)."""
    if quote_source == "eod":
        when = f"{bas_dt.month}월 {bas_dt.day}일({'월화수목금토일'[bas_dt.weekday()]})" if bas_dt else "전 영업일"
        price_label = "전날 종가예요"
        price_body = f"지금 실전 가격은 {when} 종가예요. 실시간 가격이 아니어서 오늘 실제 시장 가격과 다를 수 있어요."
    else:  # 증권사 실시간으로 바꾸면 문구도 자동으로 바뀐다
        price_label = "계속 움직여요"
        price_body = (f"실전 가격은 {config.REALTIME_QUOTE_INTERVAL_SEC}초마다 바뀌어요. "
                      "주문 확인 화면의 가격과 체결 가격이 조금 다를 수 있어요.")
    vals = {"price_label": price_label, "price_body": price_body}
    items = []
    for n, (key, title, body) in enumerate(ITEMS):
        item = {"id": key, "no": n + 1, "title": title.format(**vals), "body": body.format(**vals)}
        if key == "limit":
            item["limit"] = {"left": limit_left, "monthly": monthly_limit, "per_order": per_order,
                             "text": f"남은 한도 {limit_left:,}원 / {monthly_limit:,}원 · 한 번에 {per_order:,}원까지"}
        items.append(item)
    return items


def can_enter(checked):
    return len(checked) == ITEM_COUNT and all(checked)


def cta_label(checked):
    left = ITEM_COUNT - sum(bool(c) for c in checked)
    return "실전 화면으로 들어가기" if left == 0 else f"{left}개 더 확인하면 열려요"


def record_check(st, now):
    """6개를 다 누르고 [들어가기]를 눌렀을 때만."""
    return replace(st, last_check_at=now, last_check_version=version(), in_real_mode=True, last_real_activity_at=now)


def enter_real(st, now):
    return replace(st, in_real_mode=True, last_real_activity_at=now)


def touch(st, now):
    """실전 화면에서 무언가 할 때마다 (rerun마다)."""
    return replace(st, last_real_activity_at=now) if st.in_real_mode else st


def should_auto_exit(st, now, idle_min=None):
    idle_min = config.REAL_SAFETY_IDLE_MIN if idle_min is None else idle_min
    if not st.in_real_mode or st.last_real_activity_at is None:
        return False
    return now - st.last_real_activity_at >= timedelta(minutes=idle_min)


def exit_to_practice(st):
    """실전 → 연습: 확인 없이 바로. 오늘 체크 기록은 남긴다 (다시 들어올 땐 시트만)."""
    return replace(st, in_real_mode=False)


def parent_badge(st, now):
    if st.last_check_at and st.last_check_at.date() == now.date() and st.last_check_version == version():
        return f"오늘 안전 체크 완료 · {fmt_time(st.last_check_at)}"
    return "오늘은 아직 실전에 들어가지 않았어요"


def fmt_time(t):
    if t is None:
        return ""
    return f"{'오전' if t.hour < 12 else '오후'} {t.hour % 12 or 12}:{t.minute:02d}"


# ---------- 저장 (invest.json의 학생 상태 안 "safety") ----------

def _parse(value):
    return datetime.fromisoformat(value) if value else None


def from_saved(state, session=None):
    """invest 상태 dict + 세션 값 → SafetyState."""
    saved = state.get("safety") or {}
    session = session or {}
    return SafetyState(_parse(saved.get("last_check_at")), int(saved.get("last_check_version") or 0),
                       bool(session.get("in_real_mode")), session.get("last_real_activity_at"))


def to_saved(state, st):
    """저장할 값만 invest 상태에 쓴다. 체크할 때마다 기록(log)도 남긴다 (부모 화면·발표 자료용)."""
    old = state.get("safety") or {}
    stamp = st.last_check_at.isoformat(timespec="seconds") if st.last_check_at else None
    state["safety"] = {"last_check_at": stamp, "last_check_version": st.last_check_version}
    if stamp and stamp != old.get("last_check_at"):
        state.setdefault("safety_log", []).append({"checked_at": stamp, "version": st.last_check_version})
    return state


def settings_changed_at(state):
    g = state.get("guardrails") or {}
    return _parse(g.get("updatedAt", "")[:19]) if g.get("updatedAt") else None


def consent_activated_at(state):
    c = state.get("consent") or {}
    return _parse(c.get("decided_at", "")[:19]) if c.get("status") == "ACTIVE" and c.get("decided_at") else None
