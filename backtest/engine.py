"""포트폴리오 백테스트 엔진.

실행 모델(봇 현실과 일치):
- 신호는 i일 종가 확정 후 산출.
- 체결은 i+1일 시가에 가정(look-ahead 방지).
- 토스에 stop 주문이 없으므로 손절도 종가 기준 폴링 → 익일 시가 청산.

주의: 본 엔진은 인덱스 정렬(모든 심볼 동일 길이)을 가정한다.
실데이터 연동 시에는 날짜 기준 정렬로 교체해야 한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .datafeed import Bar
from .strategy import AIScorer, NullScorer, Strategy, StrategyParams


@dataclass
class Position:
    qty: float
    entry_price: float
    stop_price: float
    entry_date: str


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    qty: float
    reason: str

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.qty

    @property
    def ret(self) -> float:
        return (self.exit_price / self.entry_price) - 1.0


@dataclass
class BacktestConfig:
    initial_cash: float = 100_000.0
    commission_bps: float = 5.0   # 체결 명목가 대비 수수료(bps)
    slippage_bps: float = 5.0     # 체결 슬리피지(bps)
    use_ai_gate: bool = False     # 뉴스/AI 오버레이 사용 여부


@dataclass
class BacktestResult:
    equity_curve: list[float] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _fill_price(ref: float, side: str, slippage_bps: float) -> float:
    adj = slippage_bps / 10_000.0
    return ref * (1 + adj) if side == "buy" else ref * (1 - adj)


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        params: StrategyParams,
        config: BacktestConfig | None = None,
        scorer: AIScorer | None = None,
    ):
        self.strategy = strategy
        self.params = params
        self.config = config or BacktestConfig()
        self.scorer = scorer or NullScorer()

    def run(self, data: dict[str, list[Bar]]) -> BacktestResult:
        cfg = self.config
        symbols = list(data.keys())
        n = min(len(bars) for bars in data.values())
        cash = cfg.initial_cash
        positions: dict[str, Position] = {}
        entry_atr: dict[str, float] = {}
        trades: list[Trade] = []
        equity_curve: list[float] = []

        comm = cfg.commission_bps / 10_000.0

        # i: 신호 산출일, i+1: 체결일
        for i in range(n - 1):
            # ---- 1) 청산/손절 결정 (보유 종목) ----
            for sym in list(positions.keys()):
                bars = data[sym]
                pos = positions[sym]
                sig = self.strategy.evaluate(bars, i, True, entry_atr.get(sym))
                close_i = bars[i].close
                stop_hit = close_i <= pos.stop_price
                if sig.exit or stop_hit:
                    fill = _fill_price(bars[i + 1].open, "sell", cfg.slippage_bps)
                    cash += fill * pos.qty * (1 - comm)
                    trades.append(
                        Trade(
                            symbol=sym,
                            entry_date=pos.entry_date,
                            exit_date=bars[i + 1].date,
                            entry_price=pos.entry_price,
                            exit_price=fill,
                            qty=pos.qty,
                            reason="stop" if stop_hit and not sig.exit else "exit",
                        )
                    )
                    del positions[sym]
                    entry_atr.pop(sym, None)

            # ---- 2) 진입 결정 (빈 슬롯이 있으면) ----
            # 현재 자산 평가(종가 i 기준)로 사이징
            equity = cash + sum(
                positions[s].qty * data[s][i].close for s in positions
            )
            for sym in symbols:
                if sym in positions:
                    continue
                if len(positions) >= self.params.max_positions:
                    break
                bars = data[sym]
                sig = self.strategy.evaluate(bars, i, False, None)
                if not sig.enter or sig.stop_distance is None or sig.ref_price is None:
                    continue

                # 뉴스/AI 게이트(옵션): 강한 악재면 진입 스킵
                if cfg.use_ai_gate:
                    score = self.scorer.score(
                        sym, bars[i].date, {"closes": [b.close for b in bars[: i + 1]]}
                    )
                    if score.direction == "bearish" and score.materiality >= 0.6:
                        continue

                # 리스크 기반 사이징
                risk_dollars = equity * self.params.risk_per_trade
                if sig.stop_distance <= 0:
                    continue
                qty = risk_dollars / sig.stop_distance
                fill = _fill_price(bars[i + 1].open, "buy", cfg.slippage_bps)
                notional = qty * fill
                # 비중 상한 + 가용현금 제약
                cap = min(self.params.max_weight * equity, cash / (1 + comm))
                if notional > cap:
                    qty = cap / fill
                    notional = qty * fill
                if qty <= 0 or notional < 1:
                    continue
                cost = notional * (1 + comm)
                if cost > cash:
                    continue
                cash -= cost
                positions[sym] = Position(
                    qty=qty,
                    entry_price=fill,
                    stop_price=fill - sig.stop_distance,
                    entry_date=bars[i + 1].date,
                )
                entry_atr[sym] = sig.stop_distance / self.params.atr_stop_mult

            # ---- 3) 자산 평가 기록 (체결일 i+1 종가) ----
            equity_eod = cash + sum(
                positions[s].qty * data[s][i + 1].close for s in positions
            )
            equity_curve.append(equity_eod)

        # 잔여 포지션 청산가는 마지막 종가로 평가
        last = n - 1
        final_equity = cash + sum(
            positions[s].qty * data[s][last].close for s in positions
        )
        metrics = _compute_metrics(equity_curve, trades, cfg.initial_cash, final_equity)
        return BacktestResult(equity_curve=equity_curve, trades=trades, metrics=metrics)


def _compute_metrics(
    equity_curve: list[float],
    trades: list[Trade],
    initial: float,
    final: float,
) -> dict:
    if not equity_curve:
        return {}
    total_return = final / initial - 1.0
    days = len(equity_curve)
    years = days / 252.0
    cagr = (final / initial) ** (1 / years) - 1.0 if years > 0 and final > 0 else 0.0

    # 일간 수익률
    rets = []
    for a, b in zip(equity_curve[:-1], equity_curve[1:]):
        if a > 0:
            rets.append(b / a - 1.0)
    if rets:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        std = math.sqrt(var)
        sharpe = (mean / std * math.sqrt(252)) if std > 0 else 0.0
    else:
        sharpe = 0.0

    # 최대낙폭
    peak = equity_curve[0]
    mdd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_win = sum(t.pnl for t in wins)
    gross_loss = -sum(t.pnl for t in losses)
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    return {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "num_trades": len(trades),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "final_equity": final,
    }
