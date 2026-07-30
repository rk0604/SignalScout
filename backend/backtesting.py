"""
Backtesting engine.

A strategy is a pure function of price history: given bars up to and including
day t, it returns the desired position for day t. The simulator walks the bars
in order and can only ever see the past, so results are not inflated by
look-ahead bias.

Everything here is deterministic: same prices in, same numbers out. That is what
makes a stored BacktestRun reproducible rather than merely recorded.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Charged on the traded notional each time the position changes. Without a cost
# model a crossover strategy looks far better than it is.
DEFAULT_COST_BPS = 10.0   # 0.10% commission+spread
DEFAULT_SLIPPAGE_BPS = 5.0  # 0.05% adverse fill


# --------------------------------------------------------------------------
# Strategies: closes -> desired position per bar (1 = long, 0 = flat)
# --------------------------------------------------------------------------

def strategy_ma_crossover(closes, short_window=20, long_window=50):
    """
    Long while the short moving average is above the long one, flat otherwise.

    The signal is shifted forward one bar: the crossover is only observable
    once day t has closed, so the position it implies can only be held from
    t+1. Without the shift the backtest trades on information it would not have
    had, which is the classic way to manufacture fake returns.
    """
    ma_short = closes.rolling(window=short_window).mean()
    ma_long = closes.rolling(window=long_window).mean()

    desired = (ma_short > ma_long).astype(float)
    desired[ma_long.isna()] = 0.0  # no position until both averages exist
    return desired.shift(1).fillna(0.0)


def strategy_buy_and_hold(closes):
    """Always invested. The benchmark every strategy has to beat."""
    return pd.Series(1.0, index=closes.index)


STRATEGIES = {
    "ma20_50_crossover": strategy_ma_crossover,
    "buy_and_hold": strategy_buy_and_hold,
}


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def max_drawdown(equity):
    """Largest peak-to-trough decline, as a negative percentage."""
    if len(equity) == 0:
        return 0.0
    running_peak = np.maximum.accumulate(equity)
    drawdowns = (equity - running_peak) / running_peak
    return float(drawdowns.min() * 100)


def sharpe_ratio(returns, risk_free_rate=0.0):
    """Annualised excess return per unit of total volatility."""
    if len(returns) < 2:
        return None
    excess = returns - (risk_free_rate / TRADING_DAYS)
    sd = excess.std()
    if sd == 0 or np.isnan(sd):
        return None
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns, risk_free_rate=0.0):
    """
    Like Sharpe, but only downside deviation is treated as risk.

    Upside volatility is not something an investor wants penalised.
    """
    if len(returns) < 2:
        return None
    excess = returns - (risk_free_rate / TRADING_DAYS)
    downside = excess[excess < 0]
    if len(downside) == 0:
        return None  # no losing days in the window
    dd = downside.std()
    if dd == 0 or np.isnan(dd):
        return None
    return float(excess.mean() / dd * np.sqrt(TRADING_DAYS))


def cagr(equity, num_days):
    """Compound annual growth rate implied by the equity curve."""
    if len(equity) < 2 or num_days <= 0 or equity[0] <= 0:
        return None
    years = num_days / TRADING_DAYS
    if years <= 0:
        return None
    total_growth = equity[-1] / equity[0]
    if total_growth <= 0:
        return None
    return float((total_growth ** (1 / years) - 1) * 100)


def compute_metrics(equity, returns, trades):
    """Roll an equity curve and its returns into the headline numbers."""
    equity = np.asarray(equity, dtype=float)
    total_return = float((equity[-1] / equity[0] - 1) * 100) if len(equity) > 1 else 0.0

    wins = [t for t in trades if t.get("pnl_pct") is not None and t["pnl_pct"] > 0]
    closed = [t for t in trades if t.get("pnl_pct") is not None]

    return {
        "total_return_pct": total_return,
        "cagr_pct": cagr(equity, len(equity)),
        "volatility_pct": float(returns.std() * np.sqrt(TRADING_DAYS) * 100) if len(returns) > 1 else None,
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": max_drawdown(equity),
        "trade_count": len(closed),
        "win_rate_pct": (len(wins) / len(closed) * 100) if closed else None,
        "final_equity": float(equity[-1]),
    }


# --------------------------------------------------------------------------
# Simulator
# --------------------------------------------------------------------------

def simulate(closes, positions, starting_cash=10000.0,
             cost_bps=DEFAULT_COST_BPS, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """
    Walk the bars, applying the desired position and charging costs on changes.

    Returns (equity_array, daily_returns, trades). Positions are fractions of
    equity (1 = fully invested, 0 = flat), so this models a single-asset
    long/flat strategy rather than sizing or leverage.
    """
    closes = closes.astype(float)
    daily_returns = closes.pct_change().fillna(0.0)

    equity = [float(starting_cash)]
    trades = []
    open_trade = None
    prev_position = 0.0
    cost_rate = (cost_bps + slippage_bps) / 10000.0

    for i in range(1, len(closes)):
        position = float(positions.iloc[i])

        # Return earned today is yesterday's position applied to today's move.
        gross = equity[-1] * (1 + position * daily_returns.iloc[i])

        # Charge on the traded notional when the position changes.
        turnover = abs(position - prev_position)
        cost = gross * turnover * cost_rate
        equity.append(gross - cost)

        price = float(closes.iloc[i])
        date = str(closes.index[i].date())

        if position > prev_position:          # entering
            open_trade = {"entry_date": date, "entry_price": price}
        elif position < prev_position and open_trade:  # exiting
            pnl_pct = (price / open_trade["entry_price"] - 1) * 100
            trades.append({**open_trade, "exit_date": date, "exit_price": price,
                           "pnl_pct": pnl_pct})
            open_trade = None

        prev_position = position

    # A position still open at the end is marked to the last price.
    if open_trade:
        last_price = float(closes.iloc[-1])
        trades.append({**open_trade, "exit_date": str(closes.index[-1].date()),
                       "exit_price": last_price,
                       "pnl_pct": (last_price / open_trade["entry_price"] - 1) * 100,
                       "open_at_end": True})

    equity_arr = np.asarray(equity, dtype=float)
    strategy_returns = pd.Series(equity_arr).pct_change().fillna(0.0)
    return equity_arr, strategy_returns, trades


def run_backtest(closes, strategy="ma20_50_crossover", params=None,
                 starting_cash=10000.0, cost_bps=DEFAULT_COST_BPS,
                 slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """
    Run one strategy over one price series and benchmark it against buy-and-hold.

    `closes` is a pandas Series of closing prices indexed by date.
    Returns metrics, the benchmark's metrics, the equity curve and the trades.
    """
    params = params or {}
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'. Known: {sorted(STRATEGIES)}")

    if len(closes) < 2:
        raise ValueError("Not enough price history to backtest")

    positions = STRATEGIES[strategy](closes, **params)
    equity, returns, trades = simulate(
        closes, positions, starting_cash, cost_bps, slippage_bps
    )

    # Benchmark: same cash, same window, always invested. Beating the market is
    # the bar, not merely making money.
    bench_positions = strategy_buy_and_hold(closes)
    bench_equity, bench_returns, _ = simulate(
        closes, bench_positions, starting_cash, cost_bps, slippage_bps
    )

    curve = [
        {
            "date": str(closes.index[i].date()),
            "equity": round(float(equity[i]), 2),
            "benchmark": round(float(bench_equity[i]), 2),
        }
        for i in range(len(equity))
    ]

    metrics = compute_metrics(equity, returns, trades)
    bench_metrics = compute_metrics(bench_equity, bench_returns, [])

    metrics["excess_return_pct"] = (
        metrics["total_return_pct"] - bench_metrics["total_return_pct"]
    )
    metrics["beat_benchmark"] = metrics["excess_return_pct"] > 0

    return {
        "strategy": strategy,
        "params": params,
        "start_date": str(closes.index[0].date()),
        "end_date": str(closes.index[-1].date()),
        "bars": len(closes),
        "starting_cash": starting_cash,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "metrics": metrics,
        "benchmark_metrics": bench_metrics,
        "equity_curve": curve,
        "trades": trades,
    }
