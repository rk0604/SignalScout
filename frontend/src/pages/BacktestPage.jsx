import { useState, useEffect } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import api from "../api/client";
import { usd, money, signedPct } from "../lib/format";
import "./pages.css";

const STRATEGIES = [
  { id: "ma20_50_crossover", label: "MA20/50 crossover" },
  { id: "buy_and_hold", label: "Buy and hold" },
];

/* "Better" runs in different directions per metric: lower volatility wins, but
   max drawdown is negative so a shallower (higher) value wins. */
const ROWS = [
  ["Total return", "total_return_pct", "%", false],
  ["CAGR", "cagr_pct", "%", false],
  ["Volatility", "volatility_pct", "%", true],
  ["Sharpe", "sharpe", "", false],
  ["Sortino", "sortino", "", false],
  ["Max drawdown", "max_drawdown_pct", "%", false],
  ["Final equity", "final_equity", "$", false],
];

const tone = (a, b, lowerIsBetter) => {
  if (a == null || b == null || a === b) return "flat";
  return (lowerIsBetter ? a < b : a > b) ? "up" : "down";
};

export default function BacktestPage() {
  const [ticker, setTicker] = useState("");
  const [strategy, setStrategy] = useState("ma20_50_crossover");
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadHistory = async () => {
    try {
      const res = await api.get("/backtest-runs");
      setHistory(res.data.runs || []);
    } catch { /* history is non-essential */ }
  };

  useEffect(() => { loadHistory(); }, []);

  const run = async (e) => {
    e.preventDefault();
    if (!ticker.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/backtest", { ticker: ticker.trim().toUpperCase(), strategy });
      setResult(res.data);
      loadHistory();
    } catch (err) {
      setError(err.response?.data?.error || "Backtest failed.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const m = result?.metrics;
  const b = result?.benchmark_metrics;

  const fmt = (v, unit) => {
    if (v == null) return "—";
    if (unit === "$") return usd(v);
    return `${money(v)}${unit}`;
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Backtest</h1>
          <p className="page-sub">
            Measure how a strategy would have performed, against buy-and-hold.
          </p>
        </div>
      </div>

      <section className="card mb">
        <div className="card-body">
          <form className="bt-form" onSubmit={run}>
            <label className="bt-field">
              <span className="label">Ticker</span>
              <input className="field" type="search" placeholder="e.g. AAPL"
                     value={ticker} onChange={(e) => setTicker(e.target.value)} required />
            </label>
            <label className="bt-field">
              <span className="label">Strategy</span>
              <select className="field" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                {STRATEGIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </label>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "Running…" : "Run backtest"}
            </button>
          </form>
        </div>
      </section>

      {loading && <div className="loading-bar mb" />}
      {error && <div className="alert alert-error mb">{error}</div>}

      {result && (
        <>
          <div className="bt-summary card mb">
            <div className="card-body bt-summary-body">
              <div>
                <p className="label">Verdict</p>
                <p className={`bt-verdict ${m.beat_benchmark ? "up" : "down"}`}>
                  {m.beat_benchmark ? "Beat buy-and-hold" : "Lost to buy-and-hold"}
                  <span className="num"> {signedPct(m.excess_return_pct)}</span>
                </p>
              </div>
              <div className="bt-meta">
                <span>{result.ticker}</span>
                <span>{result.start_date} → {result.end_date}</span>
                <span>{result.bars} bars</span>
                <span>{result.cost_bps + result.slippage_bps} bps costs</span>
                <span title={result.backtest_run_id}>run {result.backtest_run_id.slice(0, 8)}</span>
              </div>
            </div>
          </div>

          <div className="two-col-wide mb">
            <section className="card">
              <div className="card-head"><h2 className="card-title">Equity curve</h2></div>
              <div className="card-body">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={result.equity_curve} margin={{ top: 8, right: 14, left: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#475569" }} minTickGap={48} tickMargin={6} />
                    <YAxis tick={{ fontSize: 11, fill: "#475569" }} width={58}
                           tickFormatter={(v) => `$${(v / 1000).toFixed(1)}k`} />
                    <Tooltip
                      contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, n) => [usd(v), n]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="equity" name="Strategy" stroke="#2563EB" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="benchmark" name="Buy & hold" stroke="#94A3B8"
                          strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="card">
              <div className="card-head"><h2 className="card-title">Metrics</h2></div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr><th>Metric</th><th className="r">Strategy</th><th className="r">Buy &amp; hold</th></tr>
                  </thead>
                  <tbody>
                    {ROWS.map(([label, key, unit, lower]) => (
                      <tr key={key}>
                        <td>{label}</td>
                        <td className={`r num ${tone(m[key], b[key], lower)}`}>{fmt(m[key], unit)}</td>
                        <td className="r num flat">{fmt(b[key], unit)}</td>
                      </tr>
                    ))}
                    <tr><td>Trades</td><td className="r num">{m.trade_count}</td><td className="r num flat">1</td></tr>
                    <tr><td>Win rate</td><td className="r num">{m.win_rate_pct == null ? "—" : `${money(m.win_rate_pct)}%`}</td><td className="r num flat">—</td></tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <p className="disclaimer">
            Past performance does not predict future results. Signals are lagging
            indicators tested on limited history.
          </p>
        </>
      )}

      {history.length > 0 && (
        <section className="card">
          <div className="card-head"><h2 className="card-title">Previous runs</h2></div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Run</th><th>Ticker</th><th>Strategy</th><th>Window</th>
                  <th className="r">Return</th><th className="r">Sharpe</th><th>Result</th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id}>
                    <td className="num" title={r.id}>{r.id.slice(0, 8)}</td>
                    <td>{(r.universe || []).join(", ")}</td>
                    <td>{r.strategy}</td>
                    <td className="num">{r.start_date} → {r.end_date}</td>
                    <td className="r num">{r.metrics?.total_return_pct != null ? `${money(r.metrics.total_return_pct)}%` : "—"}</td>
                    <td className="r num">{r.metrics?.sharpe != null ? money(r.metrics.sharpe) : "—"}</td>
                    <td>
                      <span className={`badge ${r.metrics?.beat_benchmark ? "badge-up" : "badge-neutral"}`}>
                        {r.metrics?.beat_benchmark ? "Beat market" : "Underperformed"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
