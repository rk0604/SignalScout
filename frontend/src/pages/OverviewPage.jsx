import { useEffect, useState, useCallback, useMemo } from "react";
import PropTypes from "prop-types";
import { Link } from "react-router-dom";
import api, { isLoggedIn } from "../api/client";
import { subscribeQuote } from "../api/realtime";
import { usd, signed, signedPct, arrow, toneClass, SERIES, OTHER_COLOR } from "../lib/format";
import StockDetail from "../components/stock/StockDetail";
import "./pages.css";

const MAX_SLICES = 7; // 7 named + "Other" == the 8-slot categorical ceiling

function StatCard({ label, value, delta, deltaPct, hint }) {
  return (
    <div className="card stat">
      <p className="label">{label}</p>
      <p className="stat-value num">{value}</p>
      {delta !== undefined ? (
        <p className={`stat-delta num ${toneClass(delta)}`}>
          {delta == null ? "—" : `${arrow(delta)} ${signed(delta)}`}
          {deltaPct != null && <span className="stat-pct">{signedPct(deltaPct)}</span>}
        </p>
      ) : (
        hint && <p className="stat-hint">{hint}</p>
      )}
    </div>
  );
}

StatCard.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.string.isRequired,
  delta: PropTypes.number,
  deltaPct: PropTypes.number,
  hint: PropTypes.string,
};

export default function OverviewPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState(null);
  const [openTicker, setOpenTicker] = useState(null);

  const load = useCallback(async () => {
    if (!isLoggedIn()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/portfolio-summary");
      setData(res.data);
    } catch (err) {
      setError(err.response?.data?.error || "Could not load your portfolio.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const tickers = useMemo(() => (data?.positions || []).map((p) => p.ticker), [data]);

  // Live quotes patch prices in place and recompute the affected numbers, so
  // the page updates without a full refetch.
  useEffect(() => {
    if (!tickers.length) return;
    const apply = (q) =>
      setData((prev) => {
        if (!prev) return prev;
        const positions = prev.positions.map((p) => {
          if (p.ticker !== q.ticker || q.price == null) return p;
          const market_value = q.price * p.num_shares;
          const pl_abs = market_value - p.cost_basis;
          return {
            ...p,
            last_quote: q.price,
            market_value,
            pl_abs,
            pl_pct: p.cost_basis ? (pl_abs / p.cost_basis) * 100 : null,
            quote_available: true,
          };
        });
        const total_value = positions.reduce((s, p) => s + p.market_value, 0);
        const total_return_abs = total_value - prev.total_cost;
        return {
          ...prev,
          positions: positions.map((p) => ({
            ...p,
            weight: total_value ? (p.market_value / total_value) * 100 : 0,
          })),
          total_value,
          total_return_abs,
          total_return_pct: prev.total_cost ? (total_return_abs / prev.total_cost) * 100 : null,
        };
      });

    const unsubs = tickers.map((t) => subscribeQuote(t, apply));
    return () => unsubs.forEach((fn) => fn());
  }, [tickers]);

  // Memoised so the `|| []` fallback doesn't produce a new array identity on
  // every render and re-run the slice calculation below.
  const positions = useMemo(() => data?.positions || [], [data]);

  // Allocation slices, largest first, tail folded into "Other".
  const slices = useMemo(() => {
    const named = positions.slice(0, MAX_SLICES).map((p, i) => ({
      ticker: p.ticker, weight: p.weight, value: p.market_value, color: SERIES[i],
    }));
    const tail = positions.slice(MAX_SLICES);
    if (tail.length) {
      named.push({
        ticker: `Other (${tail.length})`,
        weight: tail.reduce((s, p) => s + p.weight, 0),
        value: tail.reduce((s, p) => s + p.market_value, 0),
        color: OTHER_COLOR,
      });
    }
    return named;
  }, [positions]);

  if (loading && !data) {
    return (
      <>
        <div className="page-head"><h1 className="page-title">Overview</h1></div>
        <div className="card"><div className="card-body"><div className="loading-bar" /></div></div>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-sub">
            {data?.as_of
              ? `Updated ${new Date(data.as_of).toLocaleTimeString()}`
              : "Your portfolio at a glance"}
          </p>
        </div>
        <div className="page-actions">
          {data?.stale_quotes?.length > 0 && (
            <span className="badge badge-warn" title={data.stale_quotes.join(", ")}>
              {data.stale_quotes.length} stale quote{data.stale_quotes.length > 1 ? "s" : ""}
            </span>
          )}
          <button className="btn btn-ghost btn-sm" onClick={load}>Refresh</button>
        </div>
      </div>

      {error && <div className="alert alert-error mb">{error}</div>}

      {!error && positions.length === 0 ? (
        <div className="card">
          <div className="empty">
            <p className="empty-title">No positions yet</p>
            <p>Find a stock and record your first trade to see your portfolio here.</p>
            <Link className="btn btn-primary mt" to="/app/research">Go to Research</Link>
          </div>
        </div>
      ) : (
        <>
          <div className="stat-row">
            <StatCard label="Total value" value={usd(data.total_value)} />
            <StatCard
              label="Total return"
              value={usd(data.total_return_abs)}
              delta={data.total_return_abs}
              deltaPct={data.total_return_pct}
            />
            <StatCard
              label="Day change"
              value={data.day_change_abs == null ? "—" : usd(data.day_change_abs)}
              delta={data.day_change_abs}
              deltaPct={data.day_change_pct}
            />
            <StatCard
              label="Positions"
              value={String(data.position_count)}
              hint={`Cost basis ${usd(data.total_cost)}`}
            />
          </div>

          <div className="two-col">
            <section className="card">
              <div className="card-head"><h2 className="card-title">Allocation</h2></div>
              <div className="card-body">
                <div
                  className="alloc-bar"
                  role="img"
                  aria-label={`Allocation: ${slices.map((s) => `${s.ticker} ${s.weight.toFixed(1)}%`).join(", ")}`}
                >
                  {slices.map((s) => (
                    <div
                      key={s.ticker}
                      className="alloc-seg"
                      style={{ width: `${s.weight}%`, background: s.color }}
                      onMouseEnter={() => setHovered(s)}
                      onMouseLeave={() => setHovered(null)}
                    />
                  ))}
                </div>
                {/* Reserved line so hovering never reflows the layout */}
                <p className="alloc-tip">
                  {hovered
                    ? `${hovered.ticker} · ${hovered.weight.toFixed(1)}% · ${usd(hovered.value)}`
                    : " "}
                </p>
                {/* Legend doubles as direct labels, so identity is never colour-alone */}
                <ul className="legend">
                  {slices.map((s) => (
                    <li key={s.ticker}>
                      <span className="swatch" style={{ background: s.color }} />
                      <span className="legend-name">{s.ticker}</span>
                      <span className="legend-val num">{s.weight.toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="card">
              <div className="card-head"><h2 className="card-title">Movers</h2></div>
              <div className="card-body movers">
                {[data.best, data.worst].filter(Boolean).map((m, i) => (
                  <div className="mover" key={`${m.ticker}-${i}`}>
                    <div>
                      <p className="mover-ticker">{m.ticker}</p>
                      <p className="mover-label">{i === 0 ? "Best performer" : "Worst performer"}</p>
                    </div>
                    <span className={`badge ${m.pl_pct >= 0 ? "badge-up" : "badge-down"}`}>
                      {arrow(m.pl_pct)} {signedPct(m.pl_pct)}
                    </span>
                  </div>
                ))}
                {!data.best && <p className="flat">Not enough data yet.</p>}
              </div>
            </section>
          </div>

          <section className="card">
            <div className="card-head">
              <h2 className="card-title">Holdings</h2>
              <span className="label">{positions.length} position{positions.length > 1 ? "s" : ""}</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th className="r">Shares</th>
                    <th className="r">Avg cost</th>
                    <th className="r">Last</th>
                    <th className="r">Value</th>
                    <th className="r">Gain / loss</th>
                    <th className="r">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.ticker} className="row-clickable" onClick={() => setOpenTicker(p.ticker)}>
                      <td><span className="ticker-link">{p.ticker}</span></td>
                      <td className="r num">{p.num_shares}</td>
                      <td className="r num">{usd(p.avg_price)}</td>
                      <td className="r num">
                        {p.quote_available ? usd(p.last_quote) : <span className="flat" title="No quote available">—</span>}
                      </td>
                      <td className="r num">{usd(p.market_value)}</td>
                      <td className={`r num ${toneClass(p.pl_abs)}`}>
                        {signed(p.pl_abs)} <span className="pl-pct">{signedPct(p.pl_pct)}</span>
                      </td>
                      <td className="r num flat">{p.weight.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <StockDetail ticker={openTicker} onClose={() => setOpenTicker(null)} onChanged={load} />
    </>
  );
}
