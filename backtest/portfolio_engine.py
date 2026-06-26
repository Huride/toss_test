"""비중 기반 포트폴리오 백테스트 엔진.

PortfolioStrategy.target_weights(data, i) 를 받아 주기적 리밸런싱을 시뮬레이션.
가치 기반(value-based) 시뮬: 각 종목 보유가치가 일간 수익률로 변동하고,
리밸런싱 시 목표비중으로 회전(turnover)하며 거래비용을 차감한다.

look-ahead 방지: i일 종가까지의 데이터로 목표비중 결정 → i→i+1 수익률 적용.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .datafeed import Bar
from .quant import PortfolioStrategy


@dataclass
class PortfolioConfig:
    initial_cash: float = 100_000.0
    rebalance_every: int = 5          # N 영업일마다 리밸런싱
    cost_bps: float = 10.0            # 회전 명목 대비 거래비용(수수료+슬리피지)


@dataclass
class PortfolioResult:
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class WeightBacktester:
    def __init__(self, strategy: PortfolioStrategy, config: PortfolioConfig | None = None):
        self.strategy = strategy
        self.config = config or PortfolioConfig()

    def run(self, data: dict[str, list[Bar]]) -> PortfolioResult:
        cfg = self.config
        symbols = list(data.keys())
        n = min(len(bars) for bars in data.values())
        cost = cfg.cost_bps / 10_000.0

        pv: dict[str, float] = {s: 0.0 for s in symbols}  # 종목별 보유가치
        cash = cfg.initial_cash
        equity_curve: list[float] = []
        daily_returns: list[float] = []
        total_turnover = 0.0

        start = self.strategy.warmup
        for i in range(start, n - 1):
            equity = cash + sum(pv.values())

            # 리밸런싱일: i 종가 기준 목표비중 산출 → 회전
            if (i - start) % cfg.rebalance_every == 0:
                weights = self.strategy.target_weights(data, i)
                turnover = 0.0
                new_pv = {s: 0.0 for s in symbols}
                for s in symbols:
                    target_val = weights.get(s, 0.0) * equity
                    turnover += abs(target_val - pv[s])
                    new_pv[s] = target_val
                fee = turnover * cost
                total_turnover += turnover
                invested = sum(new_pv.values())
                cash = equity - invested - fee
                pv = new_pv

            # i → i+1 수익률 적용
            for s in symbols:
                if pv[s] != 0.0:
                    r = data[s][i + 1].close / data[s][i].close
                    pv[s] *= r
            new_equity = cash + sum(pv.values())
            if equity > 0:
                daily_returns.append(new_equity / equity - 1.0)
            equity_curve.append(new_equity)

        metrics = _portfolio_metrics(
            equity_curve, daily_returns, cfg.initial_cash, total_turnover
        )
        return PortfolioResult(equity_curve, daily_returns, metrics)


def _portfolio_metrics(
    equity_curve: list[float],
    daily_returns: list[float],
    initial: float,
    total_turnover: float,
) -> dict:
    if not equity_curve:
        return {}
    final = equity_curve[-1]
    total_return = final / initial - 1.0
    years = len(equity_curve) / 252.0
    cagr = (final / initial) ** (1 / years) - 1.0 if years > 0 and final > 0 else 0.0

    if daily_returns:
        mean = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean) ** 2 for r in daily_returns) / len(daily_returns)
        std = math.sqrt(var)
        sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    peak = equity_curve[0]
    mdd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "turnover_x": total_turnover / initial,  # 누적 회전(자산 배수)
        "final_equity": final,
    }


def correlation(a: list[float], b: list[float]) -> float:
    """두 일간수익률 시계열의 상관계수(분산효과 확인용)."""
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return cov / math.sqrt(va * vb)
