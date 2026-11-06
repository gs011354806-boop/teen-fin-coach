"""22번 이번 주 금융 뉴스: 네이버 뉴스 검색 API로 후보를 모으고, 주마다 카드뉴스 한 묶음을 저장한다. LLM 호출 금지.

- 공식 API만 쓴다 (웹사이트 크롤링 금지). 키는 .env/Streamlit Secrets의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET.
- 종목 이름이나 '급등주·테마주·종목 추천' 같은 말이 든 뉴스는 후보에서 뺀다 (CLAUDE.md 규칙 3).
- AI는 후보 중 3개를 골라 카드 문장과 퀴즈만 쓴다. 고른 뉴스 id, 개념, 숫자는 여기서 검사한다.
- 한 주에 한 번 만든 카드뉴스는 data/real/news_<주차>.json에 저장해 다시 부르지 않는다.
  못 만들면(키 없음, API·AI 실패) 가장 최근 저장본을 보여 준다.
"""

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "data" / "real"
ENV_PATH = ROOT / ".env"
API_URL = "https://openapi.naver.com/v1/search/news.json"
SOURCE = "네이버 뉴스 검색 API"
KST = ZoneInfo("Asia/Seoul")
HTTP_TIMEOUT_SECONDS = 10

QUERIES = ["청소년 금융", "금융사기 예방", "용돈 저축", "예금 금리", "경제 교육"]
DAYS = 7               # 최근 며칠 안의 뉴스만
PER_QUERY = 20
MAX_CANDIDATES = 12
CARD_COUNT = 3
QUIZ_COUNT = 3
BLOCKED = ["급등주", "상한가", "테마주", "종목 추천", "추천주", "매수 추천", "목표주가", "대박주", "따상"]

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*(?:%p|%|조\s*원|억\s*원|만\s*원|원|명|건|배|년|월|일|세|개|곳)?")


class NewsError(Exception):
    pass


def now_kst():
    return datetime.now(KST)


def week_id(now):
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def week_range(now):
    """그 주 월요일~일요일 (화면 표시용 'M/D~M/D')."""
    monday = (now - timedelta(days=now.weekday())).date()
    sunday = monday + timedelta(days=6)
    return f"{monday.month}/{monday.day}~{sunday.month}/{sunday.day}"


def week_path(week):
    return NEWS_DIR / f"news_{week}.json"


def get_keys():
    load_dotenv(ENV_PATH)
    cid, secret = os.getenv("NAVER_CLIENT_ID", "").strip(), os.getenv("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise NewsError("뉴스 API 키(NAVER_CLIENT_ID, NAVER_CLIENT_SECRET)가 없어요")
    return cid, secret


def clean(text):
    """검색 결과의 <b> 태그와 &quot; 같은 표기를 지운다."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text or "")).split())


def fetch(query, keys):
    """검색어 하나의 최신 뉴스 (API 원본 items). 실패하면 NewsError."""
    url = f"{API_URL}?{urllib.parse.urlencode({'query': query, 'display': PER_QUERY, 'sort': 'date'})}"
    request = urllib.request.Request(url, headers={"X-Naver-Client-Id": keys[0],
                                                   "X-Naver-Client-Secret": keys[1]})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8")).get("items", [])
    except urllib.error.HTTPError as e:
        raise NewsError(f"뉴스 API 오류({e.code})") from e
    except (OSError, ValueError) as e:
        raise NewsError(f"뉴스 요청 실패: {e!r}") from e


def press_of(item):
    """원문 주소의 도메인 (예: www.yna.co.kr → yna.co.kr). 네이버 API는 언론사 이름을 주지 않는다."""
    host = urllib.parse.urlparse(item.get("originallink") or item.get("link", "")).netloc
    return host[4:] if host.startswith("www.") else host


def blocked(text, ticker_names):
    return any(w in text for w in BLOCKED) or any(n in text for n in ticker_names)


def candidates(now, ticker_names, keys=None, fetch_fn=None):
    """최근 DAYS일 뉴스 중 걸러 낸 후보 (최대 MAX_CANDIDATES개, 최신순). id는 n1, n2, ..."""
    keys = keys or get_keys()
    fetch_fn = fetch_fn or fetch
    since = now - timedelta(days=DAYS)
    seen, found = set(), []
    for query in QUERIES:
        for item in fetch_fn(query, keys):
            title, description = clean(item.get("title")), clean(item.get("description"))
            try:
                published = parsedate_to_datetime(item.get("pubDate", ""))
            except (TypeError, ValueError):
                continue
            key = re.sub(r"\W", "", title)[:20]
            if published < since or not title or key in seen or blocked(title + description, ticker_names):
                continue
            seen.add(key)
            found.append({"title": title, "description": description, "link": item.get("link", ""),
                          "originallink": item.get("originallink", ""), "press": press_of(item),
                          "date": published.astimezone(KST).strftime("%Y-%m-%d"), "query": query})
    found.sort(key=lambda n: n["date"], reverse=True)
    return [{**n, "id": f"n{i}"} for i, n in enumerate(found[:MAX_CANDIDATES], start=1)]


def payload(cands, concepts):
    return {"news": [{"id": n["id"], "title": n["title"], "description": n["description"]} for n in cands],
            "concepts": [{"id": cid, "name": c["name_ko"], "definition": c["sections"]["한 줄 정의"]}
                         for cid, c in concepts.items()]}


def numbers(text):
    return {"".join(n.split()) for n in NUMBER.findall(text)}


def cards_check(cands, concepts, ticker_names):
    """AI 카드뉴스 검사: 있는 뉴스만 서로 다르게 고르고, 개념은 카드 목록 또는 NONE, 숫자는 그 뉴스에 있던 것만."""
    by_id = {n["id"]: n for n in cands}

    def check(result):
        ids = [result[f"card{i}_news_id"] for i in range(1, CARD_COUNT + 1)]
        if any(i not in by_id for i in ids) or len(set(ids)) != CARD_COUNT:
            raise ValueError(f"없는 뉴스 또는 같은 뉴스: {ids}")
        allowed_all = set()
        for i, nid in enumerate(ids, start=1):
            source = numbers(by_id[nid]["title"] + " " + by_id[nid]["description"])
            allowed_all |= source
            text = " ".join(result[f"card{i}_{k}"] for k in ("headline", "summary", "why"))
            if numbers(text) - source:
                raise ValueError(f"카드 {i}에 뉴스에 없는 숫자: {sorted(numbers(text) - source)}")
            if result[f"card{i}_concept"] not in concepts and result[f"card{i}_concept"] != "NONE":
                raise ValueError(f"없는 개념: {result[f'card{i}_concept']}")
        quiz = " ".join(result[f"q{i}"] + " " + " ".join(result[f"q{i}_options"]) for i in range(1, QUIZ_COUNT + 1))
        if numbers(quiz) - allowed_all:
            raise ValueError(f"퀴즈에 뉴스에 없는 숫자: {sorted(numbers(quiz) - allowed_all)}")
        everything = " ".join(str(v) for v in result.values())
        if blocked(everything, ticker_names):
            raise ValueError("종목 이름이나 투자 권유 표현")
        for i in range(1, QUIZ_COUNT + 1):
            if len(set(result[f"q{i}_options"])) != 3:
                raise ValueError(f"같은 보기: q{i}")
    return check


def build(result, cands, now):
    """AI 결과 + 뉴스 출처 → 저장할 카드뉴스 묶음."""
    by_id = {n["id"]: n for n in cands}
    cards = []
    for i in range(1, CARD_COUNT + 1):
        n = by_id[result[f"card{i}_news_id"]]
        cards.append({"headline": result[f"card{i}_headline"], "summary": result[f"card{i}_summary"],
                      "why": result[f"card{i}_why"], "concept": result[f"card{i}_concept"],
                      "news": {"title": n["title"], "link": n["originallink"] or n["link"],
                               "press": n["press"], "date": n["date"]}})
    quiz = [{"question": result[f"q{i}"], "options": result[f"q{i}_options"], "answer": int(result[f"q{i}_answer"])}
            for i in range(1, QUIZ_COUNT + 1)]
    return {"week": week_id(now), "range": week_range(now), "made_at": now.isoformat(timespec="minutes"),
            "source": SOURCE, "cards": cards, "quiz": quiz}


def save(doc, path=None):
    path = Path(path or week_path(doc["week"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def load(week, news_dir=None):
    path = Path(news_dir or NEWS_DIR) / f"news_{week}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def latest(news_dir=None):
    """가장 최근 주차의 저장본 (없으면 None)."""
    files = sorted(Path(news_dir or NEWS_DIR).glob("news_*.json"))
    return json.loads(files[-1].read_text(encoding="utf-8")) if files else None
