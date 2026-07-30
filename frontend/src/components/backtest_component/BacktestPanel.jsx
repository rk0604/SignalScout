import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";
import api from "../../api/client";
import "./backtest.css";

/*
 * Backtest panel: run a strategy over a ticker and compare it to buy-and-hold.
 *
 * Two series (strategy vs benchmark) on ONE value axis — both are equity in
 * dollars from the same starting cash, so they share a scale. A legend is
 * present because there is more than one series.
 */

const STRATEGIES = [
  { id: "ma20_50_crossover", label: "MA20/50 crossover" },
  { id: "buy_and_hold", label: "Buy and hold" },
];

const fmt = (v, digits = 2) =>
  v == null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });

const signed = (v, digits = 2) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`);

// "Better" runs in different directions per metric. Lower volatility is better,
// but max drawdown is a negative number, so a HIGHER (shallower) value wins.
const compareTone = (strategyVal, benchVal, lowerIsBetter = false) => {
  if (strategyVal == null || benchVal == null) return "tw-flat";
  if (strategyVal === benchVal) return "tw-flat";
  const wins = lowerIsBetter ? strategyVal < benchVal : strategyVal > benchVal;
  return wins ? "tw-up" : "tw-down";
};

export default function BacktestPanel() {
  const [ticker, setTicker] = useState("");
  const [strategy, setStrategy] = useState("ma20_50_crossover");
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const runBacktest = async (e) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.post("/backtest", {
        ticker: ticker.trim().toUpperCase(),
        strategy,
      });
      setResult(response.data);
    } catch (err) {
      setError(err.response?.data?.error || "Backtest failed");
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  };

  const m = result?.metrics;
  const b = result?.benchmark_metrics;

  // Metric rows: [label, key, lowerIsBetter].
  // Max drawdown is negative, so higher (shallower) is the better value.
  const rows = [
    ["Total return %", "total_return_pct", false],
    ["CAGR %", "cagr_pct", false],
    ["Volatility %", "volatility_pct", true],
    ["Sharpe", "sharpe", false],
    ["Sortino", "sortino", false],
    ["Max drawdown %", "max_drawdown_pct", false],
    ["Final equity", "final_equity", false],
  ];

  return (
    <section className="backtest-panel">
      <header className="backtest-header">
        <h3 className="backtest-title">Backtest</h3>
        {result && (
          <span className="tw-label backtest-runid" title={`Run ${result.backtest_run_id}`}>
            run {result.backtest_run_id.slice(0, 8)}
          </span>
        )}
      </header>

      <form className="backtest-form" onSubmit={runBacktest}>
        <input
          className="backtest-input tw-num"
          type="search"
          placeholder="TICKER"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          aria-label="Ticker to backtest"
        />
        <select
          className="backtest-select"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          aria-label="Strategy"
        >
          {STRATEGIES.map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
        <button className="backtest-run" type="submit" disabled={isLoading}>
          {isLoading ? "Running…" : "Run"}
        </button>
      </form>

      {error && <p className="backtest-error tw-label">{error}</p>}

      {result && (
        <>
          <p className="tw-label backtest-window">
            {result.ticker} · {result.start_date} → {result.end_date} · {result.bars} bars ·
            {" "}costs {result.cost_bps + result.slippage_bps}bps
          </p>

          <div className="backtest-verdict">
            <span className={m.beat_benchmark ? "tw-up" : "tw-down"}>
              {m.beat_benchmark ? "▲ Beat" : "▼ Lost to"} buy-and-hold
            </span>
            <span className={`tw-num ${m.excess_return_pct >= 0 ? "tw-up" : "tw-down"}`}>
              {signed(m.excess_return_pct)}%
            </span>
          </div>

          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={result.equity_curve} margin={{ top: 10, right: 16, left: 8, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: "#8A929E" }}
                minTickGap={40}
                tickMargin={6}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#8A929E" }}
                width={62}
                tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`}
              />
              <Tooltip
                contentStyle={{ background: "#16191D", border: "1px solid #23262B", borderRadius: 3, fontSize: 12 }}
                labelStyle={{ color: "#8A929E" }}
                formatter={(v, name) => [`$${fmt(v)}`, name]}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: "#8A929E" }} />
              <Line type="monotone" dataKey="equity" name="Strategy" stroke="#3987e5" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="benchmark" name="Buy & hold" stroke="#8A929E" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            </LineChart>
          </ResponsiveContainer>

          <div className="metrics-scroll">
            <table className="metrics-table">
              <thead>
                <tr>
                  <th className="tw-label">Metric</th>
                  <th className="tw-label num">Strategy</th>
                  <th className="tw-label num">Buy &amp; hold</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, key, lower]) => (
                  <tr key={key}>
                    <td>{label}</td>
                    <td className={`tw-num num ${compareTone(m[key], b[key], lower)}`}>{fmt(m[key])}</td>
                    <td className="tw-num num tw-flat">{fmt(b[key])}</td>
                  </tr>
                ))}
                <tr>
                  <td>Trades</td>
                  <td className="tw-num num">{m.trade_count}</td>
                  <td className="tw-num num tw-flat">1</td>
                </tr>
                <tr>
                  <td>Win rate %</td>
                  <td className="tw-num num">{fmt(m.win_rate_pct)}</td>
                  <td className="tw-num num tw-flat">—</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="tw-label backtest-disclaimer">
            Past performance does not predict future results. Costs modelled at
            {" "}{result.cost_bps}bps commission + {result.slippage_bps}bps slippage.
          </p>
        </>
      )}
    </section>
  );
}
