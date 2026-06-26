"""멀티 전략 비교 데모.

돈치안(추세) · 크로스섹셔널 모멘텀(팩터) · 통계적 페어(평균회귀)를
같은 합성 데이터로 백테스트하고, 일간수익률 상관으로 분산효과를 확인한다.
마지막에 역변동성(inverse-vol) 가중으로 단순 결합한 결과를 보여준다.

실행:
  python -m backtest.run_quant
"""

from __future__ import annotations

import math

from .datafeed import generate_synthetic
from .engine import Backtester, BacktestConfig
from .portfolio_engine import PortfolioConfig, WeightBacktester, correlation
from .quant import CrossSectionalMomentum, PairsMeanReversion
from .strategy import DonchianBreakout, StrategyParams


def _pct(x: float) -> str:
    return f"{x * 100:6.2f}%"


def _returns_from_equity(curve: list[float]) -> list[float]:
    out = []
    for a, b in zip(curve[:-1], curve[1:]):
        if a > 0:
            out.append(b / a - 1.0)
    return out


def _stat_line(name: str, m: dict) -> str:
    return (
        f"  {name:<10} | 수익 {_pct(m['total_return'])} | CAGR {_pct(m['cagr'])} "
        f"| Sharpe {m['sharpe']:5.2f} | MDD {_pct(m['max_drawdown'])}"
    )


def main() -> None:
    symbols = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    days = 900
    data = generate_synthetic(symbols, days=days, seed=20240601)

    # ── 전략 1: 돈치안 추세추종 (per-symbol 엔진)
    params = StrategyParams()
    don = Backtester(DonchianBreakout(params), params, BacktestConfig())
    r_don = don.run(data)
    don_rets = _returns_from_equity(r_don.equity_curve)

    # ── 전략 2: 크로스섹셔널 모멘텀 (비중 엔진)
    mom = WeightBacktester(
        CrossSectionalMomentum(lookback=60, top_k=3, trend_ma=200),
        PortfolioConfig(rebalance_every=5),
    )
    r_mom = mom.run(data)

    # ── 전략 3: 통계적 페어 (롱온리, 저평가 다리)
    pair = WeightBacktester(
        PairsMeanReversion("AAA", "BBB", window=60, entry_z=2.0, allow_short=False),
        PortfolioConfig(rebalance_every=1),
    )
    r_pair = pair.run(data)

    print("=" * 70)
    print(f" 멀티 전략 백테스트 비교 (합성 데이터, {len(symbols)}종목 x {days}일)")
    print("=" * 70)
    print(_stat_line("돈치안", r_don.metrics))
    print(_stat_line("모멘텀", r_mom.metrics))
    print(_stat_line("페어", r_pair.metrics))

    # ── 일간수익률 상관(분산효과 확인): 길이 맞춰 꼬리 정렬
    series = {"돈치안": don_rets, "모멘텀": r_mom.daily_returns, "페어": r_pair.daily_returns}
    L = min(len(s) for s in series.values())
    series = {k: v[-L:] for k, v in series.items()}
    print("\n  [일간수익률 상관행렬] (낮을수록 분산효과 큼)")
    names = list(series)
    print("           " + "".join(f"{n:>8}" for n in names))
    for a in names:
        row = "".join(f"{correlation(series[a], series[b]):>8.2f}" for b in names)
        print(f"    {a:<8}{row}")

    # ── 역변동성 결합 (간단 데모)
    def vol(x: list[float]) -> float:
        m = sum(x) / len(x)
        return math.sqrt(sum((v - m) ** 2 for v in x) / len(x)) or 1e-9

    inv = {k: 1.0 / vol(v) for k, v in series.items()}
    tot = sum(inv.values())
    w = {k: inv[k] / tot for k in inv}
    combo = [sum(w[k] * series[k][t] for k in names) for t in range(L)]
    cmean = sum(combo) / L
    cstd = math.sqrt(sum((v - cmean) ** 2 for v in combo) / L) or 1e-9
    csharpe = cmean / cstd * math.sqrt(252)
    print(f"\n  [역변동성 결합] 비중={{{', '.join(f'{k}:{w[k]:.0%}' for k in names)}}}")
    print(f"    결합 Sharpe ≈ {csharpe:5.2f}  (개별 대비 개선되면 분산효과 입증)")
    print("-" * 70)
    print("  ※ 합성 데이터라 수익성 근거가 아니라 멀티전략 하네스/분산효과 검증용입니다.")


if __name__ == "__main__":
    main()
