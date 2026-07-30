import { useEffect, useState, useCallback } from "react";
import PropTypes from "prop-types";
import api, { isLoggedIn } from "../../api/client";
import "./portfolio.css";

/*
 * Portfolio roll-up: KPI tiles, allocation, movers and a positions table.
 *
 * Forms follow the data's job: headline numbers are stat tiles (not charts),
 * and allocation is a stacked bar because the job is part-to-whole.
 *
 * Categorical slots below are the validated dark-mode palette, checked against
 * this panel surface (#101215): all 8 pass the lightness band, chroma floor,
 * CVD separation and 3:1 contrast. Assigned in fixed order and never cycled —
 * the tail folds into "Other" instead of inventing a 9th hue.
 */
const SERIES = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];
const OTHER_COLOR = "#565D66"; // de-emphasis gray for the folded tail
const MAX_SLICES = 7;          // 7 named + "Other" == the 8-slot ceiling

const money = (n) =>
  n == null
    ? "—"
    : n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const signed = (n, digits = 2) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;

// Direction is carried by an arrow and a sign as well as colour, so the
// meaning survives for colour-blind readers and in print.
const arrow = (n) => (n == null ? "" : n > 0 ? "▲" : n < 0 ? "▼" : "");
const toneClass = (n) => (n == null ? "tw-flat" : n > 0 ? "tw-up" : n < 0 ? "tw-down" : "tw-flat");

function StatTile({ label, value, delta, deltaPct, muted }) {
  return (
    <div className="stat-tile">
      <p className="tw-label stat-tile-label">{label}</p>
      <p className={`stat-tile-value tw-num ${muted ? "tw-flat" : ""}`}>{value}</p>
      {delta !== undefined && (
        <p className={`stat-tile-delta tw-num ${toneClass(delta)}`}>
          {delta == null ? "—" : `${signed(delta)} ${arrow(delta)}`}
          {deltaPct != null && <span className="stat-tile-pct">{signed(deltaPct)}%</span>}
        </p>
      )}
    </div>
  );
}

StatTile.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.string.isRequired,
  delta: PropTypes.number,
  deltaPct: PropTypes.number,
  muted: PropTypes.bool,
};

export default function PortfolioSummary() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hovered, setHovered] = useState(null); // allocation segment under the cursor

  const fetchSummary = useCallback(async () => {
    if (!isLoggedIn()) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get("/portfolio-summary");
      setData(response.data);
    } catch (err) {
      setError(err.response?.data?.error || "Could not load portfolio");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(fetchSummary, 400);
    return () => clearTimeout(timer);
  }, [fetchSummary]);

  if (isLoading && !data) {
    return (
      <section className="portfolio-panel">
        <p className="tw-label">Loading portfolio…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="portfolio-panel">
        <p className="tw-label portfolio-error">{error}</p>
      </section>
    );
  }

  const positions = data?.positions || [];

  if (!positions.length) {
    return (
      <section className="portfolio-panel">
        <header className="portfolio-header">
          <h3 className="portfolio-title">Portfolio</h3>
          <button className="portfolio-refresh tw-label" onClick={fetchSummary}>Refresh</button>
        </header>
        <p className="portfolio-empty tw-label">
          No positions yet — buy a stock to see your portfolio roll-up.
        </p>
      </section>
    );
  }

  // Fold everything past the 7th position into a single "Other" slice rather
  // than generating additional hues.
  const named = positions.slice(0, MAX_SLICES);
  const tail = positions.slice(MAX_SLICES);
  const slices = named.map((p, i) => ({
    ticker: p.ticker,
    weight: p.weight,
    value: p.market_value,
    color: SERIES[i],
  }));
  if (tail.length) {
    slices.push({
      ticker: `Other (${tail.length})`,
      weight: tail.reduce((s, p) => s + p.weight, 0),
      value: tail.reduce((s, p) => s + p.market_value, 0),
      color: OTHER_COLOR,
    });
  }

  const asOf = data.as_of ? new Date(data.as_of).toLocaleTimeString() : null;

  return (
    <section className="portfolio-panel">
      <header className="portfolio-header">
        <h3 className="portfolio-title">Portfolio</h3>
        <div className="portfolio-meta">
          {data.stale_quotes?.length > 0 && (
            <span className="portfolio-stale tw-label" title={`No live quote: ${data.stale_quotes.join(", ")}`}>
              ⚠ {data.stale_quotes.length} stale
            </span>
          )}
          {asOf && <span className="tw-label">updated {asOf}</span>}
          <button className="portfolio-refresh tw-label" onClick={fetchSummary}>Refresh</button>
        </div>
      </header>

      {/* Row 1 — headline numbers as stat tiles */}
      <div className="stat-row">
        <StatTile label="Total Value" value={money(data.total_value)} />
        <StatTile
          label="Total Return"
          value={money(data.total_return_abs)}
          delta={data.total_return_abs}
          deltaPct={data.total_return_pct}
        />
        <StatTile
          label="Day Change"
          value={data.day_change_abs == null ? "—" : money(data.day_change_abs)}
          delta={data.day_change_abs}
          deltaPct={data.day_change_pct}
          muted={data.day_change_abs == null}
        />
        <StatTile
          label="Positions"
          value={String(data.position_count)}
          delta={undefined}
        />
      </div>

      <div className="portfolio-mid">
        {/* Allocation — part-to-whole, so a stacked bar rather than a pie */}
        <div className="alloc-block">
          <p className="tw-label">Allocation</p>
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

          <div className="alloc-tooltip tw-num">
            {hovered
              ? `${hovered.ticker} · ${hovered.weight.toFixed(1)}% · $${money(hovered.value)}`
              : " "}
          </div>

          {/* Legend doubles as the direct labels, so identity is never colour-alone */}
          <ul className="alloc-legend">
            {slices.map((s) => (
              <li key={s.ticker} className="alloc-legend-item">
                <span className="alloc-swatch" style={{ background: s.color }} />
                <span className="alloc-legend-ticker">{s.ticker}</span>
                <span className="alloc-legend-weight tw-num">{s.weight.toFixed(1)}%</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Movers */}
        <div className="movers-block">
          <p className="tw-label">Top Movers</p>
          {data.best && (
            <div className="mover-row">
              <span className={`mover-arrow ${toneClass(data.best.pl_pct)}`}>{arrow(data.best.pl_pct)}</span>
              <span className="mover-ticker">{data.best.ticker}</span>
              <span className={`mover-pct tw-num ${toneClass(data.best.pl_pct)}`}>
                {signed(data.best.pl_pct)}%
              </span>
            </div>
          )}
          {data.worst && (
            <div className="mover-row">
              <span className={`mover-arrow ${toneClass(data.worst.pl_pct)}`}>{arrow(data.worst.pl_pct)}</span>
              <span className="mover-ticker">{data.worst.ticker}</span>
              <span className={`mover-pct tw-num ${toneClass(data.worst.pl_pct)}`}>
                {signed(data.worst.pl_pct)}%
              </span>
            </div>
          )}
          <p className="tw-label movers-note">
            Cost basis ${money(data.total_cost)}
          </p>
        </div>
      </div>

      {/* Row 3 — positions table. Numeric columns are right-aligned and
          tabular so they line up down the column. */}
      <div className="positions-scroll">
        <table className="positions-table">
          <thead>
            <tr>
              <th className="tw-label">Ticker</th>
              <th className="tw-label num">Shares</th>
              <th className="tw-label num">Avg</th>
              <th className="tw-label num">Last</th>
              <th className="tw-label num">Value</th>
              <th className="tw-label num">P/L $</th>
              <th className="tw-label num">P/L %</th>
              <th className="tw-label num">Weight</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.ticker}>
                <td className="pos-ticker">{p.ticker}</td>
                <td className="tw-num num">{p.num_shares}</td>
                <td className="tw-num num">{money(p.avg_price)}</td>
                <td className="tw-num num">
                  {p.quote_available ? money(p.last_quote) : <span className="tw-flat" title="No quote available">—</span>}
                </td>
                <td className="tw-num num">{money(p.market_value)}</td>
                <td className={`tw-num num ${toneClass(p.pl_abs)}`}>{signed(p.pl_abs)}</td>
                <td className={`tw-num num ${toneClass(p.pl_pct)}`}>
                  {p.pl_pct == null ? "—" : `${signed(p.pl_pct)}%`}
                </td>
                <td className="tw-num num tw-flat">{p.weight.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
