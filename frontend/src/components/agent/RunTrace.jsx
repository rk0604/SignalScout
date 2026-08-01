import PropTypes from "prop-types";
import "./runTrace.css";

/*
 * The agent's investigation, step by step.
 *
 * This is the point of the agentic mode: the conclusion is ordinary, but the
 * path to it — which signals it checked, which strategies it chose to backtest,
 * what came back — is what makes the decision reviewable rather than asserted.
 */

const TOOL_META = {
  get_holdings:     ["Read portfolio", "read"],
  get_signals:      ["Checked signals", "read"],
  get_sentiment:    ["Checked sentiment", "read"],
  get_quote:        ["Fetched quote", "read"],
  list_strategies:  ["Listed strategies", "read"],
  run_backtest:     ["Ran backtest", "test"],
  submit_proposals: ["Submitted proposals", "done"],
};

/* Tool results are stored as a truncated JSON digest; parse when we can so the
   interesting fields can be surfaced, and fall back to the raw text. */
function parseResult(result) {
  if (typeof result !== "string") return null;
  try {
    return JSON.parse(result);
  } catch {
    return null;
  }
}

function stepDetail(step) {
  const args = step.args || {};
  if (step.tool === "run_backtest") {
    const target = args.ticker || (args.universe || []).join(", ");
    return [args.strategy, target].filter(Boolean).join(" on ");
  }
  return args.ticker || "";
}

function Outcome({ step }) {
  const parsed = parseResult(step.result);
  if (!parsed) return null;

  if (step.tool === "run_backtest" && parsed.metrics) {
    const m = parsed.metrics;
    const beat = m.beat_benchmark;
    return (
      <span className={`trace-outcome ${beat ? "up" : "down"}`}>
        {m.total_return_pct != null ? `${m.total_return_pct.toFixed(1)}%` : "—"}
        {parsed.benchmark?.total_return_pct != null &&
          ` vs ${parsed.benchmark.total_return_pct.toFixed(1)}% benchmark`}
        {beat != null && (beat ? " · beat" : " · underperformed")}
      </span>
    );
  }
  if (parsed.error) return <span className="trace-outcome down">{parsed.error}</span>;
  if (parsed.note) return <span className="trace-outcome flat">{parsed.note}</span>;
  if (step.tool === "get_signals" && Array.isArray(parsed.signals)) {
    const last = parsed.signals[parsed.signals.length - 1];
    return (
      <span className="trace-outcome flat">
        {parsed.signals.length
          ? `${parsed.signals.length} signals · latest ${last.signal} ${last.date}`
          : "no crossovers"}
      </span>
    );
  }
  if (step.tool === "get_sentiment" && parsed.overall_sentiment) {
    const s = parsed.overall_sentiment;
    return <span className="trace-outcome flat">{s.label} · {s.headline_count} headlines</span>;
  }
  if (step.tool === "get_quote" && parsed.price != null) {
    return <span className="trace-outcome flat">${parsed.price.toFixed(2)}</span>;
  }
  if (step.tool === "get_holdings" && Array.isArray(parsed.holdings)) {
    return <span className="trace-outcome flat">{parsed.holdings.length} positions</span>;
  }
  return null;
}

Outcome.propTypes = { step: PropTypes.object.isRequired };

export default function RunTrace({ run }) {
  if (!run?.trace?.length) return null;

  const backtestCount = run.trace.filter((s) => s.tool === "run_backtest").length;
  // A live response reports usage as a dict; a stored run has flat columns.
  const totalTokens = run.usage
    ? (run.usage.input || 0) + (run.usage.output || 0)
    : (run.input_tokens || 0) + (run.output_tokens || 0);

  return (
    <section className="card mb">
      <div className="card-head">
        <div>
          <h2 className="card-title">Investigation</h2>
          <p className="card-sub">
            {run.steps} step{run.steps === 1 ? "" : "s"}
            {backtestCount > 0 && ` · ${backtestCount} backtest${backtestCount === 1 ? "" : "s"} commissioned`}
          </p>
        </div>
        <div className="trace-meta">
          {run.model && <span className="badge badge-neutral">{run.model}</span>}
          {run.mode && <span className="badge badge-info">{run.mode.replace("_", " ")}</span>}
          {run.cost_usd != null && (
            <span className="badge badge-neutral" title="Estimated from token usage">
              ${run.cost_usd < 0.01 ? run.cost_usd.toFixed(4) : run.cost_usd.toFixed(3)}
            </span>
          )}
          {totalTokens > 0 && (
            <span className="badge badge-neutral">{(totalTokens / 1000).toFixed(1)}k tokens</span>
          )}
        </div>
      </div>

      <div className="card-body">
        <ol className="trace">
          {run.trace.map((step) => {
            const [label, kind] = TOOL_META[step.tool] || [step.tool, "read"];
            const detail = stepDetail(step);
            return (
              <li className={`trace-step is-${kind}${step.ok === false ? " is-failed" : ""}`}
                  key={step.step}>
                <span className="trace-dot" aria-hidden="true" />
                <span className="trace-n num">{step.step}</span>
                <span className="trace-label">{label}</span>
                {detail && <span className="trace-detail num">{detail}</span>}
                <Outcome step={step} />
                {step.ms > 0 && <span className="trace-ms num">{step.ms}ms</span>}
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}

RunTrace.propTypes = {
  run: PropTypes.shape({
    steps: PropTypes.number,
    model: PropTypes.string,
    mode: PropTypes.string,
    cost_usd: PropTypes.number,
    usage: PropTypes.object,
    input_tokens: PropTypes.number,
    output_tokens: PropTypes.number,
    trace: PropTypes.array,
  }),
};
