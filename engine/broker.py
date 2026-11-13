"""투자 탭 어댑터: 시세(MarketDataProvider)와 증권사(BrokerAdapter). LLM 호출 금지.

- 이번 작업은 Mock만 구현한다. 실제 증권사 API 연동·실제 주문 전송·인증 정보 저장은 하지 않는다 (CLAUDE.md:
  실제 매수·매도 주문 연결 금지). RealBrokerAdapter는 인터페이스와 TODO만 있다.
- 시세는 기존 소스(시나리오 CSV, 공공데이터포털 종가)를 PriceTableProvider로 감싼다. 시안 재현은 MockMarketDataProvider.
- 공시·뉴스는 제목과 원문 링크만 쓴다 (본문 복제 금지). 아직 종목별 공시 API가 없어 기존 소스에서는 빈 목록이다.
"""

import json
from abc import ABC, abstractmethod
from datetime import date, timedelta
from pathlib import Path

from engine import invest_track as it

ROOT = Path(__file__).resolve().parent.parent
INSTRUMENTS_PATH = ROOT / "data" / "invest" / "instruments.json"
DEMO_PATH = ROOT / "data" / "invest" / "demo.json"


def load_instruments(path=None):
    """{종목코드: {type, isLargeCap}} (종목 구분 표). 표에 없으면 STOCK · 대형주 아님으로 본다."""
    return json.loads(Path(path or INSTRUMENTS_PATH).read_text(encoding="utf-8"))["instruments"]


def load_demo(path=None):
    """명세 7장 시안 재현 데이터."""
    return json.loads(Path(path or DEMO_PATH).read_text(encoding="utf-8"))


# ---------- 시세 ----------

class MarketDataProvider(ABC):
    @abstractmethod
    def names(self):
        """{종목코드: 이름}"""

    @abstractmethod
    def quote(self, symbol):
        """{symbol, price, changePct, asOf, delayed, label}"""

    @abstractmethod
    def history(self, symbol, days=30):
        """[(날짜, 종가)] 시간순, 최근 days 거래일"""

    @abstractmethod
    def disclosures(self, symbol):
        """[{type:'공시', title, url, source}]"""

    @abstractmethod
    def news(self, symbol):
        """[{type:'뉴스', title, url, source}]"""

    @abstractmethod
    def instrument(self, symbol):
        """{symbol, name, type: ETF|STOCK, isLargeCap}"""

    def headlines(self, symbol):
        return self.disclosures(symbol) + self.news(symbol)


class PriceTableProvider(MarketDataProvider):
    """기존 시세 소스(ui_common.market_context의 names·prices)를 감싼다. mode: scenario / real."""

    def __init__(self, names, prices, mode, instruments=None):
        self._names, self._prices, self.mode = names, prices, mode
        self._meta = instruments if instruments is not None else load_instruments()
        self.as_of = min(df["date"].iloc[-1] for df in prices.values())

    def names(self):
        return dict(self._names)

    def _rows(self, symbol):
        df = self._prices[symbol]
        return [(d, int(c)) for d, c in zip(df["date"], df["close"]) if d <= self.as_of]

    def quote(self, symbol):
        rows = self._rows(symbol)
        price = rows[-1][1]
        change = 0.0 if len(rows) < 2 else round((price / rows[-2][1] - 1) * 100, 1)
        when = f"{self.as_of[5:7]}/{self.as_of[8:]}"
        label = (f"실제 종가 · 하루 늦게 갱신 · {when} 기준" if self.mode == "real"
                 else f"연습용 가상 시세 · {when} 종가 기준")
        return {"symbol": symbol, "price": price, "changePct": change, "asOf": self.as_of, "delayed": True,
                "label": label}

    def history(self, symbol, days=30):
        return self._rows(symbol)[-days:]

    def disclosures(self, symbol):
        return []  # TODO: 공시 API(예: 금융감독원 전자공시 OpenAPI) 연결. 제목과 원문 링크만.

    def news(self, symbol):
        return []  # TODO: 종목 뉴스 제목·링크 API 연결 (주간 뉴스는 정책브리핑만 쓴다)

    def instrument(self, symbol):
        meta = self._meta.get(symbol, {})
        return {"symbol": symbol, "name": self._names.get(symbol, symbol), "type": meta.get("type", "STOCK"),
                "isLargeCap": bool(meta.get("isLargeCap", False))}


class MockMarketDataProvider(MarketDataProvider):
    """명세 7장 시안 데이터 (가상 종목 · 가상 공시). 1개월 흐름은 시안 그림처럼 만든 가상 값."""

    def __init__(self, demo):
        self.demo = demo

    def names(self):
        return {s: m["name"] for s, m in self.demo["instruments"].items()}

    def quote(self, symbol):
        q = self.demo["quotes"][symbol]
        if q.get("delayed"):
            label = f"실제 시세 · 15분 지연 · {q['asOf'][5:7]}/{q['asOf'][8:10]} {q['asOf'][11:16]} 기준"
        else:
            label = "실시간"
        return {"symbol": symbol, "price": q["price"], "changePct": q["changePct"], "asOf": q["asOf"],
                "delayed": q.get("delayed", False), "label": label}

    def history(self, symbol, days=30):
        q = self.demo["quotes"][symbol]
        price = q["price"]
        before = price / (1 + q["changePct"] / 100)
        end = date.fromisoformat(q["asOf"][:10])
        wiggle = [0.6, -0.4, 0.9, -1.2, 0.2, -0.8, 0.4, -1.0, 0.5, -0.3, 0.8, -0.6, 1.0, -0.2, 1.4]
        rows = [(end - timedelta(days=2 * (len(wiggle) - i)), round(before * (1 + w / 100)))
                for i, w in enumerate(wiggle)]
        rows.append((end, price))
        return [(d.isoformat(), c) for d, c in rows][-days:]

    def disclosures(self, symbol):
        return [h for h in self.demo.get("headlines", {}).get(symbol, []) if h["type"] == "공시"]

    def news(self, symbol):
        return [h for h in self.demo.get("headlines", {}).get(symbol, []) if h["type"] == "뉴스"]

    def instrument(self, symbol):
        m = self.demo["instruments"][symbol]
        return {"symbol": symbol, "name": m["name"], "type": m["type"], "isLargeCap": m["isLargeCap"]}


# ---------- 증권사 ----------

class BrokerAdapter(ABC):
    @abstractmethod
    def open_minor_account(self, consent):
        """미성년자 계좌 개설 → {accountId}"""

    @abstractmethod
    def place_order(self, real, req, quote, day):
        """주문 → {ok, code, filledQty, price, order}. validate_order()를 통과한 주문만 부른다."""

    @abstractmethod
    def get_account(self, real):
        """{id, kind:'REAL', cash, holdings}"""


class MockBrokerAdapter(BrokerAdapter):
    """연습용 가짜 증권사. 주문 시점 가격으로 바로 체결한다 (실제 주문 전송 없음).
    매수 금액은 체결 직전에 용돈 계좌(투자 봉투)에서 이체한 것으로 본다 (real.funded에 누적)."""

    def open_minor_account(self, consent):
        return {"accountId": f"MOCK-{consent.get('parent_id', 'P')}-{len(consent.get('requested_at') or '')}"}

    def place_order(self, real, req, quote, day):
        price = quote["price"]
        if req["side"] == "BUY":
            qty = it.estimate_qty(req["amount"], price)
            amount = req["amount"]
            real["funded"] = real.get("funded", 0) + amount
            real["cash"] += amount  # 용돈 계좌에서 이체
        else:
            qty = float(req["qty"])
            amount = round(qty * price)
        order = {"id": f"RO{len(real['orders']) + 1:04d}", "date": day, "symbol": req["symbol"],
                 "side": req["side"], "amount": amount, "qty": qty, "price": price,
                 "reason": " ".join((req.get("reason") or "").split()),
                 "fomo": bool(req.get("fomoAcknowledged")), "changePct": quote["changePct"]}
        it.apply_fill(real, order)
        return {"ok": True, "code": None, "filledQty": qty, "price": price, "order": order}

    def get_account(self, real):
        return {"id": real["account_id"], "kind": "REAL", "cash": real["cash"], "holdings": real["holdings"]}


class RealBrokerAdapter(BrokerAdapter):
    """TODO: 연계 증권사(그룹 내 증권사) 미성년자 계좌 API. 이 데모에서는 연결하지 않는다."""

    def open_minor_account(self, consent):
        raise NotImplementedError("실제 증권사 연동은 이 데모 범위 밖이에요")

    def place_order(self, real, req, quote, day):
        raise NotImplementedError("실제 주문 전송은 하지 않아요")

    def get_account(self, real):
        raise NotImplementedError("실제 증권사 연동은 이 데모 범위 밖이에요")


def open_real_account(state, broker, at=None):
    """부모 동의 → 계좌 개설(Mock) → ACTIVE. 실패하면 PENDING 그대로."""
    result = broker.open_minor_account(state["consent"])
    state["real"] = {"account_id": result["accountId"], "cash": 0, "funded": 0, "holdings": {}, "orders": []}
    it.transition(state, "APPROVE", at=at, account_id=result["accountId"])
    return state


def submit_real_order(state, broker, provider, req, day, available_cash):
    """실전 주문의 유일한 입구: validate_order → place_order → 매매 뒤 처리. {ok, code, order}.
    available_cash: 지금 이체할 수 있는 돈(투자 봉투 남은 돈 + 실전 계좌 현금)."""
    real = state["real"]
    quote = provider.quote(req["symbol"])
    instrument = provider.instrument(req["symbol"])
    usage = it.month_usage(real["orders"], it.month_key(day))
    held = real["holdings"].get(req["symbol"], {}).get("qty", 0.0)
    code = it.validate_order(req, state["guardrails"], state["consent"], usage, quote, instrument,
                             available_cash, held)
    if code:
        return {"ok": False, "code": code}
    result = broker.place_order(real, req, quote, day)
    it.after_trade(state, result["order"], instrument["name"], state["guardrails"])
    return result
