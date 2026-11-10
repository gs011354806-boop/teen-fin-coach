"""미션 탭 (28번, 시뮬레이션). 명세: teen-app/MISSION_TAB_SPEC.md · 정리: docs/MISSION_TAB.md

소비 미션: ① 홈(이번 주 미션 + AI Replay + 지난 미션) → ② 시뮬레이션(A/B/C) → ③ 결과(수행률·달라진 행동·코치)
투자 미션: ④ 홈 → ⑤ Replay → ⑥ 시뮬레이션. 화면만 만들고 잠가 둔다 (config.INVEST_MISSION_ENABLED).
같은 페이지 안에서 ?view= 로 화면이 바뀐다. 계산은 engine/spend_mission.py · engine/invest_mission.py.
config.MISSION_TAB_V2 = False면 예전 AI 코칭 루프(legacy/mission_loop_page.py)를 그대로 보여 준다.
"""

import runpy
from html import escape
from pathlib import Path

import streamlit as st

import config

if not config.MISSION_TAB_V2:
    runpy.run_path(str(Path(__file__).resolve().parent.parent / "legacy" / "mission_loop_page.py"))
    st.stop()

import ui_common as ui  # noqa: E402
from engine import envelope, invest_mission, rewards, spend_mission as sm, store  # noqa: E402
from ui_common import won  # noqa: E402

TRACKS = {"spend": "소비 미션", "invest": "투자 미션"}

student = ui.setup("미션", "🚩", active="mission")
student_id = student["student_id"]
allowance = store.load_allowance()
today = sm.today_of(allowance)
runs = store.load_mission_runs()


def all_events():
    return rewards.apply_daily_cap(rewards.earn_events(
        student, store.load_trades(), store.load_missions(), store.load_allowance(), store.load_game_reviews(),
        store.load_news_quiz(), store.load_spend_quiz(), store.load_mission_runs()))


def go(view=None, **params):
    """화면 바꾸기 (on_click에서 부른다)."""
    for key in ("view", "run"):
        st.query_params.pop(key, None)
    if view:
        st.query_params["view"] = view
    for key, value in params.items():
        st.query_params[key] = value


# ---------- 작은 그림 조각 (색은 style.css 클래스, 숫자만 SVG 속성으로) ----------

def bar(fraction, marker=None, tone="blue"):
    """진행 바 + 목표 마커. fraction·marker는 0~1."""
    width = round(max(0.0, min(1.0, fraction)) * 100, 1)
    mark = (f"<rect class='mbar-marker' x='{round(max(0.0, min(1.0, marker)) * 100, 1) - 0.6}' y='0' "
            f"width='1.2' height='12'/>" if marker is not None else "")
    return (f"<svg class='mbar mbar-{tone}' viewBox='0 0 100 12' preserveAspectRatio='none' aria-hidden='true'>"
            f"<rect class='mbar-track' x='0' y='3' width='100' height='6' rx='3'/>"
            f"<rect class='mbar-fill' x='0' y='3' width='{width}' height='6' rx='3'/>{mark}</svg>")


def ring(rate):
    circumference = 2 * 3.1416 * 42
    done = round(circumference * max(0.0, min(1.0, rate)), 1)
    return (f"<svg class='mring' viewBox='0 0 100 100' role='img' aria-label='수행률 {round(rate * 100)}%'>"
            f"<circle class='mring-track' cx='50' cy='50' r='42'/>"
            f"<circle class='mring-fill' cx='50' cy='50' r='42' stroke-dasharray='{done} {circumference}' "
            f"transform='rotate(-90 50 50)'/>"
            f"<text x='50' y='50' class='mring-num'>{round(rate * 100)}%</text>"
            f"<text x='50' y='66' class='mring-cap'>수행률</text></svg>")


def sentence(parts, strong="hl"):
    return "".join(f"<span class='{strong}'>{escape(t)}</span>" if on else escape(t) for t, on in parts)


def html(text):
    st.markdown(text, unsafe_allow_html=True)


def header(title, back=None):
    points = rewards.balance(all_events(), store.load_spends(), student_id)
    ui.app_bar(title, badge=f"{points:,}P", on_back=back)


# ---------- ① 소비 미션 홈 ----------

def render_spend_home():
    run = sm.active_run(runs, student_id)
    ui.section("이번 주 미션")
    with ui.card("m-week"):
        if run:
            p = sm.progress(run, allowance, student_id, today)
            unit = "이하" if run["direction"] == "decrease" else "이상"
            target = float(run["target"])
            frac = (p["current"] / max(target, 1)) if run["direction"] == "increase" else \
                (p["current"] / max(float(run["baseline"]), 1))
            html(f"<div class='m-row'><span class='m-cap'>이번 주 미션</span>"
                 f"<span class='m-status'>진행 중 · D-{max(p['d_day'], 0)}</span></div>"
                 f"<div class='m-title'>{escape(run['title'])}</div>"
                 f"<div class='m-row m-small'><span>이번 주 {escape(sm.metric_text(run, p['current']))}</span>"
                 f"<b>목표 {escape(sm.metric_text(run, target))} {unit}</b></div>"
                 + bar(frac, marker=(target / max(float(run["baseline"]), 1)) if run["direction"] == "decrease"
                       else None)
                 + f"<div class='m-row m-small'><span>{escape(option_effect(run))}</span>"
                   f"<b class='m-point'>+{int(float(run['reward_points']))}P</b></div>")
            if run["parent_request"] == "REQUESTED":
                ui.muted("부모님께 매칭저축 승인을 요청했어요 (시안 · 실제 부모 앱과 연결하지 않아요).")
            if run["metric"] == "save_net":
                render_transfer()
            if sm.can_finish(run, today):
                st.button("주말 결과 보기", key="m-finish", type="primary", width="stretch",
                          on_click=finish, args=(run,))
            else:
                ui.muted("토요일부터 이번 주 결과를 볼 수 있어요.")
        else:
            html("<div class='m-title'>아직 이번 주 미션이 없어요</div>")
            ui.muted("Replay를 보고 이번 주 미션을 골라보세요.")

    trig = sm.triggers(student, allowance)
    if trig:
        t = trig[0]
        with st.container(key="m-dark-replay"):
            html(f"<div class='m-dark-cap'>⟲ AI Replay · 지난주 돌아보기</div>"
                 f"<div class='m-dark-title'>{sentence(t['parts'])}</div>"
                 "<div class='m-chips'>" + "".join(
                     f"<div class='m-chip'><span>{escape(n)}</span><b>{v:,}</b></div>" for n, v in t["chips"])
                 + "</div>")
            st.button("다르게 했다면? 시뮬레이션 해보기", key="m-to-sim", width="stretch",
                      on_click=go, args=("spend_sim",))
    else:
        with ui.card("m-good"):
            html("<div class='m-cap'>지난주 돌아보기</div>"
                 "<div class='m-title'>이번 주는 눈에 띄는 소비 패턴이 없어요</div>")
            for fact in sm.strengths(student, allowance):
                html(f"<div class='m-good-line'>✓ {escape(fact)}</div>")
            st.button("목표 시뮬레이션 해보기", key="m-to-sim", width="stretch", on_click=go, args=("spend_sim",))

    done = sm.completed_runs(runs, student_id)
    if done:
        ui.section("지난 미션")
        for r in done:
            with st.container(key=f"m-past-{r['run_id']}"):
                html(f"<div class='m-past'><div><div class='m-past-title'>{escape(r['title'])}</div>"
                     f"<div class='m-small'>수행률 {round(float(r['completion_rate']) * 100)}% · 결과 보기</div></div>"
                     f"<b class='m-point'>+{int(float(r['points'] or 0))}P</b></div>")
                st.button(f"{r['title']} 결과 보기", key=f"m-open-{r['run_id']}", on_click=go,
                          args=("spend_result",), kwargs={"run": r["run_id"]})


def option_effect(run):
    sim = sm.simulation(student, allowance)
    option = next((o for o in sim["options"] if o["label"] == run["option"]), None)
    return option["mission"]["effect"] if option else ""


def render_transfer():
    spend_left = envelope.balances(allowance, student_id)["SPEND"]
    if spend_left < 1000:
        return
    with st.expander("쓰기 봉투에서 모으기로 옮기기"):
        amount = st.number_input("옮길 돈 (원)", min_value=1000, max_value=int(spend_left // 1000 * 1000),
                                 value=min(3000, int(spend_left // 1000 * 1000)), step=1000, key="m-move")
        if st.button("모으기로 옮기기", key="m-move-go", width="stretch"):
            store.append_allowance(student_id, today, envelope.transfer_entries(int(amount)))
            st.toast(f"{won(int(amount))}을 모으기 봉투로 옮겼어요.", icon=":material/savings:")
            st.rerun()


def finish(run):
    store.update_mission_run(run["run_id"], sm.finish_values(run, allowance, student_id, today))
    go("spend_result", run=run["run_id"])


# ---------- ② 소비 시뮬레이션 ----------

def render_spend_sim():
    header("소비 시뮬레이션", back=lambda: go())
    sim = sm.simulation(student, allowance)
    goal = sim["goal"]
    scale = max(sim["deadline"] * 1.5, *(o["eta"] for o in sim["options"]),
                sim["current_eta"] or 0) or 1
    with ui.card("m-goal"):
        late = sim["current_eta"] is None or sim["current_eta"] > sim["deadline"]
        html(f"<div class='m-row m-small'><span>내 목표</span><span>지금 모은 돈 <b>{won(sim['saved'])}</b></span></div>"
             f"<div class='m-title'>{escape(goal['item'])} {goal['amount'] / 10000:g}만 원 · {sim['deadline']}개월 안에</div>"
             + bar((sim["current_eta"] or scale) / scale, marker=sim["deadline"] / scale, tone="warn" if late else "blue")
             + f"<div class='m-row m-tiny'><span>시작</span><b>목표 {sim['deadline']}개월</b>"
               f"<span>{scale:.0f}개월</span></div>"
             f"<div class='m-body'>{sentence(sm.eta_sentence(sim), 'warn' if late else 'hl-blue')}</div>")

    ui.section("다르게 해보면?")
    labels = [o["label"] for o in sim["options"]]
    default = next(o["label"] for o in sim["options"] if o["recommended"])
    if st.session_state.get("m-choice") not in labels:
        st.session_state["m-choice"] = default
    for o in sim["options"]:
        chosen = st.session_state["m-choice"] == o["label"]
        with st.container(key=f"m-opt-{'on' if chosen else 'off'}-{o['label']}"):
            tag = "<span class='m-rec'>추천</span>" if o["recommended"] else ""
            html(f"<div class='m-opt'><div class='m-opt-badge'>{o['label']}</div><div class='m-opt-text'>"
                 f"<div class='m-opt-title'>{escape(o['title'])} {tag}</div>"
                 f"<div class='m-small'>{escape(o['subtitle'])}</div></div>"
                 f"<div class='m-opt-eta'>{o['eta']}개월</div></div>"
                 + bar(o["eta"] / scale, marker=sim["deadline"] / scale))
            st.button(f"{o['label']}안 고르기", key=f"m-pick-{o['label']}", on_click=pick, args=(o["label"],),
                      help="선택됨" if chosen else None)

    ui.muted(f"지난 {sim['base_weeks']}주 모으기 기록으로 코드가 계산했어요 (주 평균 {won(sim['weekly_net'])}). "
             "C안은 부모님께 승인 요청이 가요 (시안).")
    choice = st.session_state["m-choice"]
    busy = sm.active_run(runs, student_id) is not None
    if busy:
        ui.muted("이번 주 미션이 이미 진행 중이에요. 주말 결과를 본 뒤 새 미션을 시작할 수 있어요.")
    st.button(f"{choice}안으로 이번 주 미션 시작", key="m-start", type="primary", width="stretch",
              disabled=busy, on_click=start, args=(next(o for o in sim["options"] if o["label"] == choice),))


def pick(label):
    st.session_state["m-choice"] = label


def start(option):
    store.append_mission_run(sm.start_row(student, option, today))
    st.session_state["mission_message"] = ("이번 주 미션을 시작했어요! 부모님께 승인 요청을 보냈어요 (시안)"
                                           if option["parent"] else "이번 주 미션을 시작했어요!")
    go()


# ---------- ③ 소비 미션 결과 ----------

def render_spend_result():
    header("미션 결과", back=lambda: go())
    run_id = st.query_params.get("run")
    match = runs[(runs["run_id"] == run_id) & (runs["student_id"] == student_id) & (runs["status"] == "completed")]
    if not len(match):
        st.info("결과를 찾지 못했어요.")
        return
    run = match.iloc[0].to_dict()
    r = sm.result(student, run, allowance)
    with ui.card("m-result"):
        html(f"<div class='m-result'>{ring(r['rate'])}<div>"
             f"<div class='m-cap'>1주 미션 · {escape(run['option'])}안</div>"
             f"<div class='m-title'>{escape(run['title'])}</div>"
             f"<div class='m-small'>{r['weeks_total']}주 중 {r['weeks_succeeded']}주 성공</div>"
             f"<div class='m-small'>이번 주 {escape(r['actual'])} / 목표 {escape(r['target'])}</div></div></div>")
    with ui.card("m-changed"):
        before, after = r["saving_rate"]
        html("<div class='m-cap'>달라진 행동</div><div class='m-pair'>"
             f"<div class='m-tile'><span>저축률</span><b>{before:.0%} → <em>{after:.0%}</em></b></div>"
             f"<div class='m-tile'><span>미션 지표</span><b>{escape(r['baseline'])} → <em>{escape(r['actual'])}</em></b></div>"
             "</div>")
        if r["eta"] is not None:
            delta = r["eta_delta_days"]
            note = (f"<span class='hl-green'>{delta}일 빨라짐</span>" if delta and delta > 0 else
                    f"<span class='warn'>{-delta}일 늦어짐</span>" if delta and delta < 0 else "변화 없음")
            html(f"<div class='m-row m-line'><span>목표 달성 예상</span><b>{r['eta']}개월 ({note})</b></div>")
    with st.container(key="m-dark-coach"):
        html(f"<div class='m-dark-cap'>AI 코치</div><div class='m-dark-body'>{escape(r['coach'])}</div>")
    granted = next((e["granted"] for e in all_events() if e["kind"] == "미션 결과"
                    and e["label"] == f"미션 결과: {run['title']}" and e["date"] == run["finished_date"]), 0)
    with st.container(key="m-reward"):
        if granted:
            html(f"<div class='m-reward'>미션 보상 +{granted}P 적립</div>")
        elif r["points"]:
            html(f"<div class='m-reward'>오늘 받을 수 있는 포인트(하루 {rewards.DAILY_CAP}P)를 다 받아서 이번엔 0P예요</div>")
        else:
            html("<div class='m-reward'>이번엔 포인트가 없어요. 벌점도 없어요!</div>")
    share, again = ui.columns(2, key="m-result-actions")
    with share:
        if st.button("부모님께 공유", key="m-share", width="stretch"):
            st.toast("부모님께 결과를 공유했어요 (시안 · 실제 전송 없음)", icon=":material/share:")
    with again:
        st.button("다시 시뮬레이션", key="m-again", type="primary", width="stretch", on_click=go, args=("spend_sim",))


# ---------- ④⑤⑥ 투자 미션 (잠김) ----------

def load_invest_data(student_id):
    """모의투자 주문 로그(viewed_info 포함)·과거 시세가 생기면 여기서 읽는다. 지금은 없음 → None.
    반환 형식: {"orders": DataFrame, "prices": {symbol: [(date, close)]}, "cash": int, "insight": {...}}"""
    return None


def invest_locked():
    return not config.INVEST_MISSION_ENABLED or load_invest_data(student_id) is None


def render_invest_home():
    locked = invest_locked()
    if locked:
        st.info("🔒 투자 미션은 준비 중이에요. 모의투자 주문 기록과 과거 시세 데이터가 생기면 열려요. "
                "지금은 화면 모양만 미리 볼 수 있어요.")
    with ui.card("m-unlock"):
        html("<div class='m-row'><span class='m-cap'>Skill Unlock</span>"
             "<span class='m-small'><b class='hl-blue'>Lv.2 Practice</b> → Lv.3 Prove</span></div>")
        tiles = invest_mission.skill_unlock(0, 0, 0, 0)
        html("<div class='m-pair m-pair-wrap'>" + "".join(
            f"<div class='m-tile m-tile-{'ok' if (not locked and c['met']) else 'todo'}'><b>{c['label']} "
            f"{'—' if locked else c['current']}</b><span>기준 {c['target']}{c['unit']} "
            f"{'이상' if c['key'] in ('weeks', 'journal') else '이하'}</span></div>" for c in tiles) + "</div>")
    with ui.card("m-invest-week"):
        html("<div class='m-row'><span class='m-cap'>이번 주 미션</span><span class='m-status m-status-off'>준비 중</span></div>"
             "<div class='m-title'>데이터가 생기면 여기에 투자 미션이 보여요</div>" + bar(0, marker=0.5, tone="warn")
             + "<div class='m-row m-small'><span>현재 최대 비중 —</span><b>목표 50% 이하</b></div>")
    with st.container(key="m-dark-invest"):
        html("<div class='m-dark-cap'>⟲ AI Replay · 급등 직후 매수</div>"
             "<div class='m-dark-title'>모의투자 기록이 쌓이면 급등 추격·몰빵 같은 순간을 같이 돌아봐요.</div>")
        st.button("그때로 돌아가 보기", key="m-to-invest-replay", width="stretch", disabled=locked,
                  on_click=go, args=("invest_replay",))


def render_invest_replay(data):
    """⑤ 투자 Replay. data: load_invest_data()의 insight (symbol, closes, buy_index, jump_pct, return_pct,
    days, viewed_info, weight_pct)."""
    header("투자 돌아보기", back=lambda: go())
    ins = data["insight"]
    closes = ins["closes"]
    low, high = min(closes), max(closes)
    pts = " ".join(f"{i / (len(closes) - 1) * 100:.1f},{(1 - (c - low) / ((high - low) or 1)) * 40 + 5:.1f}"
                   for i, c in enumerate(closes))
    bx = ins["buy_index"] / (len(closes) - 1) * 100
    by = (1 - (closes[ins["buy_index"]] - low) / ((high - low) or 1)) * 40 + 5
    with ui.card("m-chart"):
        html(f"<div class='m-row'><b>{escape(ins['symbol'])} <span class='m-small'>가상 종목</span></b>"
             f"<span class='warn'>매수 후 {ins['return_pct']}%</span></div>"
             f"<svg class='mline' viewBox='0 0 100 50' preserveAspectRatio='none'><polyline points='{pts}'/>"
             f"<circle cx='{bx:.1f}' cy='{by:.1f}' r='2'/></svg>"
             "<div class='m-pair'>"
             f"<div class='m-tile'><span>매수 전 본 정보</span><b>{'있음' if ins['viewed_info'] else '없음'}</b></div>"
             f"<div class='m-tile'><span>투자한 비중</span><b>가상자산의 {ins['weight_pct']}%</b></div></div>")
    ui.section("왜 이 종목을 샀나요?")
    keys = list(invest_mission.ANSWER_CONCEPTS)
    answer = st.radio("이유", keys, format_func=lambda k: invest_mission.ANSWER_CONCEPTS[k][0],
                      horizontal=True, label_visibility="collapsed", key="m-why")
    concept = store.load_concepts()[invest_mission.ANSWER_CONCEPTS[answer][1]]
    with st.container(key="m-dark-lesson"):
        html(f"<div class='m-dark-cap'>1분 레슨</div><div class='m-dark-title hl'>{escape(concept['name_ko'])}</div>"
             f"<div class='m-dark-body'>{escape(concept['sections']['한 줄 정의'])}</div>")
    st.button("다르게 샀다면? 시뮬레이션 보기", key="m-to-invest-sim", type="primary", width="stretch",
              on_click=go, args=("invest_sim",))


def render_invest_sim(data):
    """⑥ 투자 시뮬레이션. ⚠️ 수익률 비교 → 규칙 4와 부딪힘. 켜기 전에 표시 방식 결정 (docs/MISSION_TAB.md)."""
    header("투자 시뮬레이션", back=lambda: go())
    compare = invest_mission.replay_compare(data["prices"], data["insight"]["symbol_key"],
                                            data["insight"]["buy_day"], data.get("peers"))
    worst = max(abs(c["return_pct"]) for c in compare) or 1
    with ui.card("m-compare"):
        html("<div class='m-cap'>같은 기간 실제 시세로 다시 재생했어요</div>"
             f"<div class='m-title'>이렇게 샀다면 {invest_mission.REPLAY_DAYS}일 뒤 결과는?</div>")
        for c in compare:
            html(f"<div class='m-row'><span>{escape(c['label'])}{' <b class=warn>내 선택</b>' if c.get('mine') else ''}"
                 f"</span><b>{c['return_pct']}%</b></div>"
                 + bar(abs(c["return_pct"]) / worst, tone="mine" if c.get("mine") else "blue"))
    ui.section("다음 주에 해볼 미션을 골라요")
    pick_id = st.radio("미션", [m["id"] for m in invest_mission.MISSION_OPTIONS], label_visibility="collapsed",
                       format_func=lambda i: next(f"{m['title']} · +{m['reward_points']}P"
                                                  for m in invest_mission.MISSION_OPTIONS if m["id"] == i),
                       key="m-invest-pick")
    ui.muted("미션을 완료하면 Lv.3 조건 '충동거래 1회 이하'에 반영돼요.")
    st.button("이 미션으로 시작하기", key="m-invest-start", type="primary", width="stretch",
              on_click=go, args=(None,))
    return pick_id


# ---------- 화면 고르기 ----------

if st.session_state.get("mission_message"):
    st.toast(st.session_state.pop("mission_message"), icon=":material/flag:")
view = st.query_params.get("view")
if view == "spend_sim":
    render_spend_sim()
elif view == "spend_result":
    render_spend_result()
elif view in ("invest_replay", "invest_sim") and not invest_locked():
    data = load_invest_data(student_id)
    (render_invest_replay if view == "invest_replay" else render_invest_sim)(data)
else:
    header("미션")
    saved = st.session_state.get("mission_track_saved", "spend")
    track = st.segmented_control("미션 갈래", list(TRACKS), format_func=TRACKS.get, default=saved,
                                 key="mission-track", label_visibility="collapsed", width="stretch")
    track = track or saved
    st.session_state["mission_track_saved"] = track
    (render_spend_home if track == "spend" else render_invest_home)()
