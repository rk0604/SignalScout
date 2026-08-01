import { useState, useEffect, useCallback, Fragment } from "react";
import api, { isLoggedIn } from "../api/client";
import RunTrace from "../components/agent/RunTrace";
import "./pages.css";

/*
 * Agent page — the human half of the propose → approve → execute loop.
 * The agent writes proposals; nothing moves until someone approves here.
 *
 * In agentic mode the agent investigates with tools first, so the run trace is
 * shown alongside the proposals: the reasoning is auditable, not just asserted.
 */

const MODES = [
  { id: "agentic", label: "Agentic (tools)", hint: "Investigates with tools and commissions its own backtests." },
  { id: "single_shot", label: "Single shot", hint: "One call over pre-gathered evidence. The baseline." },
];

const MODELS = [
  { id: "", label: "Default" },
  { id: "claude-haiku-4-5", label: "Haiku 4.5 (cheapest)" },
  { id: "claude-sonnet-5", label: "Sonnet 5" },
  { id: "claude-opus-5", label: "Opus 5" },
];

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
  const [openId, setOpenId] = useState(null); // expanded past decision
  const [mode, setMode] = useState("agentic");
  const [model, setModel] = useState("");
  const [lastRun, setLastRun] = useState(null);

  const load = useCallback(async () => {
    if (!isLoggedIn()) return;
    try {
      const res = await api.get("/agent/proposals");
      setProposals(res.data.proposals || []);
    } catch { /* listing failure is non-fatal */ }
  }, []);

  // Show the most recent investigation on arrival, not just right after a run:
  // the trace is the record of how the standing proposals came about.
  const loadLastRun = useCallback(async () => {
    if (!isLoggedIn()) return;
    try {
      const res = await api.get("/agent/runs");
      const latest = (res.data.runs || [])[0];
      if (latest) {
        setLastRun(latest);
        if (latest.summary) setSummary(latest.summary);
      }
    } catch { /* non-fatal */ }
  }, []);

  useEffect(() => { load(); loadLastRun(); }, [load, loadLastRun]);

  const propose = async () => {
    setRunning(true);
    setError(null);
    setLastRun(null);
    try {
      const res = await api.post("/agent/propose", { mode, ...(model ? { model } : {}) });
      setSummary(res.data.summary);
      setLastRun(res.data);
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
        <div className="agent-controls">
          <label className="agent-control">
            <span className="label">Mode</span>
            <select className="field" value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <label className="agent-control">
            <span className="label">Model</span>
            <select className="field" value={model} onChange={(e) => setModel(e.target.value)}>
              {MODELS.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </label>
          <button className="btn btn-primary" onClick={propose} disabled={running}>
            {running ? "Investigating…" : "Propose trades"}
          </button>
        </div>
      </div>

      <p className="agent-mode-hint">{MODES.find((m) => m.id === mode)?.hint}</p>

      {running && <div className="loading-bar mb" />}
      {error && <div className="alert alert-error mb">{error}</div>}

      <RunTrace run={lastRun} />

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
          <div className="card-head">
            <h2 className="card-title">Decision history</h2>
            <span className="label">Click a row to see the agent&apos;s reasoning</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Action</th><th>Ticker</th><th className="r">Shares</th>
                  <th>Status</th><th>Proposed</th><th></th>
                </tr>
              </thead>
              <tbody>
                {past.map((p) => {
                  const [cls, text] = STATUS[p.status] || ["badge-neutral", p.status];
                  const open = openId === p.id;
                  return (
                    <Fragment key={p.id}>
                      <tr className="row-clickable"
                          onClick={() => setOpenId(open ? null : p.id)}>
                        <td><span className={`badge ${ACTION_BADGE[p.action]}`}>{p.action}</span></td>
                        <td>{p.ticker}</td>
                        <td className="r num">{p.shares || "—"}</td>
                        <td><span className={`badge ${cls}`}>{text}</span></td>
                        <td className="num flat">
                          {p.created_at ? new Date(p.created_at).toLocaleString() : "—"}
                        </td>
                        <td className="r"><span className="disclose">{open ? "Hide" : "Reasoning"}</span></td>
                      </tr>
                      {open && (
                        <tr className="detail-row">
                          <td colSpan={6}>
                            <div className="reasoning">
                              {p.rationale && (
                                <p className="proposal-rationale">{p.rationale}</p>
                              )}
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
                              {p.decision_note && (
                                <div className="proposal-block">
                                  <p className="label">Your note on the decision</p>
                                  <p className="proposal-risks">{p.decision_note}</p>
                                </div>
                              )}
                              <div className="provenance">
                                {p.confidence && (
                                  <span className={`badge ${CONF_BADGE[p.confidence] || "badge-neutral"}`}>
                                    {p.confidence} confidence
                                  </span>
                                )}
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
                            </div>
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
