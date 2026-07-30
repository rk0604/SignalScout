import { useState, useEffect, useCallback } from "react";
import api, { isLoggedIn } from "../../api/client";
import "./agent.css";

/*
 * Agent panel — the human half of the propose → approve → execute loop.
 *
 * The agent cannot move money: it writes proposals, and nothing happens until
 * someone here approves. Every proposal shows the reasoning, the evidence it
 * cited, and what would make it wrong, so a decision is reviewable rather than
 * a yes/no on an opaque suggestion.
 */

const CONFIDENCE_TONE = { high: "tw-up", medium: "tw-flat", low: "tw-down" };

const ACTION_TONE = { buy: "tw-up", sell: "tw-down", hold: "tw-flat" };

const STATUS_LABEL = {
  pending: "awaiting review",
  approved: "approved",
  executed: "executed",
  rejected: "rejected",
  failed: "execution failed",
};

export default function AgentPanel() {
  const [proposals, setProposals] = useState([]);
  const [summary, setSummary] = useState(null);
  const [isProposing, setIsProposing] = useState(false);
  const [error, setError] = useState(null);
  const [deciding, setDeciding] = useState(null); // proposal id being acted on

  const loadProposals = useCallback(async () => {
    if (!isLoggedIn()) return;
    try {
      const response = await api.get("/agent/proposals");
      setProposals(response.data.proposals || []);
    } catch {
      /* listing failures are non-fatal; the panel still works */
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(loadProposals, 500);
    return () => clearTimeout(timer);
  }, [loadProposals]);

  const runAgent = async () => {
    setIsProposing(true);
    setError(null);
    try {
      const response = await api.post("/agent/propose", {});
      setSummary(response.data.summary);
      await loadProposals();
    } catch (err) {
      const status = err.response?.status;
      // 503 means the agent isn't configured — show the actionable message.
      setError(
        err.response?.data?.error ||
          (status === 400 ? "Add a holding before running the agent." : "Agent run failed")
      );
    } finally {
      setIsProposing(false);
    }
  };

  const decide = async (id, decision) => {
    setDeciding(id);
    setError(null);
    try {
      await api.post("/agent/decide", { proposal_id: id, decision });
      await loadProposals();
    } catch (err) {
      setError(err.response?.data?.error || `Could not ${decision} the proposal`);
      await loadProposals(); // status may still have changed (e.g. failed execution)
    } finally {
      setDeciding(null);
    }
  };

  const pending = proposals.filter((p) => p.status === "pending");
  const history = proposals.filter((p) => p.status !== "pending");

  return (
    <section className="agent-panel">
      <header className="agent-header">
        <h3 className="agent-title">Agent</h3>
        <button className="agent-run" onClick={runAgent} disabled={isProposing}>
          {isProposing ? "Analysing…" : "Propose trades"}
        </button>
      </header>

      <p className="tw-label agent-note">
        The agent proposes; it never executes. Nothing happens until you approve.
      </p>

      {error && <p className="agent-error tw-label">{error}</p>}
      {summary && <p className="agent-summary">{summary}</p>}

      {pending.length === 0 && history.length === 0 && !error && (
        <p className="tw-label agent-empty">No proposals yet.</p>
      )}

      {pending.map((p) => (
        <article key={p.id} className="proposal">
          <div className="proposal-head">
            <span className={`proposal-action ${ACTION_TONE[p.action] || ""}`}>
              {p.action.toUpperCase()}
            </span>
            <span className="proposal-ticker">{p.ticker}</span>
            {p.shares > 0 && <span className="tw-num proposal-shares">{p.shares} sh</span>}
            <span className={`tw-label ${CONFIDENCE_TONE[p.confidence] || ""}`}>
              {p.confidence} confidence
            </span>
          </div>

          <p className="proposal-rationale">{p.rationale}</p>

          {p.evidence_used?.length > 0 && (
            <ul className="proposal-evidence">
              {p.evidence_used.map((e, i) => (
                <li key={i} className="tw-label">· {e}</li>
              ))}
            </ul>
          )}

          {p.risks && (
            <p className="proposal-risks">
              <span className="tw-label">What would make this wrong: </span>
              {p.risks}
            </p>
          )}

          <div className="proposal-provenance tw-label">
            {p.model && <span>{p.model}</span>}
            {p.snapshot_refs?.length > 0 && (
              <span title={p.snapshot_refs.join(", ")}>
                {p.snapshot_refs.length} snapshot{p.snapshot_refs.length > 1 ? "s" : ""}
              </span>
            )}
            {p.backtest_run_id && (
              <span title={`Backtest ${p.backtest_run_id}`}>
                backtest {p.backtest_run_id.slice(0, 8)}
              </span>
            )}
          </div>

          <div className="proposal-actions">
            <button
              className="proposal-approve"
              onClick={() => decide(p.id, "approve")}
              disabled={deciding === p.id}
            >
              {deciding === p.id ? "…" : "Approve"}
            </button>
            <button
              className="proposal-reject"
              onClick={() => decide(p.id, "reject")}
              disabled={deciding === p.id}
            >
              Reject
            </button>
          </div>
        </article>
      ))}

      {history.length > 0 && (
        <>
          <p className="tw-label agent-history-label">Decision history</p>
          <div className="history-scroll">
            <table className="history-table">
              <tbody>
                {history.map((p) => (
                  <tr key={p.id}>
                    <td className={ACTION_TONE[p.action] || ""}>{p.action}</td>
                    <td className="pos-ticker">{p.ticker}</td>
                    <td className="tw-num num">{p.shares || "—"}</td>
                    <td className="tw-label">{STATUS_LABEL[p.status] || p.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
