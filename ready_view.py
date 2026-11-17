"""실전 준비 기준 화면 조각 (criteria/teengrow_ready/READY_SPEC.md 2장).

판단은 모두 engine/ready.py가 하고, 여기서는 기록을 읽어 넘기고 화면을 그린다.
- 진행 화면 4상태 (막 시작 · 거의 다 · 완료 · 6개월 재확인)
- 돌아보기 리포트 쓰기 (팔기 거래 하나를 골라 3문항)
- 실전 준비 퀴즈 (10문제, 8개 맞히면 통과, 다시 풀 때마다 순서를 섞음)
- 부모님께 가는 리포트 (수익률·종목 없음)
모양은 style.css의 rd-* 클래스, 색은 config.toml에서만. 화면 코드에 인라인 style을 쓰지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape

import streamlit as st

import ui_common as ui
from engine import invest_track as it, ready as rd, store

UNITS = {"첫 거래 후 일수": "일", "거래한 주": "주", "인정된 거래": "회", "그중 팔기": "회", "근거 쓴 일지": "건",
         "돌아보기": "회", "손실·아쉬운 거래 돌아보기": "회", "최고 점수": "점"}
SHORT = {"첫 거래 후 일수": "첫 거래 후", "손실·아쉬운 거래 돌아보기": "손실·아쉬운 거래"}
REMAIN_WORDS = {"첫 거래 후 일수": ("연습 기간", "일"), "거래한 주": ("거래한 주", "주"), "인정된 거래": ("거래", "회"),
                "그중 팔기": ("팔기", "회"), "근거 쓴 일지": ("일지", "건"), "돌아보기": ("돌아보기", "회"),
                "손실·아쉬운 거래 돌아보기": ("손실 거래 돌아보기", "회"), "최고 점수": ("퀴즈", "점")}
STAGE_TEXT = {
    "early": ("실전까지 천천히 준비해요", "연습하며 아래 5가지를 채우면 부모님께 실전 동의를 요청할 수 있어요."),
    "almost": ("거의 다 왔어요! {n}가지 남았어요", "{left}이 남았어요."),
    "ready": ("실전 준비를 모두 마쳤어요", "이제 부모님께 동의를 요청할 수 있어요. 부모님이 리포트를 보고 정해요."),
    "recheck": ("오랜만이에요! 퀴즈만 다시 확인해요", "6개월 넘게 쉬었어요. 나머지 기록은 그대로예요. 연습은 바로 할 수 있어요."),
}
FOOT = ("수익률·종목은 기준에 들어가지 않아요. 기준은 앱이 정하고 부모님도 바꿀 수 없어요. "
        "6개월 넘게 쉬면 실전 전에 준비 퀴즈만 다시 풀어요.")
KIND_LABEL = {"loss": "손실 난 거래", "regret": "가장 아쉬운 거래", "gain": "수익 난 거래"}
LETTERS = "ABCD"


# ---------- 기록 읽기 ----------

def load(student_id, consent, tables, now, save=True):
    """기록을 읽어 평가한다. 자격 시각(처음 한 번)·재확인 해제를 저장한다. 진행 숫자는 저장하지 않는다."""
    doc = store.load_ready(student_id)
    trades, journals, info = rd.practice_trades(tables, student_id)
    refls, quiz = rd.reflections_from(doc), rd.quiz_from(doc)
    before = rd.state_from(doc)
    state = rd.after_quiz(rd.grandfather(before, consent), quiz)
    readiness = rd.evaluate(now, trades, journals, refls, quiz, state)
    state = rd.mark_qualified(state, readiness, now)
    if save and state != before:
        store.save_ready(student_id, rd.state_to(doc, state))
    return {"student_id": student_id, "doc": doc, "state": state, "trades": trades, "journals": journals,
            "info": info, "refls": refls, "quiz": quiz, "r": readiness, "now": now}


def practice_tables():
    """연습 거래 = 연습용 시세 거래 + 실제 시세 연습 거래 (둘 다 가상 돈)."""
    tables = [store.load_trades(store.TRADES_PATH)]
    if store.REAL_TRADES_PATH.exists():
        tables.append(store.load_trades(store.REAL_TRADES_PATH))
    return tables


def gate(ctx, consent_status):
    """실전 입구에서 (tap_real 앞): None이면 통과, 아니면 NOT_READY · RECHECK_QUIZ · NO_CONSENT."""
    return rd.can_enter_real(ctx["state"], ctx["quiz"], consent_status)


# ---------- 2-1 진행 화면 ----------

def _bar(cur, goal, done):
    pct = 100 if done else round(min(1.0, cur / goal) * 100) if goal else 100
    return f"<div class='rd-bar{' rd-bar-done' if done or cur >= goal else ''}'><i style='--w:{pct}%'></i></div>"


def remaining_text(r):
    out = []
    for item in r.items:
        for label, cur, goal in item.parts:
            if cur < goal:
                word, unit = REMAIN_WORDS.get(label, (label, ""))
                out.append(f"{word} {goal - cur}{unit}")
    return ", ".join(out)


def head_html(r):
    stage = rd.stage_of(r)
    title, sub = STAGE_TEXT[stage]
    n = 5 - r.done_count if stage != "recheck" else 1
    title, sub = title.format(n=n), sub.format(left=remaining_text(r))
    segs = "".join(f"<i class='{'on' if it_.done else ''}'></i>" for it_ in r.items)
    tone = " rd-head-ready" if stage == "ready" else ""
    return (f"<div class='rd-head{tone}'><div class='rd-head-top'>{ui.mascot_html(size='lg', situation=f'ready_{stage}')}"
            f"<div><div class='rd-head-title'>{escape(title)}</div><div class='rd-head-sub'>{escape(sub)}</div></div></div>"
            f"<div class='rd-head-count'><span>채운 기준</span><b>{r.done_count} / 5</b></div>"
            f"<div class='rd-segs'>{segs}</div></div>")


def item_html(n, item, recheck):
    if item.done:
        chip = ("rd-chip-done", "완료")
    elif recheck and item.key == "quiz":
        chip = ("rd-chip-recheck", "다시 확인")
    elif any(cur for _, cur, _ in item.parts):
        chip = ("rd-chip-doing", "진행 중")
    else:
        chip = ("rd-chip-todo", "아직")
    parts = "".join(
        f"<div class='rd-part'><span>{escape(SHORT.get(label, label))}</span>"
        f"<b>{cur} / {goal}{UNITS.get(label, '')}</b></div>{_bar(cur, goal, item.done)}"
        for label, cur, goal in item.parts)
    hint = item.hint
    if item.key == "quiz" and not item.done and not recheck and item.parts[0][1]:
        best = item.parts[0][1]
        hint = f"{best}점 · {rd.QUIZ_PASS - best}개만 더 맞히면 돼요"
    return (f"<div class='rd-item-head'><span class='rd-num{' on' if item.done else ''}'>{n}</span>"
            f"<b class='rd-name'>{escape(item.name)}</b><span class='rd-chip {chip[0]}'>{chip[1]}</span></div>"
            f"{parts}<div class='rd-hint'>{escape(hint)}</div>")


ACTIONS = {"period": ("연습 거래하러 가기", "practice"), "trades": ("연습 거래하러 가기", "practice"),
           "journals": ("연습 거래하러 가기", "practice"), "reflections": ("돌아보기 쓰기", "reflect"),
           "quiz": ("준비 퀴즈 풀기", "quiz")}


def progress_view(ctx, consent_status, on_action, on_request, on_preview):
    """on_action(kind) — practice · reflect · quiz. on_request() — 동의 요청 화면. on_preview() — 리포트 미리 보기."""
    r = ctx["r"]
    with ui.card("rd-head"):
        st.markdown(head_html(r), unsafe_allow_html=True)
    for n, item in enumerate(r.items, 1):
        done_key = "done" if item.done else "open"
        with ui.card(f"rd-item-{done_key}-{item.key}"):
            st.markdown(item_html(n, item, r.needs_recheck), unsafe_allow_html=True)
            if not item.done:
                label, kind = ACTIONS[item.key]
                st.button(label, key=f"rd-go-{item.key}", on_click=on_action, args=(kind,))
    if r.needs_recheck:  # 동의가 있어도 재확인 중에는 실전이 잠긴다 (연습은 바로)
        with st.container(key="rd-locked-box"):
            st.button("퀴즈를 통과하면 실전이 다시 열려요", disabled=True, width="stretch", key="rd-locked")
    elif consent_status == it.ACTIVE:
        st.info("부모님이 이미 실전 투자에 동의했어요. 투자 홈의 '실전 계좌'로 들어가요.")
    elif consent_status == it.PENDING:
        st.info("부모님께 동의를 요청했어요. 부모님 확인을 기다리고 있어요.")
    elif r.can_request_consent:
        with st.container(key="rd-cta"):
            st.button("부모님께 동의 요청하기", type="primary", width="stretch", key="rd-request", on_click=on_request)
            st.button("부모님께 갈 리포트 미리 보기", width="stretch", key="rd-preview", on_click=on_preview)
    else:
        left = "퀴즈를 통과하면 실전이 다시 열려요" if r.needs_recheck else f"{5 - r.done_count}가지를 더 채우면 열려요"
        with st.container(key="rd-locked-box"):
            st.button(left, disabled=True, width="stretch", key="rd-locked")
    ui.muted(FOOT)


# ---------- 2-2 돌아보기 리포트 쓰기 ----------

def _day(iso):
    d = date.fromisoformat(iso[:10])
    return f"{d.month}월 {d.day}일"


def _signed(n):
    return f"+{n:,}원" if n > 0 else f"−{abs(n):,}원" if n < 0 else "0원"


def sell_choices(ctx, names, limit=6):
    """돌아볼 수 있는 팔기 거래 (최근 것부터). 이미 돌아본 거래는 빼고 따로 센다."""
    done_ids = {x.trade_id for x in ctx["refls"]}
    sells = [t for t in reversed(list(ctx["info"].values())) if t["side"] == "SELL"]
    open_ = [t for t in sells if t["id"] not in done_ids][:limit]
    for t in open_:
        t["name"] = names.get(t["ticker"], t["ticker"])
    return open_, len([t for t in sells if t["id"] in done_ids])


def choice_label(t):
    pnl = t["pnl"] or 0
    pct = f" ({pnl / t['cost'] * 100:+.1f}%)".replace("-", "−") if t.get("cost") else ""
    word = "손실" if pnl < 0 else "수익" if pnl > 0 else "본전"
    return f"{t['name']} {t['qty']:g}주 팔았어요 · {_signed(pnl)}{pct} {word}"


def choice_caption(t):
    reason = f" · 그때 쓴 이유: \"{t['journal']}\"" if t["journal"] else ""
    return f"{_day(t['date'])}{reason}"


QUESTIONS3 = (("그때 내 예상은?", "왜 샀는지, 어떻게 될 거라고 생각했는지"),
              ("실제로는?", "가격이 어떻게 움직였고 나는 무엇을 했는지"),
              ("다음엔 이렇게", "다음에 비슷한 상황이 오면 바꿀 행동 하나"))


def count_line(text):
    n = len(rd._plain(text))
    return f"{n}자 · 충분해요" if n >= rd.REFLECTION_MIN_CHARS else f"{n}자 · {rd.REFLECTION_MIN_CHARS}자 이상 써요"


def reflect_view(ctx, names, on_saved):
    """돌아볼 거래를 고르고 3문항을 쓴다. 저장되면 on_saved(문구)."""
    had_loss = any(t.side == "SELL" and (t.pnl or 0) < 0 for t in ctx["trades"])
    n_done = len({x.trade_id for x in ctx["refls"] if rd.reflection_valid(x)})
    ui.mascot_say("잃은 돈보다 배운 걸 적는 게 중요해요. 손실 난 거래부터 골라 볼까요?" if had_loss
                  else "잃은 돈보다 배운 걸 적는 게 중요해요. 가장 아쉬운 거래를 골라 볼까요?",
                  key="rd-reflect", situation="ready_reflect")
    choices, reflected = sell_choices(ctx, names)
    if not choices:
        with ui.card("rd-reflect-empty"):
            st.markdown("**돌아볼 팔기 거래가 아직 없어요**")
            ui.muted("연습 모드에서 산 종목을 팔면 그 거래를 돌아볼 수 있어요." +
                     (f" 이미 돌아본 거래 {reflected}개는 다시 쓸 수 없어요." if reflected else ""))
        return
    with ui.card("rd-pick"):
        st.markdown("**1. 돌아볼 거래 고르기**")
        ids = [t["id"] for t in choices]
        by_id = {t["id"]: t for t in choices}
        pick = st.radio("돌아볼 거래", ids, format_func=lambda i: choice_label(by_id[i]),
                        captions=[choice_caption(by_id[i]) for i in ids], key="rd-pick-w",
                        label_visibility="collapsed")
        regret = False
        if not had_loss:
            regret = st.checkbox("이 거래가 가장 아쉬운 거래예요", key="rd-regret")
        ui.muted('손실 난 거래가 없으면 "가장 아쉬운 거래"를 골라요. 같은 거래는 한 번만 돌아볼 수 있어요.')
    answers = []
    for n, (title, sub) in enumerate(QUESTIONS3, 2):
        with ui.card(f"rd-q{n}"):
            st.markdown(f"**{n}. {title}**")
            text = st.text_area(sub, key=f"rd-a{n}", height=90)
            st.markdown(f"<div class='rd-count{' ok' if len(rd._plain(text)) >= rd.REFLECTION_MIN_CHARS else ''}'>"
                        f"{escape(count_line(text))}</div>", unsafe_allow_html=True)
            answers.append(text)
    goal = rd.REFLECTIONS_MIN
    if st.button(f"저장하기 · 돌아보기 {min(goal, n_done + 1)}/{goal}", type="primary", width="stretch", key="rd-save"):
        t = by_id[pick]
        kind = rd.reflection_kind(t["pnl"], had_loss, regret)
        if rd.add_reflection(ctx["doc"], ctx["now"], pick, kind, answers):
            store.save_ready(ctx["student_id"], ctx["doc"])
            for n in (2, 3, 4):
                st.session_state.pop(f"rd-a{n}", None)
            on_saved("돌아보기를 저장했어요. 배운 점이 기록에 남았어요.")
            st.rerun()
        st.error(f"세 칸 모두 {rd.REFLECTION_MIN_CHARS}자 이상 써 주세요.")
    ui.muted(f"세 칸 모두 {rd.REFLECTION_MIN_CHARS}자 이상이면 저장돼요. 번 돈·잃은 돈의 크기는 실전 준비 기준에 영향을 주지 않아요.")


# ---------- 2-3 실전 준비 퀴즈 ----------

QKEY = "rd-quiz"


def quiz_state(ctx):
    """세션에 지금 푸는 회차를 둔다: {round_no, picks}. 회차 번호 = 지난 시도 수 + 1 (다시 풀면 순서가 바뀐다)."""
    box = st.session_state.get(QKEY)
    if not box or box.get("sid") != ctx["student_id"]:
        box = {"sid": ctx["student_id"], "round_no": len(ctx["quiz"]) + 1, "picks": [], "saved": False}
        st.session_state[QKEY] = box
    return box


def restart_quiz(ctx):
    st.session_state[QKEY] = {"sid": ctx["student_id"], "round_no": len(ctx["quiz"]) + 2, "picks": [], "saved": False}


def quiz_dots(round_, picks, current):
    out = []
    for i, (q, order) in enumerate(round_):
        if i < len(picks):
            out.append("ok" if order[picks[i]] == q.answer else "bad")
        else:
            out.append("now" if i == current else "")
    return "<div class='rd-dots'>" + "".join(f"<i class='{c}'></i>" for c in out) + "</div>"


def options_html(q, order, picked):
    rows = []
    for pos, idx in enumerate(order):
        cls = ""
        tag = ""
        if picked is not None:
            if idx == q.answer:
                cls, tag = " right", "<em>정답</em>"
            elif pos == picked:
                cls, tag = " wrong", "<em>내 답</em>"
        rows.append(f"<div class='rd-opt{cls}'><span>{LETTERS[pos]}</span><div>{escape(q.options[idx])}</div>{tag}</div>")
    return "".join(rows)


def quiz_view(ctx, on_done):
    """한 문제씩: 보기를 누르면 바로 채점 + 해설. 10문제를 다 풀면 기록을 저장하고 결과를 보여 준다."""
    box = quiz_state(ctx)
    round_ = rd.quiz_round(box["round_no"], rd.user_seed(ctx["student_id"]))
    picks = box["picks"]
    total = len(round_)
    if len(picks) >= total and box.get("show_result"):
        return quiz_result(ctx, box, round_, on_done)
    current = min(len(picks), total - 1) if not box.get("answered") else len(picks) - 1
    q, order = round_[current]
    answered = box.get("answered", False)
    right_so_far = sum(order_[p] == q_.answer for (q_, order_), p in zip(round_, picks))
    st.markdown(f"<div class='rd-quiz-top'><b>실전 준비 퀴즈 {current + 1}/{total}</b>"
                f"<span>{rd.QUIZ_PASS}개 맞히면 통과</span></div>{quiz_dots(round_, picks, current)}"
                f"<span class='rd-topic'>{escape(q.topic)}</span>", unsafe_allow_html=True)
    with ui.card("rd-quiz-q"):
        st.markdown(f"<div class='rd-q'>{escape(q.text)}</div>", unsafe_allow_html=True)
        if answered:
            st.markdown(options_html(q, order, picks[-1]), unsafe_allow_html=True)
        else:
            for pos, idx in enumerate(order):
                if st.button(f"{LETTERS[pos]}   {q.options[idx]}", key=f"rd-opt-{box['round_no']}-{current}-{pos}",
                             width="stretch"):
                    picks.append(pos)
                    box["answered"] = True
                    st.rerun()
    if answered:
        ok = order[picks[-1]] == q.answer
        st.markdown(f"<div class='rd-explain{' ok' if ok else ''}'><b>{'정답이에요!' if ok else '이번엔 아쉬워요'}</b>"
                    f"<div>{escape(q.explain)}</div></div>", unsafe_allow_html=True)
        last = len(picks) >= total
        if st.button("결과 보기" if last else "다음 문제", type="primary", width="stretch", key="rd-next"):
            box["answered"] = False
            box["show_result"] = last
            st.rerun()
    else:
        ui.muted("틀려도 괜찮아요. 다 푼 뒤 해설을 보고 다시 도전할 수 있어요. 다시 풀 때는 문제와 보기 순서가 바뀌어요.")
    st.markdown(f"<div class='rd-quiz-foot'>지금까지 {len(picks)}문제 중 {right_so_far}개 정답</div>",
                unsafe_allow_html=True)


def quiz_result(ctx, box, round_, on_done):
    score, wrong = rd.grade(round_, box["picks"])
    if not box["saved"]:
        rd.add_quiz(ctx["doc"], ctx["now"], score, wrong)
        quiz = rd.quiz_from(ctx["doc"])
        state = rd.after_quiz(ctx["state"], quiz)
        store.save_ready(ctx["student_id"], rd.state_to(ctx["doc"], state))
        box["saved"] = True
    passed = score >= rd.QUIZ_PASS
    with ui.card("rd-quiz-result"):
        st.markdown(f"<div class='say'>{ui.mascot_html(size='lg', situation='quiz_all_done' if passed else 'retry')}"
                    f"<div class='say-bubble'>{'통과했어요! 실전 준비 퀴즈를 채웠어요.' if passed else f'{rd.QUIZ_PASS}개를 맞히면 통과예요. 해설을 보고 다시 풀어 봐요.'}"
                    f"</div></div><div class='rd-score'>{rd.QUIZ_TOTAL}문제 중 <b>{score}개</b> 정답</div>",
                    unsafe_allow_html=True)
    misses = [(q, order, p) for (q, order), p in zip(round_, box["picks"]) if order[p] != q.answer]
    if misses:
        ui.section("틀린 문제 해설")
        for n, (q, order, p) in enumerate(misses):
            with ui.card(f"rd-miss-{n}"):
                st.markdown(f"<span class='rd-topic'>{escape(q.topic)}</span><div class='rd-q-sm'>{escape(q.text)}</div>"
                            f"<div class='rd-explain-line'>정답: {escape(q.options[q.answer])}</div>", unsafe_allow_html=True)
                ui.muted(q.explain)
    st.button("다시 풀기 (순서가 바뀌어요)", width="stretch", key="rd-retry", on_click=restart_quiz, args=(ctx,),
              type="secondary" if passed else "primary")
    st.button("실전 준비로 돌아가기", width="stretch", key="rd-quiz-back", on_click=on_done)


# ---------- 2-4 부모님께 가는 리포트 ----------

def make_report(ctx):
    """engine/ready.build_report + 글 3개의 꼬리표 (날짜·돌아보기 종류). 손익·종목은 넣지 않는다."""
    rep = rd.build_report(ctx["now"], ctx["r"], ctx["trades"], ctx["journals"], ctx["refls"], ctx["quiz"],
                          rd.last_wrong_topics(ctx["doc"]))
    last_j = sorted(ctx["journals"], key=lambda j: j.at)[-1:]
    valid = [x for x in sorted(ctx["refls"], key=lambda x: x.at) if rd.reflection_valid(x)][:2]
    rep["quote_tags"] = ([f"투자일지 · {_day(j.at.date().isoformat())}" for j in last_j]
                         + [f"돌아보기 · {KIND_LABEL[x.kind]}" for x in valid])
    rep["quote_kinds"] = ["journal" for _ in last_j] + [x.kind for x in valid]
    rep["kind"] = "ready"
    return rep


def criteria_rows(rep):
    first = _day(rep["first_trade"])
    wrong = f" · 틀린 주제: {', '.join(rep['quiz_wrong_topics'])}" if rep["quiz_wrong_topics"] else ""
    return [("연습 기간", f"{first} 첫 거래 · {rep['days']}일 동안 · {rep['weeks']}주에 걸쳐 거래"),
            ("연습 거래", f"인정된 거래 {rep['trades']}회 · 그중 팔기 {rep['sells']}회"),
            ("근거 쓴 투자일지", f"{rep['journals']}건"),
            ("돌아보기 리포트", f"{rep['reflections']}회"),
            ("실전 준비 퀴즈", f"{rd.QUIZ_TOTAL}문제 중 {rep['quiz_best']}개 정답 ({_day(rep['quiz_at'])}){wrong}")]


def report_html(rep, name, arrived=None):
    """보호자 화면의 실전 준비 리포트 (초록 머리 카드 + 채운 기준 + 아이가 쓴 글 + 이 리포트에 없는 것)."""
    when = f"<span class='rd-rep-when'>{escape(arrived)} 도착</span>" if arrived else ""
    head = (f"<div class='rd-rep-head'>{ui.mascot_html(size='lg', situation='ready_ready')}<div>"
            f"<div class='rd-rep-title'>{escape(name)}의 실전 준비 리포트</div>"
            f"<div class='rd-rep-sub'>{rep['days']}일 동안 연습하며 5가지 기준을 모두 채웠어요. "
            f"실전 투자 동의를 요청했어요.</div></div></div>")
    rows = "".join(f"<div class='rd-rep-row'><span class='rd-check'>✓</span><div><b>{escape(k)}</b>"
                   f"<small>{escape(v)}</small></div></div>" for k, v in criteria_rows(rep))
    tags = rep.get("quote_tags") or [""] * len(rep["quotes"])
    kinds = rep.get("quote_kinds") or ["journal"] * len(rep["quotes"])
    quotes = "".join(f"<div class='rd-quote rd-quote-{escape(k)}'><small>{escape(t)}</small>\"{escape(q)}\"</div>"
                     for q, t, k in zip(rep["quotes"], tags, kinds))
    return (f"{when}{head}<div class='rd-rep-box'><div class='rd-rep-h'>채운 기준</div>{rows}</div>"
            f"<div class='rd-rep-box'><div class='rd-rep-h'>직접 쓴 글에서</div>{quotes}</div>")


NOT_IN_REPORT = ("수익률과 종목은 준비 기준이 아니라서 넣지 않았어요. 기준은 앱이 정하며 보호자도 바꿀 수 없어요. "
                 "6개월 넘게 앱을 쓰지 않으면 실전 전에 준비 퀴즈를 다시 확인해요.")


def not_in_report_html():
    return f"<div class='rd-note'><b>이 리포트에 없는 것</b><div>{escape(NOT_IN_REPORT)}</div></div>"


def plan_html(guardrails):
    """동의하면 정하게 될 것 (앱이 처음 추천하는 값, 보호자가 언제든 바꿀 수 있음)."""
    rows = [("한 달 투자 한도", f"{guardrails['monthlyLimit']:,}원"),
            ("한 번에 살 수 있는 돈", f"{guardrails['perOrderLimit']:,}원"),
            ("살 수 있는 범위", it.SCOPES[guardrails["scope"]][0]),
            ("급등주 확인 단계", "켜짐" if guardrails["fomoCheck"] else "꺼짐")]
    body = "".join(f"<div class='sum-row'><span>{escape(k)}</span><b>{escape(v)}</b></div>" for k, v in rows)
    return (f"<div class='rd-rep-box'><div class='rd-rep-h'>동의하면 정하게 될 것</div>"
            f"<div class='rd-rep-sub2'>처음 값은 앱이 추천하고, 부모님이 언제든 바꿀 수 있어요.</div>"
            f"<div class='sum'>{body}</div></div>")


def today_label(now: datetime):
    return f"{now.month}월 {now.day}일"
