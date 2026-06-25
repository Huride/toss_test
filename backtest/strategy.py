"""전략 코어와 AI 오버레이 인터페이스.

- Strategy: 종목별 point-in-time 신호 생성.
- DonchianBreakout: 추세필터 + N일 돌파 진입 / M일 트레일링 청산 + ATR 손절.
- AIScorer: 뉴스/이슈 점수화(옵션). 기본 NullScorer 는 항상 중립.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .datafeed import Bar
from .indicators import atr, highest, lowest, sma


@dataclass
class StrategyParams:
    entry_lookback: int = 20
    exit_lookback: int = 10
    trend_ma: int = 200
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    risk_per_trade: float = 0.01
    max_positions: int = 8
    max_weight: float = 0.20


@dataclass
class Signal:
    """인덱스 i(해당 일 종가 확정 후) 시점의 의사결정. 체결은 익일 시가 가정."""

    enter: bool = False
    exit: bool = False
    # 진입 시 사이징에 사용할 손절 거리(가격 단위) = atr_stop_mult * ATR
    stop_distance: float | None = None
    ref_price: float | None = None  # 신호 산출 시점 종가(사이징 참고)


# --------------------------------------------------------------------------
# AI 오버레이 인터페이스
# --------------------------------------------------------------------------
@dataclass
class AIScore:
    direction: str = "neutral"  # bullish | neutral | bearish
    conviction: float = 0.0
    materiality: float = 0.0
    rationale: str = ""


class AIScorer(Protocol):
    def score(self, symbol: str, date: str, context: dict) -> AIScore: ...


class NullScorer:
    """뉴스/AI 비활성. 항상 중립 → 가격 코어 단독 동작."""

    def score(self, symbol: str, date: str, context: dict) -> AIScore:
        return AIScore()


# --------------------------------------------------------------------------
# 전략 인터페이스
# --------------------------------------------------------------------------
class Strategy(Protocol):
    def evaluate(
        self, bars: list[Bar], i: int, in_position: bool, entry_atr: float | None
    ) -> Signal: ...


@dataclass
class DonchianBreakout:
    params: StrategyParams = field(default_factory=StrategyParams)

    def evaluate(
        self, bars: list[Bar], i: int, in_position: bool, entry_atr: float | None
    ) -> Signal:
        p = self.params
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        # 워밍업: 추세필터 SMA 가 계산 가능해야 함
        trend = sma(closes, p.trend_ma, i)
        a = atr(bars, p.atr_period, i)
        if trend is None or a is None:
            return Signal()

        close = closes[i]

        if in_position:
            # 트레일링 청산: 최근 exit_lookback 일 최저가(당일 제외) 하향 이탈
            exit_low = lowest(lows, p.exit_lookback, i - 1)
            donchian_exit = exit_low is not None and close <= exit_low
            # ATR 손절(진입 시 ATR 고정). 봇은 stop 주문이 없어 종가 기준 폴링 청산.
            stop_hit = False
            if entry_atr is not None:
                # 손절 트리거는 엔진이 진입가를 알고 처리하므로 여기선 신호만.
                pass
            return Signal(exit=donchian_exit, stop_distance=p.atr_stop_mult * a)

        # 진입: 추세필터 + 돌파(당일 제외 최근 entry_lookback 일 최고가)
        entry_high = highest(highs, p.entry_lookback, i - 1)
        breakout = entry_high is not None and close >= entry_high
        uptrend = close > trend
        if breakout and uptrend:
            return Signal(
                enter=True,
                stop_distance=p.atr_stop_mult * a,
                ref_price=close,
            )
        return Signal()
