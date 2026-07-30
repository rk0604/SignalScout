import { useState, useContext } from "react";
import api from "../api/client";
import { StockContext } from "../components/StockContext";
import StockDetail from "../components/stock/StockDetail";
import "./pages.css";

/*
 * Research: analyst-consensus recommendations plus ticker lookup and pinning.
 * Both used to be separate cramped cards on the single dashboard.
 */

const RATING_BADGE = { buy: "badge-up", hold: "badge-neutral", sell: "badge-down" };

// The backend returns proportions; a very strong consensus is worth calling out.
const displayRating = (rating, indicator) => {
  if (rating === "buy" && indicator > 0.85) return "strong buy";
  if (rating === "sell" && indicator > 0.85) return "strong sell";
  return rating;
};

export default function ResearchPage() {
  const { pinnedStocks, setPinnedStocks } = useContext(StockContext);
  const [recs, setRecs] = useState([]);
  const [snapshot, setSnapshot] = useState(null);
  const [cached, setCached] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [query, setQuery] = useState("");
  const [openTicker, setOpenTicker] = useState(null);
  const [pinMsg, setPinMsg] = useState(null);

  const loadRecs = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/fetch-recs", {});
      setRecs(res.data.recommendations || []);
      setSnapshot(res.data.snapshot_ref || null);
      setCached(Boolean(res.data.cached));
    } catch (err) {
      const status = err.response?.status;
      setError(
        status === 429
          ? "The market data provider is rate limiting us. Try again in a few minutes."
          : status === 503
          ? "No recommendation data available right now."
          : "Could not load recommendations."
      );
    } finally {
      setLoading(false);
    }
  };

  const search = (e) => {
    e.preventDefault();
    const t = query.trim().toUpperCase();
    if (t) setOpenTicker(t);
  };

  const pin = async (ticker) => {
    setPinMsg(null);
    try {
      const res = await api.post("/pin-stock", { query: ticker });
      setPinnedStocks((prev) => [...(prev || []), res.data.data]);
      setPinMsg({ ok: true, text: `${ticker} pinned to your watchlist.` });
    } catch (err) {
      setPinMsg({
        ok: false,
        text: err.response?.status === 401 ? `${ticker} is already on your watchlist.` : "Could not pin that ticker.",
      });
    }
  };

  const unpin = async (ticker) => {
    setPinMsg(null);
    try {
      await api.get("/remove-pinned-stock", { params: { query: ticker } });
      setPinnedStocks((prev) => (prev || []).filter((t) => t !== ticker));
      setPinMsg({ ok: true, text: `${ticker} removed from your watchlist.` });
    } catch (err) {
      setPinMsg({
        ok: false,
        text: err.response?.status === 401
          ? "You can't unpin a stock you hold shares in."
          : "Could not remove that ticker.",
      });
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Research</h1>
          <p className="page-sub">Look up a ticker or scan analyst consensus.</p>
        </div>
      </div>

      <div className="two-col">
        <section className="card">
          <div className="card-head"><h2 className="card-title">Find a stock</h2></div>
          <div className="card-body">
            <form className="search-row" onSubmit={search}>
              <input
                className="field"
                type="search"
                placeholder="Ticker, e.g. NVDA"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Ticker symbol"
              />
              <button className="btn btn-primary" type="submit">Analyse</button>
            </form>
            {pinMsg && (
              <div className={`alert ${pinMsg.ok ? "alert-info" : "alert-error"} mt-sm`}>{pinMsg.text}</div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-head">
            <h2 className="card-title">Watchlist</h2>
            <span className="label">{(pinnedStocks || []).length} pinned</span>
          </div>
          <div className="card-body">
            {(pinnedStocks || []).length === 0 ? (
              <p className="flat">Nothing pinned yet. Analyse a ticker and pin it to watch it here.</p>
            ) : (
              <ul className="chips">
                {pinnedStocks.map((t) => (
                  <li key={t} className="chip">
                    <button className="chip-name" onClick={() => setOpenTicker(t)}>{t}</button>
                    <button className="chip-x" onClick={() => unpin(t)} aria-label={`Remove ${t}`}>×</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <div>
            <h2 className="card-title">Analyst consensus</h2>
            {snapshot && (
              <p className="card-sub">
                {cached ? "Cached" : "Fresh"} snapshot · {snapshot.slice(0, 8)}
              </p>
            )}
          </div>
          <button className="btn btn-primary btn-sm" onClick={loadRecs} disabled={loading}>
            {loading ? "Scanning…" : recs.length ? "Refresh" : "Run scan"}
          </button>
        </div>

        {loading && <div className="loading-bar" />}

        <div className="card-body">
          {error && <div className="alert alert-error">{error}</div>}

          {!error && recs.length === 0 && !loading && (
            <div className="empty">
              <p className="empty-title">No scan yet</p>
              <p>Run a scan to rank tickers by analyst consensus. The first run takes a minute; later ones are cached.</p>
            </div>
          )}

          {recs.length > 0 && (
            <div className="rec-grid">
              {recs.map((r) => {
                const label = displayRating(r.rating, r.indicator);
                return (
                  <button key={r.ticker} className="rec" onClick={() => setOpenTicker(r.ticker)}>
                    <div className="rec-top">
                      <span className="rec-ticker">{r.ticker}</span>
                      <span className={`badge ${RATING_BADGE[r.rating] || "badge-neutral"}`}>{label}</span>
                    </div>
                    <div className="rec-meter" aria-hidden="true">
                      <span style={{ width: `${Math.round(r.indicator * 100)}%` }} />
                    </div>
                    <p className="rec-meta num">
                      {(r.indicator * 100).toFixed(0)}% consensus
                      {r.analyst_count ? ` · ${r.analyst_count} analysts` : ""}
                    </p>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </section>

      <StockDetail
        ticker={openTicker}
        onClose={() => setOpenTicker(null)}
        onChanged={() => {}}
      />
      {openTicker && !(pinnedStocks || []).includes(openTicker) && (
        <button className="pin-fab btn btn-accent" onClick={() => pin(openTicker)}>
          Pin {openTicker}
        </button>
      )}
    </>
  );
}
