"""가격 데이터 피드.

- Bar: 일봉 한 개.
- load_csv: CSV(date,open,high,low,close,volume) 로더.
- generate_synthetic: 외부 의존 없이 백테스트 하네스를 검증하기 위한 합성 데이터.

실데이터 연동 시 토스 캔들 API(`/api/v1/candles`, interval='1d')를
`before` 페이지네이션으로 적재해 동일한 Bar 리스트로 변환하면 된다.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_csv(path: str | Path) -> list[Bar]:
    """CSV 파일에서 일봉을 로드. 헤더: date,open,high,low,close,volume"""
    bars: list[Bar] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            bars.append(
                Bar(
                    date=row["date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                )
            )
    bars.sort(key=lambda b: b.date)
    return bars


def generate_synthetic(
    symbols: list[str],
    days: int = 750,
    seed: int = 42,
    start_price: float = 100.0,
) -> dict[str, list[Bar]]:
    """추세·횡보 국면이 섞인 합성 일봉을 생성(재현 가능).

    돈치안 추세추종이 추세장에서 이익을 내고 횡보장에서 휩쏘를 겪는지
    하네스 동작을 검증하는 용도. 실제 수익성 근거가 아님.
    """
    rng = random.Random(seed)
    out: dict[str, list[Bar]] = {}
    # 가짜 거래일(주말 무시, 단순 증가). 실데이터에선 실제 영업일 사용.
    base = 20200101
    for s_idx, sym in enumerate(symbols):
        price = start_price * (1 + 0.1 * s_idx)
        bars: list[Bar] = []
        # 국면(레짐): drift 가 일정 구간마다 바뀜
        drift = rng.uniform(-0.0005, 0.0010)
        vol = rng.uniform(0.012, 0.022)
        regime_left = rng.randint(30, 90)
        day_counter = base + s_idx  # 심볼별로 살짝 다르게
        for _ in range(days):
            if regime_left <= 0:
                drift = rng.uniform(-0.0008, 0.0014)
                vol = rng.uniform(0.010, 0.025)
                regime_left = rng.randint(30, 90)
            regime_left -= 1

            shock = rng.gauss(drift, vol)
            new_close = max(1.0, price * math.exp(shock))
            o = price
            c = new_close
            hi = max(o, c) * (1 + abs(rng.gauss(0, vol / 2)))
            lo = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
            volu = rng.uniform(1e6, 5e6)
            # 날짜 문자열(단순 연속, 정렬만 보장)
            day_counter += 1
            date_str = str(day_counter)
            bars.append(Bar(date_str, round(o, 4), round(hi, 4), round(lo, 4), round(c, 4), volu))
            price = new_close
        out[sym] = bars
    return out
