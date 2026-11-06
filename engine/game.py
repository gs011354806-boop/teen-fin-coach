"""21번 자산 키우기 게임: 떨어지는 단어 중 좋은 습관만 바구니로 받는다. LLM 호출 금지.

- 단어·이유·연결 개념은 여기서 고정한다 (개념은 content/concepts 카드에만 연결).
- 학생에게 많이 보인 실수와 같은 개념의 단어를 더 자주 떨어뜨린다 (코드가 정한다).
- 코인은 게임 안 점수일 뿐, 역량 평가나 포인트 보상에 쓰지 않는다. 수익률과도 상관없다.
- 코인이 기준보다 적으면 1분 복습(개념 카드 + 퀴즈)을 마쳐야 다시 도전할 수 있다.
"""

import random
from collections import Counter

from engine import detect

START_COINS = 10000
GOOD_COINS = 1000     # 좋은 습관을 받으면
BAD_COINS = -1500     # 나쁜 습관을 받으면
PASS_COINS = 15000    # 이만큼 이상이면 바로 다시 도전, 적으면 1분 복습
DURATION_SECONDS = 40
DECK_SIZE = 40
BOOST = 2             # 학생 맞춤 개념 단어의 출제 가중치

# (단어, 좋은 습관인가, 받았을 때·놓쳤을 때 보여 줄 한 줄, 연결 개념)
WORDS = [
    ("분산투자", True, "여러 곳에 나누면 한 곳이 흔들려도 괜찮아요", "DIVERSIFICATION"),
    ("나눠 담기", True, "한 종목 비중을 정해 두면 마음이 편해요", "DIVERSIFICATION"),
    ("복리", True, "이자에 이자가 붙어 시간이 내 편이 돼요", "COMPOUND_INTEREST"),
    ("꾸준한 적립", True, "적은 돈도 매주 모으면 크게 자라요", "COMPOUND_INTEREST"),
    ("오래 두기", True, "자주 꺼내지 않아야 복리가 일해요", "COMPOUND_INTEREST"),
    ("목표저축", True, "무엇을, 얼마, 언제까지를 먼저 정해요", "GOAL_SAVING"),
    ("봉투 지키기", True, "모으기 봉투는 꺼내 쓰지 않아요", "GOAL_SAVING"),
    ("투자 일지", True, "왜 샀는지 적어 두면 다시 배울 수 있어요", "INVESTMENT_JOURNAL"),
    ("근거 확인", True, "기사, 숫자, 경험을 보고 판단해요", "INVESTMENT_JOURNAL"),
    ("하루 기다리기", True, "사고 싶을 때 하루만 참아 봐요", "NEEDS_VS_WANTS"),
    ("필요한 소비", True, "꼭 필요한 곳에 먼저 써요", "NEEDS_VS_WANTS"),
    ("틀릴 수도 있다", True, "다른 가능성도 생각하면 덜 흔들려요", "OVERCONFIDENCE"),
    ("비상금", True, "갑자기 돈이 필요할 때 목표 저축을 지켜 줘요", "EMERGENCY_FUND"),
    ("몰빵", False, "한 곳에 다 넣으면 한 번에 크게 흔들려요", "DIVERSIFICATION"),
    ("급등 따라 사기", False, "이미 오른 뒤에 급하게 사는 건 위험해요", "FOMO"),
    ("친구가 샀대", False, "남의 이유는 내 이유가 아니에요", "FOMO"),
    ("나만 놓칠까 봐", False, "조급함은 판단을 흐려요", "FOMO"),
    ("무조건 오른다", False, "'무조건'은 금융에 없어요", "OVERCONFIDENCE"),
    ("대박 확신", False, "확신이 클수록 한 번 더 확인해요", "OVERCONFIDENCE"),
    ("그냥 샀어", False, "이유가 없으면 배울 것도 없어요", "INVESTMENT_JOURNAL"),
    ("충동구매", False, "갖고 싶은 것과 필요한 것은 달라요", "NEEDS_VS_WANTS"),
    ("습관성 간식", False, "작은 돈도 매일이면 커져요", "NEEDS_VS_WANTS"),
    ("저축 꺼내 쓰기", False, "목표가 자꾸 멀어져요", "GOAL_SAVING"),
    ("빚투", False, "빌린 돈으로 투자하면 잃을 때 더 크게 잃어요", "DEBT_INVESTING"),
    ("원금 보장 고수익", False, "이런 말은 금융 사기를 먼저 의심해요", "GUARANTEED_RETURN_SCAM"),
]
BY_WORD = {w: {"word": w, "good": g, "reason": r, "concept": c} for w, g, r, c in WORDS}


def boost_concepts(student, trades, prices, allowance):
    """이 학생에게 더 자주 보여 줄 개념: 2번 이상 보인 실수 패턴의 개념(없으면 가장 많은 것) + 모으기 봉투를 꺼낸 적이 있으면 목표저축."""
    counts = Counter(p for d in detect.detect(trades, prices, student) for p in d["patterns"])
    concepts = {detect.CONCEPT_FOR_PATTERN[p] for p, n in counts.items() if n >= 2}  # 되풀이된 실수
    if counts and not concepts:
        concepts.add(detect.CONCEPT_FOR_PATTERN[counts.most_common(1)[0][0]])
    mine = allowance[(allowance["student_id"] == student["student_id"]) & (allowance["envelope"] == "SAVE")]
    if (mine["amount"] < 0).any():
        concepts.add("GOAL_SAVING")
    return sorted(concepts)


def deck(boosted, seed, size=DECK_SIZE):
    """떨어질 단어 순서. 좋은 습관과 나쁜 습관을 번갈아 비슷하게 섞고, 맞춤 개념 단어는 BOOST배 자주."""
    rng = random.Random(seed)
    weights = {w["word"]: BOOST if w["concept"] in boosted else 1 for w in BY_WORD.values()}
    goods = [w for w in BY_WORD if BY_WORD[w]["good"]]
    bads = [w for w in BY_WORD if not BY_WORD[w]["good"]]
    words = []
    for i in range(size):
        pool = goods if i % 2 == 0 else bads
        words.append(rng.choices(pool, weights=[weights[w] for w in pool])[0])
    rng.shuffle(words)
    return [{"word": w, "good": BY_WORD[w]["good"]} for w in words]


def coins(caught):
    """받은 단어로 코인 계산 (게임 안 점수)."""
    return START_COINS + sum(GOOD_COINS if BY_WORD[w]["good"] else BAD_COINS for w in caught if w in BY_WORD)


def summary(caught, missed):
    """결과: 받은 좋은 습관, 받은 나쁜 습관(횟수), 놓친 좋은 습관, 코인, 통과 여부, 복습할 개념(최대 2개)."""
    caught = [w for w in caught if w in BY_WORD]
    missed = [w for w in missed if w in BY_WORD and BY_WORD[w]["good"] and w not in caught]  # 한 번이라도 받았으면 뺀다
    good = [w for w in dict.fromkeys(caught) if BY_WORD[w]["good"]]
    bad = Counter(w for w in caught if not BY_WORD[w]["good"])
    total = coins(caught)
    weak = Counter(BY_WORD[w]["concept"] for w in caught if not BY_WORD[w]["good"])
    weak.update(BY_WORD[w]["concept"] for w in missed)
    return {"good": good, "bad": dict(bad.most_common()), "missed": list(dict.fromkeys(missed)),
            "coins": total, "passed": total >= PASS_COINS,
            "review": [c for c, _ in weak.most_common(2)]}


def object_josa(word):
    """목적격 조사: 받침이 있으면 '을', 없으면 '를'."""
    last = word.strip()[-1:]
    return "을" if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 else "를"


def facts(result, detections):
    """AI 코치 한마디의 재료 (숫자는 여기서만 만든다). 게임 결과와 실제 매수 행동을 잇는다."""
    sentences = [f"좋은 습관 단어를 {len(result['good'])}종류 받았어요."]
    if result["bad"]:
        top, n = next(iter(result["bad"].items()))
        sentences.append(f"나쁜 습관 '{top}'{object_josa(top)} {n}번 받았어요.")
    else:
        sentences.append("나쁜 습관 단어는 하나도 받지 않았어요.")
    if result["missed"]:
        sentences.append(f"'{result['missed'][0]}'처럼 좋은 습관을 놓치기도 했어요.")
    mistakes = detect.mistakes(detections)
    if mistakes:
        latest = mistakes[0]
        if detect.CONCENTRATION in latest["patterns"]:
            sentences.append(f"실제 가상투자에서도 한 종목 비중이 {latest['weight_pct']}%였던 매수가 있었어요.")
        elif detect.SURGE in latest["patterns"]:
            sentences.append("실제 가상투자에서도 급등한 날 따라 산 매수가 있었어요.")
        elif detect.NO_REASON in latest["patterns"]:
            sentences.append("실제 가상투자에서도 이유를 적지 않은 매수가 있었어요.")
    return sentences


def coach_payload(student, result, sentences):
    return {"student": {"name": student["name"], "grade": student["grade"]}, "facts": sentences,
            "good_words": result["good"], "bad_words": list(result["bad"]), "missed_words": result["missed"]}


def default_coach(result):
    if result["bad"]:
        top = next(iter(result["bad"]))
        return {"message": f"좋은 습관 단어를 잘 골라 받았어요. 다음 판에는 '{top}'{object_josa(top)} 피해 봐요."}
    return {"message": "좋은 습관 단어를 잘 골라 받았어요. 실제 가상투자에서도 같은 습관을 이어 가 봐요."}


def quiz_payload(concept):
    s = concept["sections"]
    return {"concept": {"name": concept["name_ko"], "definition": s["한 줄 정의"],
                        "example": s["이런 행동이었어요"], "checks": s["다음엔 이렇게 확인해 보세요"],
                        "existing_quiz": concept["quiz"].get("질문", "")}}


def quiz_check(concept):
    """AI 퀴즈 검사: 카드에 없는 숫자, 같은 보기, 두 문제 정답 번호가 같으면 실패 (재시도)."""
    from engine.growth import NUMBER

    card = " ".join(concept["sections"].values())
    allowed = {"".join(n.split()) for n in NUMBER.findall(card)}

    def check(result):
        text = " ".join([result["q1"], result["q2"], *result["q1_options"], *result["q2_options"]])
        extra = {"".join(n.split()) for n in NUMBER.findall(text)} - allowed
        if extra:
            raise ValueError(f"카드에 없는 숫자: {sorted(extra)}")
        for key in ("q1_options", "q2_options"):
            if len(set(result[key])) != 3:
                raise ValueError(f"같은 보기: {key}")
        if result["q1_answer"] == result["q2_answer"]:
            raise ValueError("두 문제 정답 번호가 같음")
    return check


def card_quiz(concept):
    """카드에 원래 있는 확인 문제 (AI 퀴즈가 실패해도 복습은 이 문제로 할 수 있다)."""
    q = concept["quiz"]
    return {"question": q["질문"], "options": q["보기"], "answer": "①②③④⑤".index(q["정답"]) + 1}


def ai_quiz_items(result):
    """AI 응답 → 문제 목록. 기본값(빈 문제)이면 빈 목록."""
    if not result.get("q1"):
        return []
    return [{"question": result[f"q{i}"], "options": result[f"q{i}_options"], "answer": int(result[f"q{i}_answer"])}
            for i in (1, 2)]
