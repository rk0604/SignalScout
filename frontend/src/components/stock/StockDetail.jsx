import { useEffect, useState, useCallback } from "react";
import PropTypes from "prop-types";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend, ReferenceDot,
} from "recharts";
import api from "../../api/client";
import { usd, signed, toneClass } from "../../lib/format";
import "./stockDetail.css";

/*
 * Side drawer with everything known about one ticker: price + moving averages,
 * crossover signals, fundamentals, risk, news sentiment, and a trade form.
 *
 * This replaces the old stack of react-modals, which each carried their own
 * inline styling and stacked on top of each other.
 */

const UP = "#047857";
const DOWN = "#DC2626";

export default function StockDetail({ ticker, onClose, onChanged }) {
  const [chart, setChart] = useState(null);
  const [fundamentals, setFundamentals] = useState(null);
  const [risk, setRisk] = useState(null);
  const [news, setNews] = useState(null);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const [trade, setTrade] = useState({ price: "", num_shares: "" });
  const [tradeMsg, setTradeMsg] = useState(null);
  const [tradeBusy, setTradeBusy] = useState(false);

  const reset = () => {
    setChart(null); setFundamentals(null); setRisk(null); setNews(null);
    setErrors({}); setTradeMsg(null); setTrade({ price: "", num_shares: "" });
  };

  const loadAll = useCallback(async (symbol) => {
    setLoading(true);
    const errs = {};

    // Each panel fails independently — one rate-limited endpoint shouldn't
    // blank the whole drawer.
    const [c, f, r] = await Promise.allSettled([
      api.get("/get-chart-data", { params: { stock: symbol } }),
      api.post("/fetch-stock-data", { ticker: symbol }),
      api.post("/fetch-risk-anal", { stock: symbol }),
    ]);

    if (c.status === "fulfilled") setChart(c.value.data);
    else errs.chart = c.reason?.response?.data?.error || "Price data unavailable";

    if (f.status === "fulfilled") setFundamentals(f.value.data);
    else errs.fundamentals = f.reason?.response?.data?.error || "Financials unavailable";

    if (r.status === "fulfilled") setRisk(r.value.data);
    else errs.risk = r.reason?.response?.data?.error || "Risk metrics unavailable";

    setErrors(errs);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!ticker) { reset(); return; }
    reset();
    loadAll(ticker);
  }, [ticker, loadAll]);

  // Close on Escape
  useEffect(() => {
    if (!ticker) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ticker, onClose]);

  const loadNews = async () => {
    try {
      const res = await api.get("/get-sentiment-analysis", { params: { stock: ticker } });
      setNews(res.data);
    } catch (err) {
      setErrors((p) => ({ ...p, news: err.response?.data?.error || "No news found" }));
    }
  };

  const submitTrade = async (e) => {
    e.preventDefault();
    setTradeBusy(true);
    setTradeMsg(null);
    try {
      const res = await api.post("/update-holdings", {
        holdingsUpdate: { ticker, price: trade.price, num_shares: trade.num_shares },
      });
      setTradeMsg({ ok: true, text: res.data.message });
      setTrade({ price: "", num_shares: "" });
      onChanged?.();
    } catch (err) {
      setTradeMsg({ ok: false, text: err.response?.data?.error || "Could not record the trade." });
    } finally {
      setTradeBusy(false);
    }
  };

  if (!ticker) return null;

  const latestSignal = chart?.signals?.length ? chart.signals[chart.signals.length - 1] : null;
  const fin = fundamentals?.financials || {};
  const latestYear = Object.keys(fin).sort().pop();
  const latest = latestYear ? fin[latestYear] : null;
  const extra = fundamentals?.additional_data || {};

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={`${ticker} details`}>
        <header className="drawer-head">
          <div>
            <h2 className="drawer-ticker">{ticker}</h2>
            {risk?.latest_price != null && (
              <p className="drawer-price num">{usd(risk.latest_price)}</p>
            )}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </header>

        {loading && <div className="loading-bar" />}

        <div className="drawer-body">
          {/* ---- price + moving averages ---- */}
          <section className="panel">
            <div className="panel-head">
              <h3>Price &amp; moving averages</h3>
              {latestSignal && (
                <span className={`badge ${latestSignal.signal === "Buy" ? "badge-up" : "badge-down"}`}>
                  {latestSignal.signal === "Buy" ? "▲ Golden cross" : "▼ Death cross"} {latestSignal.date}
                </span>
              )}
            </div>

            {errors.chart ? (
              <p className="panel-error">{errors.chart}</p>
            ) : chart?.series?.length ? (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={chart.series} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#475569" }} minTickGap={44} tickMargin={6} />
                    <YAxis tick={{ fontSize: 11, fill: "#475569" }} width={54}
                           domain={["auto", "auto"]} tickFormatter={(v) => `$${v.toFixed(0)}`} />
                    <Tooltip
                      contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, n) => [v == null ? "—" : usd(v), n]}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="price" name="Price" stroke="#2563EB" strokeWidth={2} dot={false} />
                    {/* MA lines are gapped during warm-up rather than drawn from zero */}
                    <Line type="monotone" dataKey="ma20" name="MA20" stroke="#1baf7a" strokeWidth={1.5}
                          strokeDasharray="4 3" dot={false} connectNulls={false} />
                    <Line type="monotone" dataKey="ma50" name="MA50" stroke="#4a3aa7" strokeWidth={1.5}
                          strokeDasharray="4 3" dot={false} connectNulls={false} />
                    {(chart.signals || []).map((s) => (
                      <ReferenceDot key={`${s.date}-${s.signal}`} x={s.date} y={s.price} r={5}
                                    fill={s.signal === "Buy" ? UP : DOWN} stroke="#fff" strokeWidth={2} isFront />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
                {chart.signals?.length === 0 && (
                  <p className="panel-note">No MA20/50 crossovers in the last year.</p>
                )}
              </>
            ) : (
              <p className="panel-note">No price history.</p>
            )}
          </section>

          {/* ---- risk ---- */}
          <section className="panel">
            <div className="panel-head"><h3>Risk</h3></div>
            {errors.risk ? (
              <p className="panel-error">{errors.risk}</p>
            ) : risk ? (
              <div className="kv-grid">
                <div><span className="label">Annual volatility</span>
                  <p className="num">{risk.volatility != null ? `${(risk.volatility * 100).toFixed(2)}%` : "—"}</p></div>
                <div><span className="label">Debt / equity</span>
                  <p className="num">{risk.debtToEquity ? Number(risk.debtToEquity).toFixed(2) : "—"}</p></div>
                <div><span className="label">Current ratio</span>
                  <p className="num">{risk.currentRatio ? Number(risk.currentRatio).toFixed(2) : "—"}</p></div>
                <div><span className="label">Quick ratio</span>
                  <p className="num">{risk.quickRatio ? Number(risk.quickRatio).toFixed(2) : "—"}</p></div>
              </div>
            ) : <p className="panel-note">Loading…</p>}
          </section>

          {/* ---- fundamentals ---- */}
          <section className="panel">
            <div className="panel-head">
              <h3>Fundamentals</h3>
              {latestYear && <span className="label">FY {latestYear.substring(0, 4)}</span>}
            </div>
            {errors.fundamentals ? (
              <p className="panel-error">{errors.fundamentals}</p>
            ) : latest ? (
              <div className="kv-grid">
                <div><span className="label">Market cap</span><p className="num">{extra["Market Cap"] ? usd(extra["Market Cap"], 0) : "—"}</p></div>
                <div><span className="label">P/E</span><p className="num">{extra["PE Ratio"] ? extra["PE Ratio"].toFixed(2) : "—"}</p></div>
                <div><span className="label">Total revenue</span><p className="num">{latest["Total Revenue"] ? usd(latest["Total Revenue"], 0) : "—"}</p></div>
                <div><span className="label">Net income</span><p className="num">{latest["Net Income"] ? usd(latest["Net Income"], 0) : "—"}</p></div>
                <div><span className="label">Gross profit</span><p className="num">{latest["Gross Profit"] ? usd(latest["Gross Profit"], 0) : "—"}</p></div>
                <div><span className="label">EPS (basic)</span><p className="num">{latest["Basic EPS"] ?? "—"}</p></div>
              </div>
            ) : <p className="panel-note">Loading…</p>}
          </section>

          {/* ---- news sentiment ---- */}
          <section className="panel">
            <div className="panel-head">
              <h3>News sentiment</h3>
              {!news && <button className="btn btn-ghost btn-sm" onClick={loadNews}>Load news</button>}
              {news?.overall_sentiment && (
                <span className={`badge ${
                  news.overall_sentiment.label === "positive" ? "badge-up"
                  : news.overall_sentiment.label === "negative" ? "badge-down" : "badge-neutral"}`}>
                  {news.overall_sentiment.label} {signed(news.overall_sentiment.polarity)}
                </span>
              )}
            </div>
            {errors.news ? (
              <p className="panel-error">{errors.news}</p>
            ) : news?.news?.length ? (
              <ul className="news-list">
                {news.news.map((n, i) => (
                  <li key={i}>
                    <span className={`news-score num ${toneClass(n.sentiment?.polarity)}`}>
                      {signed(n.sentiment?.polarity)}
                    </span>
                    <a href={n.link} target="_blank" rel="noopener noreferrer">{n.headline}</a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="panel-note">
                Headline sentiment is lexicon-based and approximate.
              </p>
            )}
          </section>

          {/* ---- trade ---- */}
          <section className="panel">
            <div className="panel-head"><h3>Record a trade</h3></div>
            <form className="trade-form" onSubmit={submitTrade}>
              <div className="trade-row">
                <label>
                  <span className="label">Price</span>
                  <input className="field" type="number" step="0.01" min="0" required
                         value={trade.price}
                         onChange={(e) => setTrade((p) => ({ ...p, price: e.target.value }))} />
                </label>
                <label>
                  <span className="label">Shares</span>
                  <input className="field" type="number" step="1" required
                         placeholder="negative to sell"
                         value={trade.num_shares}
                         onChange={(e) => setTrade((p) => ({ ...p, num_shares: e.target.value }))} />
                </label>
              </div>
              <button className="btn btn-accent" type="submit" disabled={tradeBusy}>
                {tradeBusy ? "Saving…" : "Save trade"}
              </button>
              {tradeMsg && (
                <p className={tradeMsg.ok ? "trade-ok" : "trade-err"}>{tradeMsg.text}</p>
              )}
              <p className="panel-note">Use a negative share count to record a sale.</p>
            </form>
          </section>
        </div>
      </aside>
    </>
  );
}

StockDetail.propTypes = {
  ticker: PropTypes.string,
  onClose: PropTypes.func.isRequired,
  onChanged: PropTypes.func,
};
