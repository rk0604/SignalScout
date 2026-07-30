import { useState, useEffect, useCallback } from "react";
import api, { isLoggedIn } from "../api/client";
import "./pages.css";

/*
 * Agent page — the human half of the propose → approve → execute loop.
 * The agent writes proposals; nothing moves until someone approves here.
 */

const ACTION_BADGE = { buy: "badge-up", sell: "badge-down", hold: "badge-neutral" };
const CONF_BADGE = { high: "badge-up", medium: "badge-info", low: "badge-warn" };
const STATUS = {
  pending: ["badge-info", "Awaiting review"],
  approved: ["badge-info", "Approved"],
  executed: ["badge-up", "Executed"],
  rejected: ["badge-neutral", "Rejected"],
  failed: ["badge-down", "Execution failed"],
};

export default function AgentPage() {
  const [proposals, setProposals] = useState([]);
  const [summary, setSummary] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [deciding, setDeciding] = useState(null);

  const load = useCallback(async () => {
    if (!isLoggedIn()) return;
    try {
      const res = await api.get("/agent/proposals");
      setProposals(res.data.proposals || []);
    } catch { /* listing failure is non-fatal */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const propose = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await api.post("/agent/propose", {});
      setSummary(res.data.summary);
      await load();
    } catch (err) {
      const status = err.response?.status;
      setError(
        err.response?.data?.error ||
          (status === 400 ? "Add a holding before running the agent." : "The agent run failed.")
      );
    } finally {
      setRunning(false);
    }
  };

  const decide = async (id, decision) => {
    setDeciding(id);
    setError(null);
    try {
      await api.post("/agent/decide", { proposal_id: id, decision });
    } catch (err) {
      setError(err.response?.data?.error || `Could not ${decision} that proposal.`);
    } finally {
      await load(); // status may have changed even on failure
      setDeciding(null);
    }
  };

  const pending = proposals.filter((p) => p.status === "pending");
  const past = proposals.filter((p) => p.status !== "pending");

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Agent</h1>
          <p className="page-sub">
            The agent proposes trades from stored evidence. It never executes — you decide.
          </p>
        </div>
        <button className="btn btn-primary" onClick={propose} disabled={running}>
          {running ? "Analysing…" : "Propose trades"}
        </button>
      </div>

      {running && <div className="loading-bar mb" />}
      {error && <div className="alert alert-error mb">{error}</div>}
      {summary && <div className="alert alert-info mb">{summary}</div>}

      {pending.length === 0 && past.length === 0 && !error && (
        <div className="card">
          <div className="empty">
            <p className="empty-title">No proposals yet</p>
            <p>Run the agent to get trade proposals backed by your snapshots and backtests.</p>
          </div>
        </div>
      )}

      {pending.map((p) => (
        <article className="card proposal mb" key={p.id}>
          <div className="card-head">
            <div className="proposal-head">
              <span className={`badge ${ACTION_BADGE[p.action]}`}>{p.action.toUpperCase()}</span>
              <span className="proposal-ticker">{p.ticker}</span>
              {p.shares > 0 && <span className="num proposal-shares">{p.shares} shares</span>}
            </div>
            <span className={`badge ${CONF_BADGE[p.confidence] || "badge-neutral"}`}>
              {p.confidence} confidence
            </span>
          </div>

          <div className="card-body">
            <p className="proposal-rationale">{p.rationale}</p>

            {p.evidence_used?.length > 0 && (
              <div className="proposal-block">
                <p className="label">Evidence cited</p>
                <ul className="evidence">
                  {p.evidence_used.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              </div>
            )}

            {p.risks && (
              <div className="proposal-block">
                <p className="label">What would make this wrong</p>
                <p className="proposal-risks">{p.risks}</p>
              </div>
            )}

            <div className="provenance">
              {p.model && <span className="badge badge-neutral">{p.model}</span>}
              {p.snapshot_refs?.length > 0 && (
                <span className="badge badge-neutral" title={p.snapshot_refs.join(", ")}>
                  {p.snapshot_refs.length} snapshot{p.snapshot_refs.length > 1 ? "s" : ""}
                </span>
              )}
              {p.backtest_run_id && (
                <span className="badge badge-neutral" title={p.backtest_run_id}>
                  backtest {p.backtest_run_id.slice(0, 8)}
                </span>
              )}
            </div>

            <div className="proposal-actions">
              <button className="btn btn-accent" disabled={deciding === p.id}
                      onClick={() => decide(p.id, "approve")}>
                {deciding === p.id ? "Working…" : "Approve & execute"}
              </button>
              <button className="btn btn-danger" disabled={deciding === p.id}
                      onClick={() => decide(p.id, "reject")}>
                Reject
              </button>
            </div>
          </div>
        </article>
      ))}

      {past.length > 0 && (
        <section className="card">
          <div className="card-head"><h2 className="card-title">Decision history</h2></div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Action</th><th>Ticker</th><th className="r">Shares</th><th>Status</th><th>Proposed</th></tr>
              </thead>
              <tbody>
                {past.map((p) => {
                  const [cls, text] = STATUS[p.status] || ["badge-neutral", p.status];
                  return (
                    <tr key={p.id}>
                      <td><span className={`badge ${ACTION_BADGE[p.action]}`}>{p.action}</span></td>
                      <td>{p.ticker}</td>
                      <td className="r num">{p.shares || "—"}</td>
                      <td><span className={`badge ${cls}`}>{text}</span></td>
                      <td className="num flat">
                        {p.created_at ? new Date(p.created_at).toLocaleString() : "—"}
                      </td>
                    </tr>
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
