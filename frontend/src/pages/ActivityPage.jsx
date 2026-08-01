import { useEffect, useState, useCallback, Fragment } from "react";
import PropTypes from "prop-types";
import api, { isLoggedIn } from "../api/client";
import "./pages.css";

/*
 * Activity — the audit ledger, surfaced.
 *
 * The app already records every state change with the evidence behind it;
 * this is the page that makes that trail reviewable instead of just stored.
 */

const GROUPS = [
  { id: "", label: "Everything" },
  { id: "agent", label: "Agent" },
  { id: "trade", label: "Trades" },
  { id: "auth", label: "Sign-in" },
  { id: "watchlist", label: "Watchlist" },
];

const MEMBERS = {
  agent: ["agent_propose", "agent_approve", "agent_reject", "agent_execute",
          "agent_execute_failed", "agent_tool_call"],
  trade: ["buy", "buy_new", "sell"],
  auth: ["register", "login", "login_failed"],
  watchlist: ["pin", "unpin"],
};

const ACTION_META = {
  register:            ["badge-info",    "Account created"],
  login:               ["badge-neutral", "Signed in"],
  login_failed:        ["badge-down",    "Failed sign-in"],
  pin:                 ["badge-info",    "Pinned"],
  unpin:               ["badge-neutral", "Unpinned"],
  buy:                 ["badge-up",      "Bought"],
  buy_new:             ["badge-up",      "Opened position"],
  sell:                ["badge-down",    "Sold"],
  agent_tool_call:     ["badge-neutral", "Agent used a tool"],
  agent_propose:       ["badge-info",    "Agent proposed"],
  agent_approve:       ["badge-up",      "Approved"],
  agent_reject:        ["badge-neutral", "Rejected"],
  agent_execute:       ["badge-up",      "Agent executed"],
  agent_execute_failed:["badge-down",    "Execution failed"],
  recs_snapshot:       ["badge-neutral", "Data snapshot"],
  signals_generated:   ["badge-info",    "Signals generated"],
  backtest_run:        ["badge-info",    "Backtest run"],
  backtest_note:       ["badge-neutral", "Backtest note"],
};

/* Fields that hold the agent's reasoning. When a payload carries them, the
   detail row renders them as prose rather than leaving them buried in JSON. */
function Reasoning({ payload }) {
  const { rationale, evidence_used, risks } = payload || {};
  if (!rationale && !evidence_used?.length && !risks) return null;
  return (
    <div className="reasoning">
      {rationale && <p className="proposal-rationale">{rationale}</p>}
      {evidence_used?.length > 0 && (
        <div className="proposal-block">
          <p className="label">Evidence cited</p>
          <ul className="evidence">
            {evidence_used.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}
      {risks && (
        <div className="proposal-block">
          <p className="label">What would make this wrong</p>
          <p className="proposal-risks">{risks}</p>
        </div>
      )}
    </div>
  );
}

Reasoning.propTypes = { payload: PropTypes.object };

export default function ActivityPage() {
  const [entries, setEntries] = useState([]);
  const [group, setGroup] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!isLoggedIn()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get("/audit-log", { params: { limit: 200 } });
      setEntries(res.data.entries || []);
    } catch (err) {
      setError(err.response?.data?.error || "Could not load your activity.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const visible = group ? entries.filter((e) => (MEMBERS[group] || []).includes(e.action)) : entries;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Activity</h1>
          <p className="page-sub">
            Every state change, with the evidence behind it. This log is append-only.
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load}>Refresh</button>
      </div>

      <div className="filter-row mb">
        {GROUPS.map((g) => (
          <button
            key={g.id}
            className={`filter-chip${group === g.id ? " is-active" : ""}`}
            onClick={() => setGroup(g.id)}
          >
            {g.label}
          </button>
        ))}
      </div>

      {loading && <div className="loading-bar mb" />}
      {error && <div className="alert alert-error mb">{error}</div>}

      {!loading && visible.length === 0 ? (
        <div className="card">
          <div className="empty">
            <p className="empty-title">Nothing here yet</p>
            <p>Actions you take will appear here with a full record of what drove them.</p>
          </div>
        </div>
      ) : (
        <section className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th><th>Action</th><th>Subject</th><th>Evidence</th><th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((e) => {
                  const [cls, label] = ACTION_META[e.action] || ["badge-neutral", e.action];
                  const open = expanded === e.id;
                  return (
                    // Keyed Fragment: each entry renders a row plus an
                    // optional detail row, so the key belongs on the wrapper.
                    <Fragment key={e.id}>
                      <tr>
                        <td className="num flat">
                          {e.created_at ? new Date(e.created_at).toLocaleString() : "—"}
                        </td>
                        <td><span className={`badge ${cls}`}>{label}</span></td>
                        <td>{e.entity || "—"}</td>
                        <td className="num flat">
                          {e.snapshot_ref ? (
                            <span title={e.snapshot_ref}>snapshot {e.snapshot_ref.slice(0, 8)}</span>
                          ) : "—"}
                        </td>
                        <td className="r">
                          {e.payload && (
                            <button className="btn btn-ghost btn-sm"
                                    onClick={() => setExpanded(open ? null : e.id)}>
                              {open ? "Hide" : "Details"}
                            </button>
                          )}
                        </td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={5}>
                            {/* Agent decisions carry the reasoning; show it as
                                prose, with the raw record still available below. */}
                            <Reasoning payload={e.payload} />
                            <details className="payload-raw">
                              <summary>Raw record</summary>
                              <pre className="payload">{JSON.stringify(e.payload, null, 2)}</pre>
                            </details>
                            {e.request_id && (
                              <p className="label">Request {e.request_id}</p>
                            )}
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
