import { useState, useEffect, useMemo, useCallback, Fragment } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import api from "../api/client";
import { usd, money, signedPct } from "../lib/format";
import RunNote from "../components/backtest/RunNote";
import "./pages.css";

/*
 * Backtest.
 *
 * The strategy catalogue and its parameter schemas come from the API, so the
 * form is generated rather than hard-coded: adding a strategy on the backend
 * makes it appear here with the right controls and no frontend change.
 */

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

const PRESETS = [
  { label: "Mega-cap tech", tickers: "AAPL, MSFT, NVDA, AMZN, GOOGL, META" },
  { label: "Semis", tickers: "NVDA, AMD, AVGO, TSM, INTC, MU" },
  { label: "Banks", tickers: "JPM, BAC, WFC, GS, MS, C" },
];

const tone = (a, b, lowerIsBetter) => {
  if (a == null || b == null || a === b) return "flat";
  return (lowerIsBetter ? a < b : a > b) ? "up" : "down";
};

const defaultsFor = (spec) =>
  Object.fromEntries((spec?.params || []).map((p) => [p.name, p.default]));

export default function BacktestPage() {
  const [strategies, setStrategies] = useState([]);
  const [strategyId, setStrategyId] = useState(null);
  const [params, setParams] = useState({});
  const [ticker, setTicker] = useState("AAPL");
  const [universe, setUniverse] = useState(PRESETS[0].tickers);

  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [openRun, setOpenRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const spec = useMemo(
    () => strategies.find((s) => s.id === strategyId) || null,
    [strategies, strategyId]
  );

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.get("/backtest-runs");
      setHistory(res.data.runs || []);
    } catch { /* history is non-essential */ }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const res = await api.get("/strategies");
        const list = res.data.strategies || [];
        setStrategies(list);
        const initial = list.find((s) => s.id === "ma_crossover") || list[0];
        if (initial) {
          setStrategyId(initial.id);
          setParams(defaultsFor(initial));
        }
      } catch {
        setError("Could not load the strategy catalogue.");
      }
    })();
    loadHistory();
  }, [loadHistory]);

  const pickStrategy = (s) => {
    setStrategyId(s.id);
    setParams(defaultsFor(s)); // params are per-strategy; never carry them across
    setError(null);
  };

  const setParam = (name, value) => setParams((p) => ({ ...p, [name]: value }));

  const run = async (e) => {
    e.preventDefault();
    if (!spec) return;
    setLoading(true);
    setError(null);
    try {
      const body = { strategy: spec.id, params };
      if (spec.multi_asset) {
        body.universe = universe.split(/[,\s]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
      } else {
        body.ticker = ticker.trim().toUpperCase();
      }
      const res = await api.post("/backtest", body);
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

  const universeList = universe.split(/[,\s]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Backtest</h1>
          <p className="page-sub">
            Replay a strategy over history, priced with costs and slippage, against a fair benchmark.
          </p>
        </div>
      </div>

      {/* ---- strategy ladder ---- */}
      <section className="card mb">
        <div className="card-head">
          <h2 className="card-title">Strategy</h2>
          <span className="label">{strategies.length} available</span>
        </div>
        <div className="card-body">
          <div className="strat-grid">
            {strategies.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`strat-card${s.id === strategyId ? " is-active" : ""}`}
                onClick={() => pickStrategy(s)}
                aria-pressed={s.id === strategyId}
              >
                <div className="strat-top">
                  <span className="strat-level">L{s.complexity}</span>
                  {s.multi_asset && <span className="badge badge-info">Portfolio</span>}
                </div>
                <p className="strat-name">{s.label}</p>
                <p className="strat-family">{s.family}</p>
              </button>
            ))}
          </div>
          {spec && <p className="strat-summary">{spec.summary}</p>}
        </div>
      </section>

      {/* ---- configuration ---- */}
      {spec && (
        <section className="card mb">
          <div className="card-head"><h2 className="card-title">Configure</h2></div>
          <div className="card-body">
            <form onSubmit={run}>
              <div className="bt-form">
                {spec.multi_asset ? (
                  <label className="bt-field bt-field-wide">
                    <span className="label">Universe</span>
                    <input
                      className="field" type="text" value={universe}
                      onChange={(e) => setUniverse(e.target.value)}
                      placeholder="AAPL, MSFT, NVDA, …" required
                    />
                    <span className="field-hint">
                      {universeList.length} ticker{universeList.length === 1 ? "" : "s"}
                      {spec.min_universe ? ` · at least ${spec.min_universe} needed` : ""}
                    </span>
                  </label>
                ) : (
                  <label className="bt-field">
                    <span className="label">Ticker</span>
                    <input
                      className="field" type="search" value={ticker}
                      onChange={(e) => setTicker(e.target.value)}
                      placeholder="e.g. AAPL" required
                    />
                  </label>
                )}

                {(spec.params || []).map((p) => (
                  <label className="bt-field" key={p.name} title={p.help}>
                    <span className="label">{p.label}</span>
                    {p.type === "enum" ? (
                      <select
                        className="field"
                        value={params[p.name] ?? p.default}
                        onChange={(e) => setParam(p.name, e.target.value)}
                      >
                        {p.options.map((o) => (
                          <option key={o} value={o}>{o.toUpperCase()}</option>
                        ))}
                      </select>
                    ) : p.type === "bool" ? (
                      <span className="bt-check">
                        <input
                          type="checkbox"
                          checked={Boolean(params[p.name])}
                          onChange={(e) => setParam(p.name, e.target.checked)}
                        />
                        <span>{p.help}</span>
                      </span>
                    ) : (
                      <input
                        className="field" type="number"
                        value={params[p.name] ?? p.default}
                        min={p.min} max={p.max}
                        step={p.step || (p.type === "int" ? 1 : 0.01)}
                        onChange={(e) => setParam(p.name, e.target.value)}
                      />
                    )}
                    {p.type !== "bool" && <span className="field-hint">{p.help}</span>}
                  </label>
                ))}
              </div>

              <div className="bt-actions">
                <button className="btn btn-primary" type="submit" disabled={loading}>
                  {loading ? "Running…" : "Run backtest"}
                </button>
                <button
                  className="btn btn-ghost btn-sm" type="button"
                  onClick={() => setParams(defaultsFor(spec))}
                >
                  Reset parameters
                </button>
                {spec.multi_asset && (
                  <span className="bt-presets">
                    {PRESETS.map((p) => (
                      <button
                        key={p.label} type="button" className="filter-chip"
                        onClick={() => setUniverse(p.tickers)}
                      >
                        {p.label}
                      </button>
                    ))}
                  </span>
                )}
              </div>
            </form>
          </div>
        </section>
      )}

      {loading && <div className="loading-bar mb" />}
      {error && <div className="alert alert-error mb">{error}</div>}

      {result && (
        <>
          <div className="bt-summary card mb">
            <div className="card-body bt-summary-body">
              <div>
                <p className="label">Verdict</p>
                <p className={`bt-verdict ${m.beat_benchmark ? "up" : "down"}`}>
                  {m.beat_benchmark ? "Beat the benchmark" : "Lost to the benchmark"}
                  <span className="num"> {signedPct(m.excess_return_pct)}</span>
                </p>
              </div>
              <div className="bt-meta">
                <span>{result.strategy_label || result.strategy}</span>
                <span>{result.ticker}</span>
                <span>{result.start_date} → {result.end_date}</span>
                <span>{result.bars} bars</span>
                <span>{result.cost_bps + result.slippage_bps} bps costs</span>
                <span title={result.backtest_run_id}>run {result.backtest_run_id.slice(0, 8)}</span>
              </div>
            </div>
            {/* The parameters actually used, echoed back from the server after
                clamping — so the record matches what ran. */}
            {result.params && Object.keys(result.params).length > 0 && (
              <div className="bt-params">
                {Object.entries(result.params).map(([k, v]) => (
                  <span className="bt-param" key={k}>
                    <span className="label">{k}</span>
                    <span className="num">{String(v)}</span>
                  </span>
                ))}
              </div>
            )}
            {result.missing_tickers?.length > 0 && (
              <div className="alert alert-error mt-sm">
                No price history for: {result.missing_tickers.join(", ")} — excluded from the run.
              </div>
            )}
            <div className="bt-note-wrap">
              <RunNote
                key={result.backtest_run_id}
                runId={result.backtest_run_id}
                initialNote={result.notes || ""}
                onSaved={(notes) => {
                  setResult((r) => (r ? { ...r, notes } : r));
                  loadHistory();
                }}
              />
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
                    <Line type="monotone" dataKey="benchmark"
                          name={result.universe?.length > 1 ? "Equal weight" : "Buy & hold"}
                          stroke="#94A3B8" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="card">
              <div className="card-head"><h2 className="card-title">Metrics</h2></div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Metric</th><th className="r">Strategy</th>
                      <th className="r">{result.universe?.length > 1 ? "Equal weight" : "Buy & hold"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map(([label, key, unit, lower]) => (
                      <tr key={key}>
                        <td>{label}</td>
                        <td className={`r num ${tone(m[key], b[key], lower)}`}>{fmt(m[key], unit)}</td>
                        <td className="r num flat">{fmt(b[key], unit)}</td>
                      </tr>
                    ))}
                    <tr><td>Trades</td><td className="r num">{m.trade_count}</td><td className="r num flat">—</td></tr>
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
          <div className="card-head">
            <h2 className="card-title">Previous runs</h2>
            <span className="label">Click a run to read or add a note</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Run</th><th>Universe</th><th>Strategy</th><th>Window</th>
                  <th className="r">Return</th><th className="r">Sharpe</th><th>Result</th><th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => {
                  const open = openRun === r.id;
                  return (
                    <Fragment key={r.id}>
                      <tr className="row-clickable" onClick={() => setOpenRun(open ? null : r.id)}>
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
                        <td className="r">
                          <span className="disclose">{r.notes ? "Note ✎" : open ? "Hide" : "Add note"}</span>
                        </td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={8}>
                            <RunNote
                              runId={r.id}
                              initialNote={r.notes || ""}
                              onSaved={(notes) => setHistory((h) =>
                                h.map((x) => (x.id === r.id ? { ...x, notes } : x)))}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
