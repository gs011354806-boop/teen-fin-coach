"""실전 준비 기준 (criteria/teengrow_ready/READY_SPEC.md) — 수익률이 아니라 '어떻게 투자했나'로
실전 동의 요청 자격을 정한다. 계산은 모두 이 파일의 순수 함수 (LLM·Streamlit 없음).

기준 5가지를 모두 채우면 부모님께 동의를 요청할 수 있다. 실전 허락은 부모 동의로 정해진다.
기준 값은 이 파일 맨 위 상수에만 있다. 부모님 설정 화면·API로 바꿀 수 없다 (evaluate에 기준 인자가 없다).
6개월(183일) 넘게 앱을 쓰지 않았다면 실전 전에 준비 퀴즈만 다시 통과해야 한다.
한도·종목 범위와는 상관없다. 연습 거래만 세고, 손익은 '손실 난 거래가 있었는지' 한 가지에만 쓴다.
아래쪽 '앱 기록 연결'이 trades.csv·data/students/ready.json을 이 파일의 기록 모양으로 바꾼다.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

# ── 기준 값 (앱 고정. 부모 설정으로 바꾸지 않는다) ─────────────────
PRACTICE_MIN_DAYS = 28
PRACTICE_MIN_WEEKS = 3
TRADES_MIN = 10
SELLS_MIN = 3
DAILY_COUNT_CAP = 2
JOURNALS_MIN = 8
JOURNAL_MIN_CHARS = 10
JOURNAL_DUP_RATIO = 0.85
REFLECTIONS_MIN = 2
REFLECTION_MIN_CHARS = 10
QUIZ_TOTAL = 10
QUIZ_PASS = 8
RECHECK_AFTER_DAYS = 183


# ── 기록 ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Trade:
    id: str
    at: datetime
    code: str
    side: str                 # BUY | SELL
    pnl: float | None = None  # 팔기의 손익(원). 기준에는 '손실 거래가 있었는지'만 쓴다


@dataclass(frozen=True)
class Journal:
    at: datetime
    text: str
    trade_id: str | None = None


@dataclass(frozen=True)
class Reflection:
    at: datetime
    trade_id: str
    kind: str                 # loss | regret | gain
    answers: tuple[str, str, str]   # 내 예상 / 실제로는 / 다음엔


@dataclass(frozen=True)
class QuizAttempt:
    at: datetime
    score: int


@dataclass(frozen=True)
class ReadyState:
    """사용자별 저장 값."""
    qualified_at: datetime | None = None       # 5가지를 처음 모두 채운 시각
    last_active_at: datetime | None = None
    recheck_since: datetime | None = None      # 6개월 휴면으로 퀴즈 재확인이 필요해진 시각


def _plain(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", s or "")


# ── 2. 거래 세기 ─────────────────────────────────────────────
@dataclass(frozen=True)
class CountedTrade:
    day: date
    at: datetime
    code: str
    kind: str                 # BUY | SELL | ROUNDTRIP


def count_trades(trades: list[Trade]) -> list[CountedTrade]:
    """같은 날 같은 종목: 사고팔았으면 ROUNDTRIP 1회, 아니면 그 방향 1회. 하루 최대 2회(먼저 한 것)."""
    groups: dict[tuple[date, str], list[Trade]] = {}
    for t in sorted(trades, key=lambda x: x.at):
        groups.setdefault((t.at.date(), t.code), []).append(t)
    events = []
    for (day, code), ts in groups.items():
        sides = {t.side for t in ts}
        kind = "ROUNDTRIP" if sides == {"BUY", "SELL"} else ts[0].side
        events.append(CountedTrade(day, ts[0].at, code, kind))
    events.sort(key=lambda e: e.at)
    out, per_day = [], {}
    for e in events:
        if per_day.get(e.day, 0) < DAILY_COUNT_CAP:
            per_day[e.day] = per_day.get(e.day, 0) + 1
            out.append(e)
    return out


# ── 3. 일지 세기 ─────────────────────────────────────────────
def count_journals(journals: list[Journal]) -> int:
    kept: list[str] = []
    for j in sorted(journals, key=lambda x: x.at):
        p = _plain(j.text)
        if len(p) < JOURNAL_MIN_CHARS:
            continue
        if any(p == k or SequenceMatcher(None, p, k).ratio() >= JOURNAL_DUP_RATIO for k in kept):
            continue
        kept.append(p)
    return len(kept)


# ── 4. 돌아보기 ──────────────────────────────────────────────
def reflection_valid(r: Reflection) -> bool:
    return len(r.answers) == 3 and all(len(_plain(a)) >= REFLECTION_MIN_CHARS for a in r.answers)


def count_reflections(refls: list[Reflection], trades: list[Trade]) -> tuple[int, bool]:
    """(인정된 개수, 손실/아쉬움 조건 충족). 같은 거래는 1번만."""
    seen, ok = set(), []
    for r in sorted(refls, key=lambda x: x.at):
        if reflection_valid(r) and r.trade_id not in seen:
            seen.add(r.trade_id)
            ok.append(r)
    had_loss = any(t.side == "SELL" and (t.pnl or 0) < 0 for t in trades)
    need = {"loss"} if had_loss else {"loss", "regret"}
    return len(ok), any(r.kind in need for r in ok)


# ── 평가 ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Item:
    key: str
    name: str
    done: bool
    parts: tuple[tuple[str, int, int], ...]     # (라벨, 현재, 목표)
    hint: str


@dataclass(frozen=True)
class Readiness:
    items: tuple[Item, ...]
    needs_recheck: bool

    @property
    def done_count(self) -> int:
        return sum(i.done for i in self.items)

    @property
    def all_done(self) -> bool:
        return all(i.done for i in self.items)

    @property
    def can_request_consent(self) -> bool:
        return self.all_done and not self.needs_recheck

    def remaining(self) -> list[str]:
        out = []
        for i in self.items:
            for label, cur, goal in i.parts:
                if cur < goal:
                    out.append(f"{label} {goal - cur}")
        return out


def evaluate(now: datetime, trades: list[Trade], journals: list[Journal], refls: list[Reflection],
             quiz: list[QuizAttempt], state: ReadyState = ReadyState()) -> Readiness:
    counted = count_trades(trades)
    first = counted[0].day if counted else None
    days = (now.date() - first).days if first else 0
    weeks = len({e.day.isocalendar()[:2] for e in counted})
    sells = sum(e.kind == "SELL" for e in counted)
    n_j = count_journals(journals)
    n_r, loss_ok = count_reflections(refls, trades)
    recheck = needs_recheck(state, quiz)
    since = state.recheck_since if recheck else None
    best = max([a.score for a in quiz if since is None or a.at >= since], default=0)
    quiz_done = best >= QUIZ_PASS and not recheck

    items = (
        Item("period", "연습 기간", days >= PRACTICE_MIN_DAYS and weeks >= PRACTICE_MIN_WEEKS,
             (("첫 거래 후 일수", days, PRACTICE_MIN_DAYS), ("거래한 주", weeks, PRACTICE_MIN_WEEKS)),
             "첫 연습 거래 후 4주, 그중 서로 다른 3주에 거래해요."),
        Item("trades", "연습 거래", len(counted) >= TRADES_MIN and sells >= SELLS_MIN,
             (("인정된 거래", len(counted), TRADES_MIN), ("그중 팔기", sells, SELLS_MIN)),
             "하루 2회까지만 인정해요. 같은 날 같은 종목을 사고팔면 1회예요."),
        Item("journals", "근거 쓴 일지", n_j >= JOURNALS_MIN,
             (("근거 쓴 일지", n_j, JOURNALS_MIN),),
             "근거를 10자 이상 쓴 일지만 세요. 비슷한 문장은 한 번만."),
        Item("reflections", "돌아보기 리포트", n_r >= REFLECTIONS_MIN and loss_ok,
             (("돌아보기", n_r, REFLECTIONS_MIN), ("손실·아쉬운 거래 돌아보기", int(loss_ok), 1)),
             "한 번은 손실 난 거래(없으면 가장 아쉬운 거래)를 돌아봐요."),
        Item("quiz", "실전 준비 퀴즈", quiz_done,
             (("최고 점수", best, QUIZ_PASS),),
             "오랜만이에요. 실전 전에 준비 퀴즈를 다시 풀어요." if recheck else "10문제 중 8개를 맞히면 통과예요."),
    )
    return Readiness(items, recheck)


# ── 6개월 휴면 재확인 ─────────────────────────────────────────
def on_app_open(state: ReadyState, now: datetime) -> ReadyState:
    """앱을 열 때마다 호출. 이미 자격을 얻은 사람이 183일 넘게 쉬었다면 재확인을 건다."""
    s = state
    if s.qualified_at and s.last_active_at and now - s.last_active_at > timedelta(days=RECHECK_AFTER_DAYS) \
            and s.recheck_since is None:
        s = replace(s, recheck_since=now)
    return replace(s, last_active_at=now)


def needs_recheck(state: ReadyState, quiz: list[QuizAttempt]) -> bool:
    if state.recheck_since is None:
        return False
    return not any(a.at >= state.recheck_since and a.score >= QUIZ_PASS for a in quiz)


def after_quiz(state: ReadyState, quiz: list[QuizAttempt]) -> ReadyState:
    """퀴즈를 낸 뒤 호출. 재확인을 통과했으면 해제."""
    if state.recheck_since and not needs_recheck(state, quiz):
        return replace(state, recheck_since=None)
    return state


def mark_qualified(state: ReadyState, r: Readiness, now: datetime) -> ReadyState:
    if r.all_done and not r.needs_recheck and state.qualified_at is None:
        return replace(state, qualified_at=now)
    return state


def can_enter_real(state: ReadyState, quiz: list[QuizAttempt], consent_status: str) -> str | None:
    """실전 입구(REAL_SAFETY_SPEC의 tap_real 앞)에서 호출. 막히면 이유 코드."""
    if state.qualified_at is None:
        return "NOT_READY"
    if needs_recheck(state, quiz):
        return "RECHECK_QUIZ"
    if consent_status != "ACTIVE":
        return "NO_CONSENT"
    return None


# ── 실전 준비 퀴즈 ────────────────────────────────────────────
@dataclass(frozen=True)
class Question:
    id: str
    topic: str
    text: str
    options: tuple[str, ...]
    answer: int
    explain: str


QUESTIONS: tuple[Question, ...] = (
    Question("loss", "원금 손실", "실전에서 산 주식의 가격이 내려가면 어떻게 될까요?",
             ("넣은 돈보다 적게 돌려받을 수 있어요", "앱이 손실을 채워 줘요", "팔기 전까지는 절대 손해가 아니에요", "다음 날 자동으로 원래 가격이 돼요"),
             0, "실전 투자는 원금이 보장되지 않아요."),
    Question("diversify", "분산", "'달걀을 한 바구니에 담지 말라'는 투자에서 무슨 뜻일까요?",
             ("여러 곳에 나눠 투자해 한 번에 크게 잃는 걸 줄여요", "한 종목에 모두 넣어야 크게 벌어요", "주식은 하루에 한 번만 사요", "현금은 가지고 있지 말아요"),
             0, "나눠 담으면 한 종목이 크게 내려도 전체 손실이 작아져요."),
    Question("fee", "수수료·세금", "주식을 사고팔 때 드는 비용으로 맞는 것은?",
             ("수수료(그리고 팔 때 세금)", "비용은 전혀 없어요", "살 때만 세금이 있어요", "앱 포인트로 내요"),
             0, "자주 사고팔수록 수수료가 쌓여요."),
    Question("fomo", "급등주", "오늘 30% 오른 종목을 친구들이 다 샀대요. 가장 좋은 행동은?",
             ("오른 이유를 먼저 찾아보고 급하게 따라 사지 않아요", "지금 바로 최대한 많이 사요", "친구에게 대신 사 달라고 해요", "내일 더 오를 테니 빌려서 사요"),
             0, "많이 오른 날 따라 사면 비싸게 살 위험이 커요."),
    Question("scam", "투자 사기", "'무조건 오르는 종목 알려줄게' 단체 대화방 초대가 왔어요.",
             ("투자 사기일 수 있어 응하지 않고 부모님께 알려요", "들어가서 종목을 받아요", "돈을 먼저 보내면 더 좋은 정보를 줘요", "친구도 초대해요"),
             0, "확실한 수익을 약속하는 곳은 사기일 가능성이 커요."),
    Question("limit", "실전 한도", "이번 달 한도 50,000원 중 30,000원어치를 사고, 그중 10,000원어치를 팔았어요. 이번 달에 더 살 수 있는 돈은?",
             ("30,000원 (판 돈만큼 다시 생겨요)", "20,000원", "40,000원", "50,000원 (새로 시작돼요)"),
             1, "판 돈은 한도를 다시 채우지 않아요. 50,000 − 30,000 = 20,000원."),
    Question("reason", "근거 쓰기", "실전에서 사는 이유를 꼭 써야 주문되는 이유는?",
             ("충동적으로 사는 걸 막고 나중에 돌아보려고", "부모님께 혼나지 않으려고", "포인트를 더 받으려고", "증권사가 요구해서"),
             0, "이유를 쓰면 한 번 더 생각하게 되고, 돌아볼 기록이 남아요."),
    Question("price", "시세", "지금 teengrow 실전 화면의 가격은 어떤 가격일까요?",
             ("전날 종가예요 (실시간이 아니에요)", "1초마다 바뀌는 실시간 가격이에요", "다음 날 예상 가격이에요", "친구들이 산 평균 가격이에요"),
             0, "공공데이터 시세는 전 영업일 종가라 오늘 실제 가격과 다를 수 있어요."),
    Question("margin", "미수·신용", "빌린 돈으로 주식을 사는 미수·신용거래는 teengrow에서?",
             ("할 수 없어요", "한도 안에서 할 수 있어요", "부모님이 허락하면 할 수 있어요", "레벨이 오르면 할 수 있어요"),
             0, "빌린 돈으로 투자하면 잃을 수 있는 돈이 넣은 돈보다 커질 수 있어서 막아 둬요."),
    Question("after_loss", "손실 뒤", "실전에서 손실이 났어요. 가장 좋은 행동은?",
             ("처음 산 이유가 아직 맞는지 돌아보고 기록해요", "만회하려고 바로 더 많이 사요", "앱을 지우고 잊어요", "다른 친구 종목을 따라 사요"),
             0, "급하게 만회하려 하면 손실이 더 커지기 쉬워요."),
)


def quiz_round(attempt_no: int, user_seed: int = 0) -> list[tuple[Question, list[int]]]:
    """문제 순서와 보기 순서를 섞는다. 반환: [(문제, 보기 순서 index 목록)]. 첫 시도도 섞는다."""
    rng = random.Random(user_seed * 1000 + attempt_no)
    qs = list(QUESTIONS)
    rng.shuffle(qs)
    out = []
    for q in qs:
        order = list(range(len(q.options)))
        rng.shuffle(order)
        out.append((q, order))
    return out


def grade(round_: list[tuple[Question, list[int]]], picks: list[int]) -> tuple[int, list[str]]:
    """picks: 화면에 보인 순서 기준으로 고른 칸. 반환: (점수, 틀린 주제)."""
    score, wrong = 0, []
    for (q, order), p in zip(round_, picks):
        if order[p] == q.answer:
            score += 1
        else:
            wrong.append(q.topic)
    return score, wrong


# ── 부모님께 가는 리포트 ──────────────────────────────────────
def build_report(now: datetime, r: Readiness, trades: list[Trade], journals: list[Journal],
                 refls: list[Reflection], quiz: list[QuizAttempt], wrong_topics: list[str]) -> dict:
    """리포트에는 수익률·종목을 넣지 않는다."""
    if not r.can_request_consent:
        raise ValueError("기준을 모두 채워야 리포트를 만들 수 있어요")
    counted = count_trades(trades)
    best = max(quiz, key=lambda a: (a.score, a.at))
    valid_refls = [x for x in sorted(refls, key=lambda x: x.at) if reflection_valid(x)]
    return {
        "created_at": now.isoformat(),
        "first_trade": counted[0].day.isoformat(),
        "days": (now.date() - counted[0].day).days,
        "weeks": len({e.day.isocalendar()[:2] for e in counted}),
        "trades": len(counted),
        "sells": sum(e.kind == "SELL" for e in counted),
        "journals": count_journals(journals),
        "reflections": len(valid_refls),
        "quiz_best": best.score, "quiz_at": best.at.date().isoformat(), "quiz_wrong_topics": wrong_topics,
        "quotes": [j.text for j in sorted(journals, key=lambda x: x.at)[-1:]] + [x.answers[2] for x in valid_refls[:2]],
    }


# ── 앱 기록 연결 (trades.csv · real_trades.csv · data/students/ready.json) ──────────
# 연습 거래 = 연습 모드의 가상 거래 (연습용 시세 trades.csv + 실제 시세 연습 real_trades.csv). 실전 계좌 주문은 세지 않는다.
# trades.csv에는 날짜만 있어서 같은 날 거래의 순서는 파일 순서로 정한다 (1초씩 띄운 시각).

def practice_trades(tables, student_id):
    """[(trade_id, date, ticker, side, qty, price, journal)] → (list[Trade], list[Journal], {trade_id: 정보}).
    팔기의 손익은 이동평균 단가로 계산한다 (손실 여부와 돌아보기 화면 표시에만 쓴다)."""
    rows = []
    for table in tables:
        if table is None or not len(table):
            continue
        mine = table[table["student_id"] == student_id]
        rows += [r for r in mine.to_dict("records")]
    rows.sort(key=lambda r: r["date"])  # 같은 날은 파일 순서 (sort는 안정 정렬)
    trades, journals, info = [], [], {}
    held: dict[str, tuple[float, float]] = {}   # 종목 → (수량, 평균 단가)
    for n, r in enumerate(rows):
        at = datetime.fromisoformat(str(r["date"])[:10]) + timedelta(seconds=n)
        qty, price = float(r["qty"]), float(r["price"])
        q0, avg = held.get(r["ticker"], (0.0, 0.0))
        pnl = None
        if r["side"] == "BUY":
            held[r["ticker"]] = (q0 + qty, (q0 * avg + qty * price) / (q0 + qty) if q0 + qty else 0.0)
        else:
            pnl = round((price - avg) * qty) if q0 else 0
            held[r["ticker"]] = (max(0.0, q0 - qty), avg)
        tid = str(r["trade_id"])
        trades.append(Trade(tid, at, str(r["ticker"]), r["side"], pnl))
        text = str(r.get("journal") or "").strip()
        if text:
            journals.append(Journal(at, text, tid))
        info[tid] = {"id": tid, "date": str(r["date"])[:10], "ticker": str(r["ticker"]), "side": r["side"],
                     "qty": qty, "price": price, "pnl": pnl, "cost": avg * qty if r["side"] == "SELL" else None,
                     "journal": text}
    return trades, journals, info


def _dt(value):
    return datetime.fromisoformat(value) if value else None


def _iso(value):
    return value.isoformat(timespec="seconds") if value else None


def state_from(doc) -> ReadyState:
    s = (doc or {}).get("state") or {}
    return ReadyState(_dt(s.get("qualified_at")), _dt(s.get("last_active_at")), _dt(s.get("recheck_since")))


def state_to(doc, state: ReadyState):
    doc["state"] = {"qualified_at": _iso(state.qualified_at), "last_active_at": _iso(state.last_active_at),
                    "recheck_since": _iso(state.recheck_since)}
    return doc


def reflections_from(doc) -> list[Reflection]:
    return [Reflection(_dt(r["at"]), r["trade_id"], r["kind"], tuple(r["answers"])) for r in (doc or {}).get("reflections", [])]


def quiz_from(doc) -> list[QuizAttempt]:
    return [QuizAttempt(_dt(q["at"]), int(q["score"])) for q in (doc or {}).get("quiz", [])]


def add_reflection(doc, at: datetime, trade_id, kind, answers):
    """저장 전에 확인: 세 칸 모두 10자 이상, 같은 거래는 한 번만. 저장했으면 True."""
    r = Reflection(at, trade_id, kind, tuple(a.strip() for a in answers))
    if not reflection_valid(r) or any(x["trade_id"] == trade_id for x in doc.get("reflections", [])):
        return False
    doc.setdefault("reflections", []).append({"at": _iso(at), "trade_id": trade_id, "kind": kind,
                                              "answers": list(r.answers)})
    return True


def add_quiz(doc, at: datetime, score, wrong_topics):
    doc.setdefault("quiz", []).append({"at": _iso(at), "score": int(score), "wrong": list(wrong_topics)})


def last_wrong_topics(doc):
    """가장 높은 점수(같으면 최근) 시도의 틀린 주제 — 부모 리포트에 남긴다."""
    tries = (doc or {}).get("quiz", [])
    if not tries:
        return []
    return max(tries, key=lambda q: (q["score"], q["at"])).get("wrong", [])


def grandfather(state: ReadyState, consent) -> ReadyState:
    """이 기준이 생기기 전에 이미 부모 동의를 받은 사람: 동의한 시각을 자격 시각으로 본다 (실전에서 갑자기 잠기지 않게)."""
    if state.qualified_at is None and consent.get("status") in ("ACTIVE", "REVOKED") and consent.get("decided_at"):
        return replace(state, qualified_at=_dt(consent["decided_at"]))
    return state


def reflection_kind(pnl, had_loss, regret_pick=False):
    """손실 난 팔기 → loss. 손실 거래가 한 번도 없으면 학생이 고른 '가장 아쉬운 거래' → regret. 나머지 → gain."""
    if pnl is not None and pnl < 0:
        return "loss"
    return "regret" if (not had_loss and regret_pick) else "gain"


def stage_of(r: Readiness) -> str:
    """진행 화면 상태: early(막 시작) · almost(거의 다) · ready(완료) · recheck(6개월 재확인)."""
    if r.needs_recheck:
        return "recheck"
    if r.can_request_consent:
        return "ready"
    return "almost" if r.done_count >= 2 else "early"


def user_seed(student_id) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(str(student_id)))
