"""오늘의 뉴스 (하루 3개 · 카드 4장 · 퀴즈) — NEWS_MARKET_SPEC.md 5·6·7·9장. LLM 호출 금지.

- 뉴스 출처는 22번과 같은 정책브리핑 정책뉴스 API (engine/news.fetch, 같은 DATA_GO_KR_KEY). 금융 관련 · 공공누리 1유형만.
- 고르기: 최근 NEWS_LOOKBACK_DAYS일 → 제목 겹침 0.6 이상은 같은 기사 → 키워드 점수 순, 대표 카테고리가 서로 다르게 3개.
  최근 7일 안에 이미 쓴 기사는 빼고, 키워드가 하나도 안 맞는 기사는 후보가 모자랄 때만.
- 카드 문장은 기존 카드뉴스 생성기(22번)와 같은 규칙의 AI 프롬프트(news_daily)가 쓰고, 숫자·길이·금지 표현은 여기서 검사한다.
  4번 카드 '오늘의 단어'는 content/concepts의 개념 이름과 한 줄 정의만 쓴다 (CLAUDE.md 규칙 8). 없으면 '콘텐츠 없음'.
- 퀴즈 유형은 코드가 정한다: 1번 내용 확인 / 2번 단어 / 3번 나라면?. 단어 문제는 개념 파일의 확인 문제를 쓴다.
  주가·등락을 맞히는 문제는 만들지 않는다.
- 그림은 키워드 일러스트(assets/news_illustrations)만. 실제 뉴스 사진을 내려받지 않는다.
- 뉴스 속 종목: 기사에 이름이 실제로 나온 회사만 (긴 이름 먼저, 최대 3개). 투자 권유 표현이 든 기사는 계속 거른다.
- 하루치는 3개가 모두 준비됐을 때만 data/real/daily_news/news_<날짜>.json에 통째로 저장한다 (부분 저장 금지).
"""

import base64
import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd

import config
from engine import news, quotes

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "real" / "daily_news"
KEYWORD_MAP_PATH = ROOT / "assets" / "keyword_map.json"
IMAGE_DIR = ROOT / "assets" / "news_illustrations"
SOURCE = news.SOURCE

QUIZ_TYPES = ["content", "word", "apply"]
QUIZ_TYPE_LABELS = {"content": "내용 확인", "word": "단어", "apply": "나라면?"}
CARD_TAGS = ["1 · 무슨 일?", "2 · 왜 중요해?", "3 · 나랑 무슨 상관?", "4 · 오늘의 단어"]
TITLE_WEIGHT, BODY_WEIGHT, MAX_CATEGORIES = 3, 1, 2
TITLE_MAX, BODY_MAX, TIP_MAX, LIST_MAX, EXPLAIN_MAX = 26, 70, 40, 70, 70
# 주가·등락을 맞히게 하는 퀴즈 (만들지 않는다)
PRICE_QUIZ_WORDS = ["주가가 오를", "주가가 내릴", "주가는", "오를까", "내릴까", "떨어질까", "상승할까", "하락할까", "등락"]
IMAGE_CAPTION = "키워드 이미지 · 실제 뉴스 사진 아님"


class DailyNewsError(Exception):
    pass


# ---------- 6장 키워드 이미지 ----------

@lru_cache(maxsize=2)
def load_keyword_map(path=None):
    return json.loads(Path(path or KEYWORD_MAP_PATH).read_text(encoding="utf-8"))


def score_categories(title, body, kmap):
    """[(카테고리, 점수, 맞은 키워드)] 점수 내림차순 (같으면 keyword_map 순서). 제목 3점, 본문 1점."""
    order = list(kmap["categories"])
    rows = []
    for cat, info in kmap["categories"].items():
        hits, score = [], 0
        for kw in info["keywords"]:
            t, b = title.count(kw), body.count(kw)
            if t or b:
                hits.append(kw)
                score += TITLE_WEIGHT * t + BODY_WEIGHT * b
        if score:
            rows.append((cat, score, hits))
    rows.sort(key=lambda r: (-r[1], order.index(r[0])))
    return rows


def pick_categories(title, body, kmap):
    return [c for c, _, _ in score_categories(title, body, kmap)[:MAX_CATEGORIES]] or [kmap["fallback"]]


def top_keywords(title, body, kmap, n=2):
    """해시태그 2개: 제목에 나온 키워드 먼저."""
    found = []
    for _, _, hits in score_categories(title, body, kmap):
        for kw in sorted(hits, key=lambda k: (k not in title, -len(k))):
            if kw not in found:
                found.append(kw)
    return found[:n]


def slide_categories(cats, slides=4):
    """카드 1·3번 = 1순위 그림, 2·4번 = 2순위 그림 (없으면 1순위)."""
    second = cats[1] if len(cats) > 1 else cats[0]
    return [cats[0] if i % 2 == 0 else second for i in range(slides)]


def diversify(day_cats):
    """같은 날 대표 그림이 겹치면 뒤 뉴스는 2순위를 대표로 올린다."""
    used, out = set(), []
    for cats in day_cats:
        cats = list(cats)
        if cats[0] in used and len(cats) > 1 and cats[1] not in used:
            cats[0], cats[1] = cats[1], cats[0]
        used.add(cats[0])
        out.append(cats)
    return out


def category_label(cat, kmap=None):
    return (kmap or load_keyword_map())["categories"].get(cat, {}).get("label", "경제 일반")


def alt_text(cat, kmap=None):
    return f"{category_label(cat, kmap)} 키워드 일러스트 (실제 뉴스 사진 아님)"


@lru_cache(maxsize=32)
def image_uri(cat):
    """SVG를 data URI로 (Streamlit에서 st.image보다 확실하다). 파일이 없으면 general."""
    path = IMAGE_DIR / f"{cat}.svg"
    if not path.exists():
        path = IMAGE_DIR / "general.svg"
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# ---------- 5장 고르기 · 7장 뉴스 속 종목 ----------

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def similar(a, b):
    ta, tb = set(_TOKEN.findall(a)), set(_TOKEN.findall(b))
    return 0.0 if not ta or not tb else len(ta & tb) / len(ta | tb)


def dedupe(items, threshold=None):
    """제목이 비슷한 기사는 가장 최근 1건만."""
    threshold = config.NEWS_TITLE_SIMILAR if threshold is None else threshold
    kept = []
    for it in sorted(items, key=lambda x: x["published_at"], reverse=True):
        if all(similar(it["title"], k["title"]) < threshold for k in kept):
            kept.append(it)
    return kept


def pick_daily(items, kmap, n=None, used_ids=()):
    """중복 제거 → 키워드 점수 높은 순 → 대표 카테고리가 겹치지 않게 n개 (모자라면 나머지에서)."""
    n = n or config.DAILY_NEWS_COUNT
    pool = [i for i in dedupe(items) if i["id"] not in set(used_ids)]
    scored = []
    for it in pool:
        ranked = score_categories(it["title"], it["body"], kmap)
        top = ranked[0][0] if ranked else kmap["fallback"]
        scored.append((sum(s for _, s, _ in ranked), it.get("teen_score", 0), it["published_at"], top, it))
    scored.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    picked, cats = [], set()
    for total, _, _, top, it in scored:
        if total > 0 and top not in cats:
            picked.append(it)
            cats.add(top)
        if len(picked) == n:
            return picked
    for *_, it in scored:
        if it not in picked:
            picked.append(it)
        if len(picked) == n:
            break
    return picked


def stock_master():
    """{종목명: 종목코드} — 실제 시세 관심 목록(15종목)과 시나리오 종목. 전 종목 수집은 하지 않는다."""
    from engine import store
    master = {name: code for code, name in quotes.load_watchlist().items()}
    master.update({name: code for code, name in store.load_ticker_names().items()})
    return master


def find_mentioned_stocks(text, master, limit=3):
    """기사에 이름이 실제로 나온 회사만 (업종 추천 아님). 긴 이름부터 찾아 '카카오뱅크'가 '카카오'로 잡히지 않게. 글에 먼저 나온 순."""
    taken, first_pos = [], {}
    for name in sorted(master, key=len, reverse=True):
        for m in re.finditer(re.escape(name), text):
            s, e = m.start(), m.end()
            if any(s < te and ts < e for ts, te in taken):
                continue
            taken.append((s, e))
            code = master[name]
            first_pos[code] = min(first_pos.get(code, s), s)
    return sorted(first_pos, key=first_pos.get)[:limit]


def blocked(text):
    """투자 권유 표현·청소년에게 맞지 않는 주제 (회사 이름만 나온 기사는 2026-11-16 사용자 결정으로 허용)."""
    return any(w in text for w in news.BLOCKED + news.SENSITIVE)


def candidates(now, fetch_fn=None, key=None):
    """최근 NEWS_LOOKBACK_DAYS일 금융 정책뉴스 후보: [{id, title, body, publisher, url, published_at, teen_score}]."""
    key = key or news.get_keys()
    fetch_fn = fetch_fn or news.fetch
    end = now.date()
    first = end - timedelta(days=config.NEWS_LOOKBACK_DAYS - 1)
    found, seen = [], set()
    day = end
    while day >= first:
        start = max(first, day - timedelta(days=news.WINDOW_DAYS - 1))
        for item in fetch_fn(start.strftime("%Y%m%d"), day.strftime("%Y%m%d"), key):
            title = item["title"]
            body = " ".join(p for p in [item["subtitle"], item["body"]] if p)
            if item.get("kogl", "1") != "1" or not title or not news.is_finance(item) or blocked(title + body):
                continue
            uid = item["link"] or re.sub(r"\W", "", title)[:30]
            if uid in seen:
                continue
            seen.add(uid)
            found.append({"id": uid, "title": title, "body": body[:news.DESCRIPTION_CHARS],
                          "publisher": item["ministry"] or "정책브리핑", "url": item["link"],
                          "published_at": news.news_date(item["approved"]) or end.isoformat(),
                          "teen_score": news.teen_score(title, body[:news.DESCRIPTION_CHARS])})
        day = start - timedelta(days=1)
    return found


# ---------- AI 카드 문장 (기존 생성기와 같은 규칙) ----------

def payload(picked, concepts):
    return {"news": [{"no": i, "title": n["title"], "description": n["body"], "quiz_type": QUIZ_TYPE_LABELS[t]}
                     for i, (n, t) in enumerate(zip(picked, QUIZ_TYPES), start=1)],
            "concepts": [{"id": cid, "name": c["name_ko"], "definition": c["sections"]["한 줄 정의"]}
                         for cid, c in concepts.items()]}


def cards_check(picked, concepts):
    """AI 결과 검사: 길이, 그 뉴스에 있던 숫자만, 개념 id, 보기 4개가 서로 다름, 주가 맞히기 금지, 권유 표현 금지."""

    def check(result):
        for i, n in enumerate(picked, start=1):
            source = news.numbers(n["title"] + " " + n["body"])
            for key, limit in (("what_title", TITLE_MAX), ("why_title", TITLE_MAX), ("me_title", TITLE_MAX),
                               ("what", BODY_MAX), ("why", BODY_MAX), ("me", BODY_MAX), ("tip", TIP_MAX),
                               ("list", LIST_MAX)):
                if len(result[f"n{i}_{key}"]) > limit:
                    raise ValueError(f"뉴스 {i}의 {key}가 {limit}자보다 김")
            text = " ".join(result[f"n{i}_{k}"] for k in ("what_title", "what", "why_title", "why", "me_title",
                                                          "me", "tip", "list"))
            quiz = " ".join([result[f"q{i}"], result[f"q{i}_explain"]] + result[f"q{i}_options"])
            extra = news.numbers(text + " " + quiz) - source
            if extra:
                raise ValueError(f"뉴스 {i}에 없는 숫자: {sorted(extra)}")
            if result[f"n{i}_concept"] not in concepts and result[f"n{i}_concept"] != "NONE":
                raise ValueError(f"없는 개념: {result[f'n{i}_concept']}")
            if any(w in quiz for w in PRICE_QUIZ_WORDS):
                raise ValueError(f"퀴즈 {i}가 주가·등락을 묻는다")
            if len(set(result[f"q{i}_options"])) != 4:
                raise ValueError(f"퀴즈 {i}에 같은 보기")
        if blocked(" ".join(str(v) for v in result.values())):
            raise ValueError("투자 권유 표현")
    return check


def concept_quiz(concept):
    """개념 파일의 확인 문제 → 퀴즈 dict (정답 표기 ①②③ → 번호)."""
    q = concept["quiz"]
    marks = "①②③④⑤"
    return {"question": q["질문"], "options": list(q["보기"]), "answer": marks.index(q["정답"][0]),
            "explanation": f"{concept['name_ko']}: {concept['sections']['한 줄 정의']}"}


def build_doc(result, picked, concepts, kmap, now, master=None):
    """AI 결과 + 뉴스 출처 → 하루치 저장 문서."""
    flags = config.NEWS_MARKET_FLAGS
    cats_list = diversify([pick_categories(n["title"], n["body"], kmap) for n in picked])
    items = []
    for i, (n, cats, qtype) in enumerate(zip(picked, cats_list, QUIZ_TYPES), start=1):
        cid = result[f"n{i}_concept"]
        concept = concepts.get(cid)
        tags = top_keywords(n["title"], n["body"], kmap) or [category_label(cats[0], kmap)]
        cards = [
            {"tag": CARD_TAGS[0], "title": result[f"n{i}_what_title"], "body": result[f"n{i}_what"]},
            {"tag": CARD_TAGS[1], "title": result[f"n{i}_why_title"], "body": result[f"n{i}_why"]},
            {"tag": CARD_TAGS[2], "title": result[f"n{i}_me_title"], "body": result[f"n{i}_me"],
             "tip": result[f"n{i}_tip"]},
            {"tag": CARD_TAGS[3], "concept": cid if concept else "",
             "word": concept["name_ko"] if concept else tags[0],
             "meaning": concept["sections"]["한 줄 정의"] if concept else ""},
        ]
        quiz = {"question": result[f"q{i}"], "options": result[f"q{i}_options"],
                "answer": int(result[f"q{i}_answer"]) - 1, "explanation": result[f"q{i}_explain"]}
        if qtype == "word" and concept and concept.get("quiz"):
            quiz = concept_quiz(concept)  # 단어 문제는 개념 파일의 확인 문제 (규칙 8)
        items.append({
            "news_id": n["id"], "title": n["title"], "publisher": n["publisher"], "url": n["url"],
            "published_at": n["published_at"], "summary": result[f"n{i}_list"],
            "categories": cats, "tags": tags,
            "images": slide_categories(cats) if flags["newsImages"] else [],
            "stocks": find_mentioned_stocks(n["title"] + " " + n["body"], master or {}) if flags["newsStockLink"] else [],
            "cards": cards, "quiz": {"type": qtype, **quiz},
        })
    return {"day": now.date().isoformat(), "made_at": now.isoformat(timespec="minutes"), "source": SOURCE,
            "items": items}


# ---------- 저장 ----------

def day_path(day, news_dir=None):
    return Path(news_dir or DAILY_DIR) / f"news_{day}.json"


def save(doc, news_dir=None):
    """하루치를 통째로 바꾼다 (3개가 다 준비됐을 때만 부른다)."""
    if len(doc["items"]) != config.DAILY_NEWS_COUNT:
        raise DailyNewsError("뉴스가 3개가 아니면 저장하지 않아요")
    path = day_path(doc["day"], news_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def load(day, news_dir=None):
    path = day_path(day, news_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def latest(news_dir=None):
    files = sorted(Path(news_dir or DAILY_DIR).glob("news_*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None


def recent_docs(today, days=7, news_dir=None):
    """today를 포함한 최근 days일의 저장본 (날짜순)."""
    docs = []
    for k in range(days - 1, -1, -1):
        doc = load((date.fromisoformat(today) - timedelta(days=k)).isoformat(), news_dir)
        if doc:
            docs.append(doc)
    return docs


def used_ids(today, news_dir=None):
    return {it["news_id"] for d in recent_docs(today, config.NEWS_REUSE_BLOCK_DAYS + 1, news_dir)
            for it in d["items"] if d["day"] != today}


def run_news_job(now, ask, concepts, fetch_fn=None, news_dir=None, key=None):
    """오늘의 뉴스 만들기 (자동 업데이트 작업). ask(payload, check) → AI 결과 dict (실패하면 예외 또는 빈 dict).
    후보가 모자라거나 AI가 실패하면 예외 → 어제 뉴스를 그대로 두고 다음 재시도 칸에 다시."""
    kmap = load_keyword_map()
    cands = candidates(now, fetch_fn, key)
    picked = pick_daily(cands, kmap, used_ids=used_ids(now.date().isoformat(), news_dir))
    if len(picked) < config.DAILY_NEWS_COUNT:
        raise DailyNewsError(f"뉴스 후보 부족: {len(picked)}개")
    result = ask(payload(picked, concepts), cards_check(picked, concepts))
    if not result:
        raise DailyNewsError("AI가 카드뉴스를 만들지 못했어요")
    doc = build_doc(result, picked, concepts, kmap, now, stock_master())
    save(doc, news_dir)
    return doc


# ---------- 학생 기록: 읽기 · 퀴즈 · 오답노트 · 주말 복습 (9장) ----------

def first_answers(answers, student_id, day=None):
    """학생의 (날짜, news_id)별 첫 답만 (다시 풀기는 포인트·정답률에 넣지 않는다)."""
    mine = answers[answers["student_id"] == student_id]
    if day:
        mine = mine[mine["day"] == day]
    return mine[mine["retry"] != "TRUE"].drop_duplicates(["day", "news_id"])


def today_progress(doc, answers, reads, student_id):
    day = doc["day"]
    read = set(reads[(reads["student_id"] == student_id) & (reads["day"] == day)]["news_id"])
    first = first_answers(answers, student_id, day)
    status = {r.news_id: r.correct == "TRUE" for r in first.itertuples()}
    points = news_points(answers, student_id, day)
    return {"read": sum(it["news_id"] in read for it in doc["items"]),
            "quiz": sum(it["news_id"] in status for it in doc["items"]),
            "status": status, "read_ids": read, "points": points,
            "max_points": config.NEWS_QUIZ_CORRECT_POINTS * config.DAILY_NEWS_COUNT + config.NEWS_QUIZ_ALL_DONE_BONUS}


def news_points(answers, student_id, day):
    first = first_answers(answers, student_id, day)
    pts = config.NEWS_QUIZ_CORRECT_POINTS * int((first["correct"] == "TRUE").sum())
    if len(first) >= config.DAILY_NEWS_COUNT:
        pts += config.NEWS_QUIZ_ALL_DONE_BONUS
    return pts


def point_events(answers, reviews, student_id):
    """포인트 기록 (rewards.earn_events가 하루 200P 상한 안에서 합친다)."""
    events = []
    first = first_answers(answers, student_id)
    for r in first.itertuples():
        if r.correct == "TRUE":
            events.append({"date": r.date, "kind": "뉴스 퀴즈", "capped": True,
                           "label": f"오늘의 뉴스 퀴즈 정답 ({r.day})", "points": config.NEWS_QUIZ_CORRECT_POINTS})
    for day, rows in first.groupby("day"):
        if len(rows) >= config.DAILY_NEWS_COUNT:
            events.append({"date": rows["date"].max(), "kind": "뉴스 퀴즈", "capped": True,
                           "label": f"오늘의 뉴스 3문제 완주 ({day})", "points": config.NEWS_QUIZ_ALL_DONE_BONUS})
    mine = reviews[(reviews["student_id"] == student_id) & (reviews["correct"] == "TRUE")]
    for r in mine.drop_duplicates(["week", "qid"]).itertuples():
        events.append({"date": r.date, "kind": "뉴스 복습", "capped": True,
                       "label": f"주말 복습 퀴즈 정답 ({r.week})", "points": config.NEWS_REVIEW_CORRECT_POINTS})
    return events


def week_days(today):
    d = date.fromisoformat(today)
    monday = d - timedelta(days=d.weekday())
    return [(monday + timedelta(days=k)).isoformat() for k in range(7)]


def item_index(docs):
    return {(d["day"], it["news_id"]): it for d in docs for it in d["items"]}


def wrong_notes(docs, answers, student_id):
    """이번 주 처음 틀린 문제 (나중에 맞혀도 오답노트에 남는다)."""
    idx = item_index(docs)
    notes = []
    for r in first_answers(answers, student_id).itertuples():
        it = idx.get((r.day, r.news_id))
        if it and r.correct != "TRUE":
            q = it["quiz"]
            notes.append({"day": r.day, "news_id": r.news_id, "type": q["type"], "news": it["cards"][0]["title"],
                          "question": q["question"], "answer": q["options"][q["answer"]], "quiz": q})
    return notes


def week_words(docs, reads, student_id):
    """이번 주 읽은 뉴스의 '오늘의 단어' (개념 파일에서 온 단어만)."""
    read = set(zip(reads[reads["student_id"] == student_id]["day"], reads[reads["student_id"] == student_id]["news_id"]))
    words = []
    for d in docs:
        for it in d["items"]:
            w = it["cards"][3]
            if (d["day"], it["news_id"]) in read and w.get("concept") and w["word"] not in [x["word"] for x in words]:
                words.append({"word": w["word"], "meaning": w["meaning"], "concept": w["concept"]})
    return words


def week_summary(today, answers, reads, reviews, student_id, news_dir=None):
    days = week_days(today)
    docs = [d for d in (load(day, news_dir) for day in days) if d]
    first = first_answers(answers, student_id)
    first = first[first["day"].isin(days)]
    read = reads[(reads["student_id"] == student_id) & reads["day"].isin(days)]
    by_day = {day: int((first[first["day"] == day]["correct"] == "TRUE").sum()) if day in set(first["day"]) else None
              for day in days}
    rate = None if not len(first) else round((first["correct"] == "TRUE").mean() * 100)
    pts = sum(e["points"] for e in point_events(answers, reviews, student_id)
              if e["date"] in days or any(day in e["label"] for day in days))
    return {"days": days, "by_day": by_day, "read": int(read["news_id"].nunique()), "rate": rate, "points": pts,
            "notes": wrong_notes(docs, answers[answers["day"].isin(days)], student_id),
            "words": week_words(docs, reads, student_id), "docs": docs}


def review_questions(summary, concepts):
    """주말 복습 5문제: 오답노트 먼저, 모자라면 이번 주 단어(개념 파일 확인 문제)."""
    qs = [{"qid": f"{n['day']}:{n['news_id']}", "label": f"{QUIZ_TYPE_LABELS[n['type']]} · {n['news']}", **n["quiz"]}
          for n in summary["notes"]]
    for w in summary["words"]:
        c = concepts.get(w["concept"])
        if c and c.get("quiz") and len(qs) < config.NEWS_REVIEW_COUNT:
            qs.append({"qid": f"word:{w['concept']}", "label": f"단어 · {w['word']}", **concept_quiz(c)})
    return qs[:config.NEWS_REVIEW_COUNT]


def news_trades(trades, student_id, days):
    """그 주 거래 중 뉴스 근거([뉴스] 말머리)를 붙인 수."""
    mine = trades[(trades["student_id"] == student_id) & trades["date"].isin(days)]
    return len(mine), int(mine["journal"].str.startswith("[뉴스]").sum())


def news_reason_prefix(title):
    return f"[뉴스] {title} — " if title else ""


def stock_news(code, today, news_dir=None, days=7):
    """최근 days일 동안 이 종목이 나온 뉴스 [(day, item)] (최신 먼저)."""
    out = []
    for d in reversed(recent_docs(today, days, news_dir)):
        out += [(d["day"], it) for it in d["items"] if code in it.get("stocks", [])]
    return out


def empty_answers():
    from engine import store
    return pd.DataFrame(columns=store.NEWS_ANSWER_COLUMNS)


DEMO_PATH = ROOT / "data" / "real" / "daily_news_demo.json"


def load_demo(concepts, path=None):
    """시안 재현 문서 (?mock=1). 단어 뜻과 단어 문제는 개념 파일에서 채운다 (규칙 8)."""
    doc = json.loads(Path(path or DEMO_PATH).read_text(encoding="utf-8"))
    for it in doc["items"]:
        word = it["cards"][3]
        c = concepts.get(word.get("concept"))
        if c:
            word["word"], word["meaning"] = c["name_ko"], c["sections"]["한 줄 정의"]
            if it["quiz"]["type"] == "word" and c.get("quiz"):
                it["quiz"] = {"type": "word", **concept_quiz(c)}
    return doc


def streak_days(answers, student_id, today):
    """오늘까지 하루도 빠지지 않고 뉴스 퀴즈를 푼 날 수 (오늘 안 풀었으면 어제까지)."""
    days = set(answers[answers["student_id"] == student_id]["day"])
    d = date.fromisoformat(today)
    if d.isoformat() not in days:
        d -= timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n
