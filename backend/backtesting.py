"""
Backtesting engine.

A strategy is a pure function of price history: given bars up to and including
day t, it returns the desired position for day t. The simulator walks the bars
in order and can only ever see the past, so results are not inflated by
look-ahead bias.

Everything here is deterministic: same prices in, same numbers out. That is what
makes a stored BacktestRun reproducible rather than merely recorded.

Two engines live here:

  * single-asset  — positions are a fraction of equity on one ticker
                    (1 = fully long, 0 = flat, >1 = levered).
  * portfolio     — weights across a universe of tickers, rebalanced
                    periodically, optionally market-neutral (short the
                    bottom of the cross-section).

STRATEGY_SPECS is the single source of truth for what parameters a strategy
takes. The API serves it to the UI so forms are generated rather than
hard-coded, it validates user input, and it is the schema the AI agent fills
in when it proposes a strategy to test.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# Charged on the traded notional each time the position changes. Without a cost
# model a crossover strategy looks far better than it is.
DEFAULT_COST_BPS = 10.0   # 0.10% commission+spread
DEFAULT_SLIPPAGE_BPS = 5.0  # 0.05% adverse fill


# --------------------------------------------------------------------------
# Indicator helpers
# --------------------------------------------------------------------------

def moving_average(series, window, ma_type="sma"):
    """Simple or exponential moving average."""
    if ma_type == "ema":
        return series.ewm(span=int(window), adjust=False).mean()
    return series.rolling(window=int(window)).mean()


def rsi(closes, period=14):
    """
    Relative Strength Index using Wilder's smoothing.

    Returns 0-100. The first `period` bars are left as NaN: the average gain
    and loss have not stabilised yet, and acting on them would be noise.
    """
    period = int(period)
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))

    # All-gain windows have no downside: RSI is 100 by definition. A flat
    # window (no move either way) is neutral rather than undefined.
    out[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    out.iloc[:period] = np.nan
    return out


def realized_volatility(closes, window):
    """Annualised standard deviation of daily returns over a rolling window."""
    daily = closes.pct_change()
    return daily.rolling(window=int(window)).std() * np.sqrt(TRADING_DAYS)


def _finalize(desired, warmup=0):
    """
    Turn a raw signal into a tradeable position series.

    Two guards, applied to every strategy so none can forget them:
      * warm-up bars are forced flat — an indicator that has not accumulated
        enough history yet is not a signal, it is noise.
      * the series is shifted one bar forward. A signal derived from day t's
        close can only be acted on from t+1. Without this the backtest trades
        on information it would not have had, which is the classic way to
        manufacture fake returns.
    """
    desired = desired.astype(float).fillna(0.0)
    if warmup > 0:
        desired.iloc[: min(int(warmup), len(desired))] = 0.0
    return desired.shift(1).fillna(0.0)


def _stateful_band(closes, enter_mask, exit_mask, valid_mask):
    """
    Walk an enter/exit rule that has hysteresis.

    Mean-reversion rules enter on one threshold and leave on a different one,
    so the position depends on whether we are already in a trade — it cannot
    be expressed as a single elementwise comparison.
    """
    pos = np.zeros(len(closes), dtype=float)
    holding = False
    for i in range(len(closes)):
        if not valid_mask.iloc[i]:
            holding = False
            pos[i] = 0.0
            continue
        if holding:
            if exit_mask.iloc[i]:
                holding = False
        elif enter_mask.iloc[i]:
            holding = True
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=closes.index)


# --------------------------------------------------------------------------
# Strategies: closes -> desired position per bar
# --------------------------------------------------------------------------

def strategy_buy_and_hold(closes):
    """Always invested. The benchmark every strategy has to beat."""
    return pd.Series(1.0, index=closes.index)


def strategy_ma_crossover(closes, fast=20, slow=50, ma_type="sma"):
    """
    Trend following. Long while the fast moving average is above the slow one.

    The oldest systematic rule there is: trends persist, so ride them and step
    aside when they break.
    """
    fast, slow = int(fast), int(slow)
    if fast >= slow:
        raise ValueError("fast window must be shorter than slow window")

    ma_fast = moving_average(closes, fast, ma_type)
    ma_slow = moving_average(closes, slow, ma_type)

    desired = (ma_fast > ma_slow).astype(float)
    # EMA has no NaN warm-up of its own, so mask explicitly for both types.
    return _finalize(desired, warmup=slow)


def strategy_rsi_reversion(closes, period=14, oversold=30.0, exit_level=50.0):
    """
    Mean reversion. Buy oversold, exit once the oscillator has recovered.

    The opposite thesis to trend following: short-horizon overshoots snap back.
    Entry and exit use different thresholds, so a position is held through the
    middle of the range rather than flickering around one level.
    """
    period = int(period)
    oversold, exit_level = float(oversold), float(exit_level)
    if oversold >= exit_level:
        raise ValueError("oversold level must be below the exit level")

    r = rsi(closes, period)
    positions = _stateful_band(
        closes,
        enter_mask=(r < oversold),
        exit_mask=(r >= exit_level),
        valid_mask=r.notna(),
    )
    return _finalize(positions, warmup=period)


def strategy_bollinger_reversion(closes, period=20, k=2.0):
    """
    Volatility-envelope mean reversion.

    Distance from the mean is measured in standard deviations rather than
    dollars, so the same rule adapts to calm and turbulent markets. Long when
    price closes below the lower band; exit when it returns to the mean.
    """
    period, k = int(period), float(k)

    mid = closes.rolling(window=period).mean()
    sd = closes.rolling(window=period).std()
    lower = mid - k * sd

    positions = _stateful_band(
        closes,
        enter_mask=(closes < lower),
        exit_mask=(closes >= mid),
        valid_mask=mid.notna() & sd.notna(),
    )
    return _finalize(positions, warmup=period)


def strategy_tsmom_vol_target(closes, lookback=252, vol_window=60,
                              target_vol=0.15, max_leverage=1.0):
    """
    Time-series momentum with volatility targeting — the managed-futures rule.

    Two separable decisions, which is what makes this different in kind from
    the rules above:

      * direction — long if the trailing `lookback` return is positive.
      * size      — scale the position so its *expected risk* is constant:
                    target_vol / realized_vol. Calm markets get a bigger
                    position, turbulent ones a smaller one.

    Sizing by risk rather than conviction is the line between a chart rule and
    a systematic strategy. Set max_leverage above 1 to allow gearing.
    """
    lookback, vol_window = int(lookback), int(vol_window)
    target_vol, max_leverage = float(target_vol), float(max_leverage)

    trailing_return = closes.pct_change(lookback)
    direction = (trailing_return > 0).astype(float)

    vol = realized_volatility(closes, vol_window).replace(0.0, np.nan)
    size = (target_vol / vol).clip(upper=max_leverage)

    desired = direction * size
    desired[trailing_return.isna() | vol.isna()] = 0.0
    return _finalize(desired, warmup=max(lookback, vol_window))


def strategy_cross_sectional_momentum(closes_df, lookback=252, skip=21,
                                      top_quantile=0.2, long_short=False,
                                      rebalance_days=21):
    """
    Cross-sectional momentum — the equity momentum factor. Multi-asset.

    Relative, not absolute: the question is not "is this going up" but "is it
    going up more than its peers". Rank the universe by trailing return, hold
    the top slice, rebalance periodically.

    `skip` omits the most recent month from the ranking window. Recent winners
    tend to reverse at short horizons, so the standard academic construction
    (Jegadeesh-Titman "12-1") measures momentum up to a month ago.

    With long_short the bottom slice is shorted, giving roughly zero net
    exposure. Longs and shorts are each sized to 0.5 gross so total exposure
    stays comparable to the long-only version.

    Returns a DataFrame of target weights per bar, not a single Series.
    """
    lookback, skip = int(lookback), int(skip)
    rebalance_days = max(1, int(rebalance_days))
    top_quantile, long_short = float(top_quantile), bool(long_short)

    if skip >= lookback:
        raise ValueError("skip must be shorter than lookback")
    if not 0 < top_quantile <= 0.5:
        raise ValueError("top_quantile must be between 0 and 0.5")

    # Return from t-lookback to t-skip, per asset.
    momentum = closes_df.shift(skip) / closes_df.shift(lookback) - 1.0

    weights = pd.DataFrame(0.0, index=closes_df.index, columns=closes_df.columns)
    n_pick = max(1, int(round(closes_df.shape[1] * top_quantile)))
    current = None

    for i in range(len(closes_df)):
        if i % rebalance_days != 0:
            if current is not None:
                weights.iloc[i] = current
            continue

        ranked = momentum.iloc[i].dropna().sort_values(ascending=False)
        if len(ranked) < 2:
            if current is not None:
                weights.iloc[i] = current
            continue

        k = min(n_pick, len(ranked) // 2 if long_short else len(ranked))
        k = max(1, k)
        row = pd.Series(0.0, index=closes_df.columns)

        if long_short and len(ranked) >= 2 * k:
            row[ranked.index[:k]] = 0.5 / k
            row[ranked.index[-k:]] = -0.5 / k
        else:
            row[ranked.index[:k]] = 1.0 / k

        weights.iloc[i] = row
        current = row

    # Same one-bar guard as the single-asset path: rankings computed from
    # today's close can only be traded tomorrow.
    return weights.shift(1).fillna(0.0)


# --------------------------------------------------------------------------
# Strategy registry
# --------------------------------------------------------------------------

STRATEGY_FUNCS = {
    "buy_and_hold": strategy_buy_and_hold,
    "ma_crossover": strategy_ma_crossover,
    "rsi_reversion": strategy_rsi_reversion,
    "bollinger_reversion": strategy_bollinger_reversion,
    "tsmom_vol_target": strategy_tsmom_vol_target,
    "cross_sectional_momentum": strategy_cross_sectional_momentum,
}

# Older runs were stored under these names; keep them resolvable so history
# and any saved proposal still points at a runnable strategy.
STRATEGY_ALIASES = {
    "ma20_50_crossover": "ma_crossover",
}

STRATEGY_SPECS = {
    "buy_and_hold": {
        "label": "Buy and hold",
        "family": "Baseline",
        "complexity": 0,
        "multi_asset": False,
        "summary": "Always invested. The benchmark every other strategy is measured against.",
        "params": {},
    },
    "ma_crossover": {
        "label": "Moving-average crossover",
        "family": "Trend following",
        "complexity": 1,
        "multi_asset": False,
        "summary": "Long while the fast average is above the slow one. Trends persist, so ride them.",
        "params": {
            "fast": {"type": "int", "default": 20, "min": 2, "max": 200,
                     "label": "Fast window", "help": "Bars in the fast moving average."},
            "slow": {"type": "int", "default": 50, "min": 3, "max": 400,
                     "label": "Slow window", "help": "Must be longer than the fast window."},
            "ma_type": {"type": "enum", "default": "sma", "options": ["sma", "ema"],
                        "label": "Average type", "help": "EMA reacts faster to recent prices."},
        },
    },
    "rsi_reversion": {
        "label": "RSI mean reversion",
        "family": "Mean reversion",
        "complexity": 2,
        "multi_asset": False,
        "summary": "Buy when RSI is oversold, exit once it recovers. Bets that overshoots snap back.",
        "params": {
            "period": {"type": "int", "default": 14, "min": 2, "max": 100,
                       "label": "RSI period", "help": "Lookback for the oscillator."},
            "oversold": {"type": "float", "default": 30.0, "min": 1.0, "max": 49.0,
                         "label": "Entry (oversold)", "help": "Go long below this RSI level."},
            "exit_level": {"type": "float", "default": 50.0, "min": 2.0, "max": 99.0,
                           "label": "Exit level", "help": "Close the position at or above this level."},
        },
    },
    "bollinger_reversion": {
        "label": "Bollinger-band reversion",
        "family": "Mean reversion",
        "complexity": 3,
        "multi_asset": False,
        "summary": "Long when price closes below the lower band; exit at the mean. Distance is measured in standard deviations, so it adapts to volatility.",
        "params": {
            "period": {"type": "int", "default": 20, "min": 3, "max": 200,
                       "label": "Period", "help": "Window for the mean and standard deviation."},
            "k": {"type": "float", "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.1,
                  "label": "Band width (σ)", "help": "How many standard deviations from the mean."},
        },
    },
    "tsmom_vol_target": {
        "label": "Time-series momentum + vol targeting",
        "family": "Systematic / quant",
        "complexity": 4,
        "multi_asset": False,
        "summary": "Direction from the trailing return, position size scaled to hit a constant risk target. Sizing by risk rather than conviction is what separates this from a chart rule.",
        "params": {
            "lookback": {"type": "int", "default": 252, "min": 20, "max": 756,
                         "label": "Trend lookback", "help": "Bars used to judge direction. 252 ≈ one year."},
            "vol_window": {"type": "int", "default": 60, "min": 10, "max": 252,
                           "label": "Volatility window", "help": "Bars used to measure realised volatility."},
            "target_vol": {"type": "float", "default": 0.15, "min": 0.02, "max": 0.60, "step": 0.01,
                           "label": "Target volatility", "help": "Annualised risk target, e.g. 0.15 = 15%."},
            "max_leverage": {"type": "float", "default": 1.0, "min": 0.1, "max": 3.0, "step": 0.1,
                             "label": "Max leverage", "help": "Cap on position size. 1.0 keeps it long/flat."},
        },
    },
    "cross_sectional_momentum": {
        "label": "Cross-sectional momentum",
        "family": "Systematic / quant",
        "complexity": 5,
        "multi_asset": True,
        "min_universe": 4,
        "summary": "Rank a universe by trailing return, hold the leaders, rebalance periodically. The equity momentum factor — relative strength, not absolute.",
        "params": {
            "lookback": {"type": "int", "default": 252, "min": 40, "max": 756,
                         "label": "Ranking lookback", "help": "Bars used to rank the universe."},
            "skip": {"type": "int", "default": 21, "min": 0, "max": 120,
                     "label": "Skip recent bars", "help": "Omit the most recent bars; recent winners tend to reverse."},
            "top_quantile": {"type": "float", "default": 0.2, "min": 0.05, "max": 0.5, "step": 0.05,
                             "label": "Top slice", "help": "Fraction of the universe to hold, e.g. 0.2 = top 20%."},
            "long_short": {"type": "bool", "default": False,
                           "label": "Market neutral", "help": "Also short the bottom slice for roughly zero net exposure."},
            "rebalance_days": {"type": "int", "default": 21, "min": 1, "max": 126,
                               "label": "Rebalance every", "help": "Bars between rebalances. 21 ≈ monthly."},
        },
    },
}

# Kept for backwards compatibility with callers that only need the names.
STRATEGIES = STRATEGY_FUNCS


def resolve_strategy(name):
    """Map a possibly-legacy strategy name onto a current one."""
    if name in STRATEGY_FUNCS:
        return name
    if name in STRATEGY_ALIASES:
        return STRATEGY_ALIASES[name]
    raise ValueError(
        f"Unknown strategy '{name}'. Known: {sorted(STRATEGY_FUNCS)}"
    )


def coerce_params(strategy, raw):
    """
    Validate and normalise parameters against a strategy's spec.

    Unknown keys are dropped, types are coerced, and values are clamped to the
    documented range. The result is what gets stored on the BacktestRun, so a
    run always records the parameters actually used rather than what was asked
    for. This is also the gate the AI agent's proposed spec passes through.
    """
    strategy = resolve_strategy(strategy)
    spec = STRATEGY_SPECS[strategy]
    raw = raw or {}
    out = {}

    for name, meta in spec["params"].items():
        value = raw.get(name, meta["default"])
        if value is None or value == "":
            value = meta["default"]

        try:
            if meta["type"] == "int":
                value = int(round(float(value)))
            elif meta["type"] == "float":
                value = float(value)
            elif meta["type"] == "bool":
                value = value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes")
            elif meta["type"] == "enum" and value not in meta["options"]:
                value = meta["default"]
        except (TypeError, ValueError):
            raise ValueError(f"{meta['label']} must be a number")

        if meta["type"] in ("int", "float"):
            if "min" in meta:
                value = max(meta["min"], value)
            if "max" in meta:
                value = min(meta["max"], value)

        out[name] = value

    return strategy, out


def required_bars(strategy, params):
    """
    Minimum bars of history before a strategy can produce a signal.

    Used to warn rather than silently return a flat line when the requested
    window is shorter than the indicator's warm-up.
    """
    strategy = resolve_strategy(strategy)
    p = params or {}
    if strategy == "ma_crossover":
        return int(p.get("slow", 50)) + 1
    if strategy == "rsi_reversion":
        return int(p.get("period", 14)) * 2
    if strategy == "bollinger_reversion":
        return int(p.get("period", 20)) + 1
    if strategy == "tsmom_vol_target":
        return max(int(p.get("lookback", 252)), int(p.get("vol_window", 60))) + 1
    if strategy == "cross_sectional_momentum":
        return int(p.get("lookback", 252)) + int(p.get("rebalance_days", 21))
    return 2


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
# Single-asset simulator
# --------------------------------------------------------------------------

def simulate(closes, positions, starting_cash=10000.0,
             cost_bps=DEFAULT_COST_BPS, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """
    Walk the bars, applying the desired position and charging costs on changes.

    Returns (equity_array, daily_returns, trades). Positions are fractions of
    equity (1 = fully invested, 0 = flat), so a strategy that sizes by risk can
    ask for 0.6 or 1.4 and the arithmetic already holds.
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

        # A trade is open while the position is non-zero. Size changes within
        # an open position (vol targeting does this constantly) are costed
        # above but do not open or close a trade.
        if prev_position == 0 and position != 0:
            open_trade = {"entry_date": date, "entry_price": price}
        elif prev_position != 0 and position == 0 and open_trade:
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


# --------------------------------------------------------------------------
# Portfolio simulator (multi-asset)
# --------------------------------------------------------------------------

def simulate_portfolio(closes_df, weights_df, starting_cash=10000.0,
                       cost_bps=DEFAULT_COST_BPS, slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """
    Walk the bars holding a basket, charging costs on rebalance turnover.

    Weights are fractions of equity per asset and may be negative (short).
    Turnover is summed across every name that changed, so a full rebalance of
    the basket is charged for each leg rather than once.
    """
    closes_df = closes_df.astype(float)
    returns = closes_df.pct_change().fillna(0.0)
    cost_rate = (cost_bps + slippage_bps) / 10000.0

    equity = [float(starting_cash)]
    prev_w = pd.Series(0.0, index=closes_df.columns)
    open_trades = {}
    trades = []

    for i in range(1, len(closes_df)):
        w = weights_df.iloc[i]

        portfolio_return = float((w * returns.iloc[i]).sum())
        gross = equity[-1] * (1 + portfolio_return)

        turnover = float((w - prev_w).abs().sum())
        equity.append(gross - gross * turnover * cost_rate)

        date = str(closes_df.index[i].date())

        # Track each name's round trip so win rate stays meaningful for a basket.
        for ticker in closes_df.columns:
            before, after = float(prev_w.get(ticker, 0.0)), float(w.get(ticker, 0.0))
            if before == 0 and after == 0:
                continue
            price = float(closes_df[ticker].iloc[i])
            if before == 0 and after != 0:
                open_trades[ticker] = {
                    "ticker": ticker, "entry_date": date, "entry_price": price,
                    "side": "long" if after > 0 else "short",
                }
            elif before != 0 and after == 0 and ticker in open_trades:
                trade = open_trades.pop(ticker)
                raw = (price / trade["entry_price"] - 1) * 100
                trades.append({**trade, "exit_date": date, "exit_price": price,
                               "pnl_pct": raw if trade["side"] == "long" else -raw})

        prev_w = w

    last_date = str(closes_df.index[-1].date())
    for ticker, trade in open_trades.items():
        price = float(closes_df[ticker].iloc[-1])
        raw = (price / trade["entry_price"] - 1) * 100
        trades.append({**trade, "exit_date": last_date, "exit_price": price,
                       "pnl_pct": raw if trade["side"] == "long" else -raw,
                       "open_at_end": True})

    equity_arr = np.asarray(equity, dtype=float)
    strategy_returns = pd.Series(equity_arr).pct_change().fillna(0.0)
    return equity_arr, strategy_returns, trades


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------

def _build_result(strategy, params, index, equity, returns, trades,
                  bench_equity, bench_returns, starting_cash,
                  cost_bps, slippage_bps, universe):
    curve = [
        {
            "date": str(index[i].date()),
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
        "strategy_label": STRATEGY_SPECS[strategy]["label"],
        "params": params,
        "universe": universe,
        "start_date": str(index[0].date()),
        "end_date": str(index[-1].date()),
        "bars": len(index),
        "starting_cash": starting_cash,
        "cost_bps": cost_bps,
        "slippage_bps": slippage_bps,
        "metrics": metrics,
        "benchmark_metrics": bench_metrics,
        "equity_curve": curve,
        "trades": trades,
    }


def run_backtest(closes, strategy="ma_crossover", params=None,
                 starting_cash=10000.0, cost_bps=DEFAULT_COST_BPS,
                 slippage_bps=DEFAULT_SLIPPAGE_BPS, ticker=None):
    """
    Run one single-asset strategy over one price series, against buy-and-hold.

    `closes` is a pandas Series of closing prices indexed by date.
    """
    strategy, params = coerce_params(strategy, params)
    if STRATEGY_SPECS[strategy]["multi_asset"]:
        raise ValueError(f"{STRATEGY_SPECS[strategy]['label']} needs a universe of tickers")

    if len(closes) < 2:
        raise ValueError("Not enough price history to backtest")

    positions = STRATEGY_FUNCS[strategy](closes, **params)
    equity, returns, trades = simulate(
        closes, positions, starting_cash, cost_bps, slippage_bps
    )

    # Benchmark: same cash, same window, always invested. Beating the market is
    # the bar, not merely making money.
    bench_positions = strategy_buy_and_hold(closes)
    bench_equity, bench_returns, _ = simulate(
        closes, bench_positions, starting_cash, cost_bps, slippage_bps
    )

    return _build_result(
        strategy, params, closes.index, equity, returns, trades,
        bench_equity, bench_returns, starting_cash, cost_bps, slippage_bps,
        [ticker] if ticker else [],
    )


def run_portfolio_backtest(closes_df, strategy="cross_sectional_momentum",
                           params=None, starting_cash=10000.0,
                           cost_bps=DEFAULT_COST_BPS,
                           slippage_bps=DEFAULT_SLIPPAGE_BPS):
    """
    Run a multi-asset strategy over a universe, against an equal-weight hold.

    `closes_df` is a DataFrame of closing prices, dates by ticker.
    """
    strategy, params = coerce_params(strategy, params)
    if not STRATEGY_SPECS[strategy]["multi_asset"]:
        raise ValueError(f"{STRATEGY_SPECS[strategy]['label']} runs on a single ticker")

    if closes_df.shape[0] < 2:
        raise ValueError("Not enough price history to backtest")
    if closes_df.shape[1] < 2:
        raise ValueError("A cross-sectional strategy needs at least two tickers")

    weights = STRATEGY_FUNCS[strategy](closes_df, **params)
    equity, returns, trades = simulate_portfolio(
        closes_df, weights, starting_cash, cost_bps, slippage_bps
    )

    # Benchmark: equal-weight the whole universe and hold it. The strategy has
    # to beat owning everything, not just make money.
    n = closes_df.shape[1]
    bench_weights = pd.DataFrame(1.0 / n, index=closes_df.index, columns=closes_df.columns)
    bench_equity, bench_returns, _ = simulate_portfolio(
        closes_df, bench_weights, starting_cash, cost_bps, slippage_bps
    )

    return _build_result(
        strategy, params, closes_df.index, equity, returns, trades,
        bench_equity, bench_returns, starting_cash, cost_bps, slippage_bps,
        list(closes_df.columns),
    )
