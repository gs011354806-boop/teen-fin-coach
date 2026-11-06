"""22번 이번 주 금융 뉴스: 정책브리핑 정책뉴스 API(공공데이터포털)로 후보를 모으고, 주마다 카드뉴스 한 묶음을 저장한다. LLM 호출 금지.

- 공식 API만 쓴다 (웹사이트 크롤링 금지). 키는 시세와 같은 DATA_GO_KR_KEY (.env/Streamlit Secrets).
- 정부 정책뉴스 중 금융 관련(금융위원회·금융감독원 등 부처 또는 금융 낱말)만 후보로 남긴다.
- 종목 이름이나 '급등주·테마주·종목 추천' 같은 말이 든 뉴스는 뺀다 (CLAUDE.md 규칙 3).
- AI는 후보 중 3개를 골라 카드 문장과 퀴즈만 쓴다. 고른 뉴스 id, 개념, 숫자는 여기서 검사한다.
- 한 주에 한 번 만든 카드뉴스는 data/real/news_<주차>.json에 저장해 다시 부르지 않는다.
  못 만들면(키 없음, 활용신청 전, API·AI 실패) 가장 최근 저장본을 보여 준다.
- 출처 표시: 정책브리핑(www.korea.kr), 공공누리
"""

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "data" / "real"
ENV_PATH = ROOT / ".env"
# 데이터 페이지(15095335)의 정책뉴스 기사목록 조회. 예전 policyNewsService/policyNewsList는 폐기됨 (2026-11 확인)
API_URL = "https://apis.data.go.kr/1371000/policyNewsService2/policyNewsList2"
SOURCE = "정책브리핑(korea.kr), 공공데이터포털"
KST = ZoneInfo("Asia/Seoul")
HTTP_TIMEOUT_SECONDS = 15

DAYS = 7               # 최근 며칠 안의 뉴스만
WINDOW_DAYS = 3        # 한 번에 요청하는 기간 (긴 기간은 나눠서 부른다)
MAX_CANDIDATES = 12
DESCRIPTION_CHARS = 300  # AI에 넘길 본문 앞부분 길이
CARD_COUNT = 3
QUIZ_COUNT = 3
FINANCE_MINISTRIES = ["금융위원회", "금융감독원", "기획재정부", "공정거래위원회", "한국은행", "예금보험공사"]
FINANCE_WORDS = ["금융", "저축", "예금", "적금", "금리", "대출", "사기", "보이스피싱", "피싱", "청소년", "용돈",
                 "소비자", "보험", "카드", "물가", "자산", "투자자 보호", "경제교육"]
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
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise NewsError("공공데이터포털 키(DATA_GO_KR_KEY)가 없어요")
    return key


def clean(text):
    """본문 HTML 태그와 &nbsp; 같은 표기를 지우고 공백을 하나로."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def windows(now):
    """최근 DAYS일을 WINDOW_DAYS일씩 나눈 (시작, 끝) YYYYMMDD 목록."""
    end, first = now.date(), now.date() - timedelta(days=DAYS - 1)
    result = []
    while end >= first:
        start = max(first, end - timedelta(days=WINDOW_DAYS - 1))
        result.append((start.strftime("%Y%m%d"), end.strftime("%Y%m%d")))
        end = start - timedelta(days=1)
    return result


def parse_items(body):
    """정책뉴스 XML → 뉴스 dict 목록. 결과 코드가 정상이 아니면 NewsError."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise NewsError("정책브리핑 응답을 읽지 못했어요") from e
    code = (root.findtext(".//resultCode") or "").strip()
    if code and code not in ("0", "00"):
        raise NewsError(f"정책브리핑 API 오류: {(root.findtext('.//resultMsg') or code).strip()}")
    reason = root.findtext(".//returnAuthMsg") or root.findtext(".//returnReasonCode")
    if reason:
        raise NewsError(f"정책브리핑 API 오류: {reason.strip()} (활용신청·키를 확인해 주세요)")
    items = []
    for node in root.iter("NewsItem"):
        get = lambda tag: (node.findtext(tag) or "").strip()
        items.append({"title": clean(get("Title")), "subtitle": clean(get("SubTitle1")),
                      "body": clean(get("DataContents")), "ministry": clean(get("MinisterCode")),
                      "link": get("OriginalUrl"), "approved": get("ApproveDate")})
    return items


def fetch(start, end, key):
    """한 기간의 정책뉴스. 실패하면 NewsError."""
    query = urllib.parse.urlencode({"serviceKey": key, "startDate": start, "endDate": end})
    try:
        with urllib.request.urlopen(f"{API_URL}?{query}", timeout=HTTP_TIMEOUT_SECONDS) as response:
            return parse_items(response.read())
    except urllib.error.HTTPError as e:
        reason = re.search(r"<returnAuthMsg>(.*?)</returnAuthMsg>", e.read().decode("utf-8", errors="replace"))
        hint = " (공공데이터포털에서 정책브리핑 정책뉴스 API 활용신청이 필요해요)" if e.code in (401, 403) else ""
        raise NewsError(f"정책브리핑 API 오류(HTTP {e.code}): {reason.group(1) if reason else ''}{hint}") from e
    except OSError as e:
        raise NewsError(f"정책브리핑 요청 실패: {e!r}") from e


def blocked(text, ticker_names):
    return any(w in text for w in BLOCKED) or any(n in text for n in ticker_names)


def is_finance(item):
    text = f"{item['title']} {item['subtitle']} {item['body'][:DESCRIPTION_CHARS]}"
    return any(m in item["ministry"] for m in FINANCE_MINISTRIES) or any(w in text for w in FINANCE_WORDS)


def news_date(approved):
    """ApproveDate (예: '11/05/2026 10:00:00' 또는 '2026-11-05 10:00:00') → 'YYYY-MM-DD'. 모르면 빈 문자열."""
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(approved, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def candidates(now, ticker_names, keys=None, fetch_fn=None):
    """최근 DAYS일 금융 정책뉴스 후보 (최대 MAX_CANDIDATES개, 최신순). id는 n1, n2, ..."""
    key = keys or get_keys()
    fetch_fn = fetch_fn or fetch
    seen, found = set(), []
    for start, end in windows(now):
        for item in fetch_fn(start, end, key):
            title = item["title"]
            description = " ".join(part for part in [item["subtitle"], item["body"]] if part)[:DESCRIPTION_CHARS]
            dedupe = re.sub(r"\W", "", title)[:20]
            if not title or dedupe in seen or not is_finance(item) or blocked(title + description, ticker_names):
                continue
            seen.add(dedupe)
            found.append({"title": title, "description": description, "link": item["link"], "originallink": "",
                          "press": item["ministry"] or "정책브리핑", "date": news_date(item["approved"])})
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
