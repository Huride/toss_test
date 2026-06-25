"""기술적 지표. 모두 point-in-time(주어진 인덱스까지의 데이터만) 계산.

look-ahead 방지를 위해, 인덱스 i 시점 신호는 i 까지의 값만 사용한다.
"""

from __future__ import annotations

from .datafeed import Bar


def sma(values: list[float], period: int, end: int) -> float | None:
    """values[end-period+1 .. end] 의 단순이동평균. 데이터 부족 시 None."""
    if end + 1 < period:
        return None
    window = values[end - period + 1 : end + 1]
    return sum(window) / period


def highest(values: list[float], period: int, end: int) -> float | None:
    """values[end-period+1 .. end] 의 최대값."""
    if end + 1 < period:
        return None
    return max(values[end - period + 1 : end + 1])


def lowest(values: list[float], period: int, end: int) -> float | None:
    if end + 1 < period:
        return None
    return min(values[end - period + 1 : end + 1])


def atr(bars: list[Bar], period: int, end: int) -> float | None:
    """Wilder 의 ATR 근사(단순평균 버전). end 시점까지의 True Range 평균."""
    if end < period:
        return None
    trs: list[float] = []
    for i in range(end - period + 1, end + 1):
        prev_close = bars[i - 1].close
        tr = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - prev_close),
            abs(bars[i].low - prev_close),
        )
        trs.append(tr)
    return sum(trs) / period
