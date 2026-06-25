"""백테스트 실행 데모.

외부 키/네트워크 없이 합성 데이터로 하네스 동작을 검증한다.
실데이터 연동 시 datafeed.load_csv 또는 토스 캔들 적재로 교체.

실행:
  python -m backtest.run_backtest
  python -m backtest.run_backtest --symbols AAA BBB CCC --days 1000 --ai-gate
"""

from __future__ import annotations

import argparse

from .datafeed import generate_synthetic
from .engine import Backtester, BacktestConfig
from .strategy import DonchianBreakout, StrategyParams


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> None:
    ap = argparse.ArgumentParser(description="돈치안 스윙 전략 백테스트(합성 데이터)")
    ap.add_argument("--symbols", nargs="+", default=["AAA", "BBB", "CCC", "DDD", "EEE"])
    ap.add_argument("--days", type=int, default=750)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--ai-gate", action="store_true", help="뉴스/AI 게이트 활성(데모: NullScorer)")
    args = ap.parse_args()

    data = generate_synthetic(args.symbols, days=args.days, seed=args.seed)

    params = StrategyParams()
    config = BacktestConfig(use_ai_gate=args.ai_gate)
    bt = Backtester(strategy=DonchianBreakout(params), params=params, config=config)
    result = bt.run(data)
    m = result.metrics

    print("=" * 56)
    print(f" 돈치안 스윙 백테스트 (합성 데이터, {len(args.symbols)}종목 x {args.days}일)")
    print("=" * 56)
    print(f"  총수익률      : {_pct(m['total_return'])}")
    print(f"  CAGR          : {_pct(m['cagr'])}")
    print(f"  Sharpe        : {m['sharpe']:.2f}")
    print(f"  최대낙폭(MDD) : {_pct(m['max_drawdown'])}")
    print(f"  거래횟수      : {m['num_trades']}")
    print(f"  승률          : {_pct(m['win_rate'])}")
    pf = m["profit_factor"]
    print(f"  손익비(PF)    : {'inf' if pf == float('inf') else f'{pf:.2f}'}")
    print(f"  최종자산      : {m['final_equity']:,.0f}")
    print("-" * 56)
    print("  ※ 합성 데이터 결과이므로 수익성 근거가 아니라 하네스 검증용입니다.")
    print("  ※ 실데이터(토스 일봉) 연동 후 파라미터 튜닝/검증이 다음 단계.")


if __name__ == "__main__":
    main()
