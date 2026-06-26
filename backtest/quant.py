"""수리적/포트폴리오 전략 모듈.

per-symbol 신호 방식(engine.py)과 달리, 이들은 매 시점 전 종목을 보고
목표 비중(target weights)을 산출하는 포트폴리오 레벨 전략이다.
WeightBacktester(portfolio_engine.py)가 비중을 받아 리밸런싱을 시뮬레이션한다.

토스 제약(롱온리·무공매도)을 고려해:
- 크로스섹셔널 모멘텀: 롱온리 상위 N.
- 통계적 페어: 기본 롱온리(저평가 다리만). allow_short=True는 백테스트 분석용이며,
  실거래에선 숏 다리를 인버스 ETF로 근사해야 한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from .datafeed import Bar


# --------------------------------------------------------------------------
# 공통 수학 헬퍼 (모두 인덱스 i 까지의 데이터만 사용 → look-ahead 방지)
# --------------------------------------------------------------------------
def log_return(closes: list[float], i: int, lookback: int) -> float | None:
    if i - lookback < 0:
        return None
    prev = closes[i - lookback]
    if prev <= 0:
        return None
    return math.log(closes[i] / prev)


def rolling_mean_std(values: list[float], i: int, window: int) -> tuple[float, float] | None:
    if i + 1 < window:
        return None
    w = values[i - window + 1 : i + 1]
    mean = sum(w) / window
    var = sum((x - mean) ** 2 for x in w) / window
    return mean, math.sqrt(var)


def hedge_ratio(log_a: list[float], log_b: list[float], i: int, window: int) -> float | None:
    """log_a ≈ alpha + beta·log_b 의 OLS beta = cov/var (window 구간)."""
    if i + 1 < window:
        return None
    xa = log_a[i - window + 1 : i + 1]
    xb = log_b[i - window + 1 : i + 1]
    mb = sum(xb) / window
    ma = sum(xa) / window
    var_b = sum((b - mb) ** 2 for b in xb)
    if var_b <= 0:
        return None
    cov = sum((a - ma) * (b - mb) for a, b in zip(xa, xb))
    return cov / var_b


# --------------------------------------------------------------------------
# 포트폴리오 전략 인터페이스
# --------------------------------------------------------------------------
class PortfolioStrategy(Protocol):
    warmup: int

    def target_weights(self, data: dict[str, list[Bar]], i: int) -> dict[str, float]: ...


# --------------------------------------------------------------------------
# ③ 크로스섹셔널 모멘텀 (롱온리 상위 N)
# --------------------------------------------------------------------------
@dataclass
class CrossSectionalMomentum:
    lookback: int = 60
    top_k: int = 3
    trend_ma: int = 200          # 0 이면 추세필터 끔
    invest_ratio: float = 1.0    # 선택 종목에 투입할 총 비중

    @property
    def warmup(self) -> int:
        return max(self.lookback, self.trend_ma) + 1

    def target_weights(self, data: dict[str, list[Bar]], i: int) -> dict[str, float]:
        scores: list[tuple[str, float]] = []
        for sym, bars in data.items():
            closes = [b.close for b in bars]
            r = log_return(closes, i, self.lookback)
            if r is None:
                continue
            if self.trend_ma > 0:
                if i + 1 < self.trend_ma:
                    continue
                ma = sum(closes[i - self.trend_ma + 1 : i + 1]) / self.trend_ma
                if closes[i] <= ma:  # 추세필터: 상승추세만
                    continue
            scores.append((sym, r))
        if not scores:
            return {}
        scores.sort(key=lambda x: x[1], reverse=True)
        picks = [s for s, _ in scores[: self.top_k]]
        w = self.invest_ratio / len(picks)
        return {s: w for s in picks}


# --------------------------------------------------------------------------
# ② 통계적 페어 (공적분 스프레드 평균회귀)
# --------------------------------------------------------------------------
@dataclass
class PairsMeanReversion:
    sym_a: str
    sym_b: str
    window: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    gross: float = 1.0           # 페어에 투입할 총 명목(롱+숏 합)
    allow_short: bool = False    # True는 분석용. 실거래 숏은 인버스ETF 근사 필요

    @property
    def warmup(self) -> int:
        return self.window + 1

    def target_weights(self, data: dict[str, list[Bar]], i: int) -> dict[str, float]:
        a = [b.close for b in data[self.sym_a]]
        b = [b.close for b in data[self.sym_b]]
        la = [math.log(x) for x in a]
        lb = [math.log(x) for x in b]
        beta = hedge_ratio(la, lb, i, self.window)
        if beta is None or beta <= 0:
            return {}
        spread = [la[j] - beta * lb[j] for j in range(i + 1)]
        ms = rolling_mean_std(spread, i, self.window)
        if ms is None:
            return {}
        mean, std = ms
        if std <= 0:
            return {}
        z = (spread[i] - mean) / std

        # z < -entry: a 저평가 → a 롱 (+ b 숏). z > +entry: 반대.
        leg = self.gross / (1 + (beta if self.allow_short else 0))
        if z <= -self.entry_z:
            w = {self.sym_a: leg}
            if self.allow_short:
                w[self.sym_b] = -beta * leg
            return w
        if z >= self.entry_z:
            if self.allow_short:
                return {self.sym_a: -leg, self.sym_b: beta * leg}
            return {self.sym_b: leg}  # 롱온리: 저평가된 b 다리만
        if abs(z) <= self.exit_z:
            return {}  # 청산(현금)
        return {}  # 중립 구간 → 포지션 없음(보수적)
