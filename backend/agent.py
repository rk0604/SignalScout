"""
AI portfolio agent — the propose half of a propose → approve → execute loop.

Design constraint: **the agent never writes to the portfolio.** It investigates
using read-only tools, and finishes by submitting structured proposals. A human
approves, and only then does the existing holdings path execute the trade.

Two modes:

  * agentic     — the agent is given tools and runs a loop: form a hypothesis,
                  commission a backtest, read the metrics, refine or try
                  another, then propose citing the runs it actually ran. This
                  is the default.
  * single_shot — one call over evidence gathered up front. Kept because it is
                  the honest baseline to compare the agentic loop against.

This module deliberately knows nothing about Flask or the database. Tools are
executed through a callback supplied by the caller, so the loop can be tested
with fakes and the app keeps ownership of data access.
"""

import os
import json
import time

import anthropic

# Cheapest capable model by default: the loop makes several calls per run, so
# per-token cost matters more here than in a one-shot. Overridable per request
# so the same harness can be pointed at a stronger model for comparison.
DEFAULT_MODEL = "claude-haiku-4-5"
SINGLE_SHOT_MODEL = "claude-opus-5"

# Ceiling on tool-use rounds. This is a safety rail, not a budget one: it stops
# a confused agent looping forever. When it is hit the agent is asked once more,
# with the submit tool forced, so a run always ends with an answer.
MAX_ITERATIONS = 6
MAX_TOKENS = 4000

# Rough public per-million-token prices, used only to attach an estimated cost
# to a run so the UI can show what it spent. Estimates — update if pricing moves.
MODEL_PRICING = {
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00},
    "claude-sonnet-5":   {"input": 3.00, "output": 15.00},
    "claude-opus-5":     {"input": 15.00, "output": 75.00},
}


# --------------------------------------------------------------------------
# Proposal shape
# --------------------------------------------------------------------------

PROPOSAL_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "shares": {
            "type": "integer",
            "description": "Share count for buy/sell; 0 for hold.",
        },
        "rationale": {
            "type": "string",
            "description": "Why this action, referencing the evidence provided.",
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "evidence_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Which specific inputs drove this (e.g. 'MA20/50 golden cross 2026-05-02', 'backtest 6eadf744 Sharpe 0.98').",
        },
        "risks": {
            "type": "string",
            "description": "What would make this proposal wrong.",
        },
    },
    "required": [
        "ticker", "action", "shares", "rationale",
        "confidence", "evidence_used", "risks",
    ],
    "additionalProperties": False,
}

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Two or three sentences on the portfolio's current state.",
        },
        "proposals": {
            "type": "array",
            "description": "Proposed actions. May be empty if no action is warranted.",
            "items": PROPOSAL_ITEM_SCHEMA,
        },
    },
    "required": ["summary", "proposals"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

# Every tool is read-only except submit_proposals, which only ever creates
# pending rows. There is deliberately no tool that can move a position.
TOOL_SCHEMAS = [
    {
        "name": "list_strategies",
        "description": (
            "List the backtestable strategies and the parameters each accepts. "
            "Call this first if you intend to test a strategy, so you use valid "
            "names and parameter ranges."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "run_backtest",
        "description": (
            "Backtest a strategy over historical prices and return its metrics "
            "alongside a benchmark. This is the primary way to test whether a "
            "trading idea has any historical support before proposing it. "
            "Single-ticker strategies take `ticker`; cross-sectional ones take "
            "`universe`. Results are stored and can be cited by id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy": {"type": "string", "description": "Strategy id from list_strategies."},
                "params": {"type": "object", "description": "Strategy parameters; omit to use defaults."},
                "ticker": {"type": "string", "description": "Ticker for single-asset strategies."},
                "universe": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tickers for cross-sectional strategies.",
                },
            },
            "required": ["strategy"],
        },
    },
    {
        "name": "get_holdings",
        "description": "The user's current positions: shares, average cost and latest quote.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_quote",
        "description": "Latest and previous close for one ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_signals",
        "description": "Recent MA20/50 crossover signals for one ticker, from stored price data.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sentiment",
        "description": "Stored news-headline sentiment for one ticker. Lexicon-based and approximate.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "submit_proposals",
        "description": (
            "Submit your final proposals and end the analysis. Call this exactly "
            "once, when you have gathered enough evidence. An empty proposals "
            "list is a valid answer when no action is warranted."
        ),
        "input_schema": PROPOSAL_SCHEMA,
    },
]

TERMINAL_TOOL = "submit_proposals"


_ROLE = """You are a portfolio analyst for SignalScout. You propose trades; you never execute them — a human reviews every proposal before anything happens."""

# Rules that must hold in both modes, so the two are a fair comparison: same
# standards of evidence and disclosure, only the means of gathering differ.
_GROUND_RULES = """Ground rules:
- Reason ONLY from the evidence available to you. Do not use remembered prices, news, or company facts.
- If the evidence is thin or contradictory, say so and propose fewer actions. Deciding not to trade is a legitimate conclusion — but record it: submit a `hold` proposal with shares 0 for each position you reviewed, explaining why no action is warranted. Only return an empty proposals list if there were no positions to review.
- Cite the specific evidence behind each proposal in `evidence_used`. A rationale that cannot point at real evidence should not be proposed.
- State what would make each proposal wrong in `risks`.
- Signals here are lagging indicators validated on limited history. Treat backtest results as weak evidence, not proof, and never imply a predicted outcome.
- Size proposals conservatively relative to existing position sizes.

You are not a licensed financial adviser and this is not financial advice; you are producing an analyst's recommendation for a human to accept or reject."""

AGENTIC_SYSTEM_PROMPT = f"""{_ROLE}

You start with only the current positions. Everything else — signals, sentiment, quotes, backtests — you must retrieve yourself with tools.

How to work:
- Check the signals and sentiment for the positions you are considering.
- Before you cite a trading rule as a reason to act or not act, TEST IT. Call run_backtest on the rule and the ticker in question. Do not claim a strategy underperforms without a backtest id to point at; run at least one backtest before submitting unless the portfolio is empty.
- Use list_strategies if you are unsure which strategy names or parameters are valid.
- Prefer three to five well-chosen tool calls over exhaustive searching. You have a limited number of steps.
- Finish by calling submit_proposals exactly once.
- Include the ids of backtests you ran in `evidence_used`.

{_GROUND_RULES}"""

SINGLE_SHOT_SYSTEM_PROMPT = f"""{_ROLE}

All the evidence available to you is supplied in the user message. You cannot retrieve more, so work with what is there and be explicit about what is missing.

{_GROUND_RULES}"""

# Kept for callers that imported the original name.
SYSTEM_PROMPT = AGENTIC_SYSTEM_PROMPT

# Extended thinking is not available on every model; asking for it on one that
# lacks support is a hard 400 rather than a silent downgrade.
ADAPTIVE_THINKING_MODELS = ("claude-opus-5", "claude-sonnet-5")


class AgentUnavailable(RuntimeError):
    """Raised when the agent cannot run (missing key, upstream failure)."""


def build_evidence(portfolio, signals, sentiment, backtests):
    """
    The full evidence block, gathered up front. Used by single-shot mode.

    Kept as explicit JSON rather than prose so the same inputs can be replayed
    later and produce a comparable decision.
    """
    return json.dumps(
        {
            "portfolio": portfolio,
            "ma_crossover_signals": signals,
            "news_sentiment": sentiment,
            "recent_backtests": backtests,
        },
        indent=2,
        default=str,
    )


def build_starting_context(portfolio):
    """
    The minimal context the agentic loop starts from: positions only.

    Signals, sentiment and backtests are deliberately withheld. Handing the
    agent a pre-assembled dossier would leave it nothing to investigate and
    reduce the loop to a single shot with extra steps — the agent is supposed
    to decide what evidence it needs and go get it.
    """
    return json.dumps(
        {
            "portfolio": portfolio,
            "available_via_tools": [
                "current signals", "news sentiment", "live quotes",
                "backtests of any strategy you want to test",
            ],
        },
        indent=2,
        default=str,
    )


def estimate_cost(model, usage):
    """Rough USD cost for a run, from accumulated token counts."""
    price = MODEL_PRICING.get(model)
    if not price:
        return None
    # Cache reads are heavily discounted and writes carry a premium; without
    # per-model cache pricing, treat them as ordinary input rather than
    # pretending to a precision we do not have.
    input_tokens = usage.get("input", 0) + usage.get("cache_read", 0) + usage.get("cache_write", 0)
    return round(
        input_tokens / 1_000_000 * price["input"]
        + usage.get("output", 0) / 1_000_000 * price["output"],
        6,
    )


def _client():
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise AgentUnavailable(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable the agent."
        )
    return anthropic.Anthropic()


def _accumulate(usage, response):
    u = response.usage
    usage["input"] += getattr(u, "input_tokens", 0) or 0
    usage["output"] += getattr(u, "output_tokens", 0) or 0
    usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
    usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0


def _digest(value, limit=900):
    """Compact a tool result for the audit trail without storing whole payloads."""
    text = json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


# --------------------------------------------------------------------------
# Agentic loop
# --------------------------------------------------------------------------

def run_agentic(evidence_json, execute_tool, model=None, max_iterations=MAX_ITERATIONS):
    """
    Investigate with tools, then propose.

    `execute_tool(name, args) -> dict` is supplied by the caller and is the only
    way this module touches data. Returns the proposal payload plus a full trace
    of what the agent did, so the run can be audited step by step.

    Raises AgentUnavailable if the agent cannot run at all.
    """
    client = _client()
    model = model or DEFAULT_MODEL

    # Cache the system prompt and tool definitions: they are identical on every
    # turn of the loop and every run, and they dominate the input tokens.
    system = [{
        "type": "text",
        "text": AGENTIC_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }]
    tools = [dict(t) for t in TOOL_SCHEMAS]
    tools[-1] = {**tools[-1], "cache_control": {"type": "ephemeral"}}

    messages = [{
        "role": "user",
        "content": (
            "Here is the starting evidence for this portfolio.\n\n"
            f"<evidence>\n{evidence_json}\n</evidence>\n\n"
            "Investigate as needed, then submit at most 3 proposals. Propose "
            "nothing if the evidence does not support acting."
        ),
    }]

    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    trace = []
    steps = 0

    def call(force_submit=False):
        kwargs = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "tools": tools,
            "messages": messages,
        }
        if force_submit:
            kwargs["tool_choice"] = {"type": "tool", "name": TERMINAL_TOOL}
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            raise AgentUnavailable(f"Claude API error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentUnavailable("Could not reach the Claude API.") from e

    def finish(tool_input, stop_reason):
        return {
            "summary": tool_input.get("summary", ""),
            "proposals": (tool_input.get("proposals") or [])[:3],
            "model": model,
            "mode": "agentic",
            "steps": steps,
            "trace": trace,
            "usage": usage,
            "cost_usd": estimate_cost(model, usage),
            "stop_reason": stop_reason,
        }

    for _ in range(max_iterations):
        response = call()
        _accumulate(usage, response)

        if response.stop_reason == "refusal":
            raise AgentUnavailable("The model declined to answer this request.")

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            # Model replied in prose without submitting. Ask once more with the
            # submit tool forced rather than losing the work.
            break

        messages.append({"role": "assistant", "content": response.content})

        # A submit ends the run immediately; any other calls in the same turn
        # are moot because the agent has committed to an answer.
        terminal = next((t for t in tool_uses if t.name == TERMINAL_TOOL), None)
        if terminal:
            steps += 1
            trace.append({"step": steps, "tool": TERMINAL_TOOL, "args": None,
                          "result": "submitted", "ms": 0})
            return finish(terminal.input, "submitted")

        results = []
        for block in tool_uses:
            steps += 1
            started = time.monotonic()
            try:
                output = execute_tool(block.name, block.input or {})
                ok = True
            except Exception as e:  # a failing tool is information, not a crash
                output = {"error": str(e)}
                ok = False
            elapsed = int((time.monotonic() - started) * 1000)

            trace.append({
                "step": steps,
                "tool": block.name,
                "args": block.input,
                "result": _digest(output),
                "ok": ok,
                "ms": elapsed,
            })
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output, default=str),
                **({"is_error": True} if not ok else {}),
            })

        messages.append({"role": "user", "content": results})

    # Out of iterations (or the model stopped talking): force a final answer so
    # a run never ends with nothing to show.
    messages.append({
        "role": "user",
        "content": "Stop investigating and submit your proposals now, based on what you have.",
    })
    response = call(force_submit=True)
    _accumulate(usage, response)

    terminal = next((b for b in response.content
                     if b.type == "tool_use" and b.name == TERMINAL_TOOL), None)
    if not terminal:
        raise AgentUnavailable("The agent did not produce any proposals.")

    steps += 1
    trace.append({"step": steps, "tool": TERMINAL_TOOL, "args": None,
                  "result": "submitted (forced)", "ms": 0})
    return finish(terminal.input, "forced_submit")


# --------------------------------------------------------------------------
# Single-shot (baseline)
# --------------------------------------------------------------------------

def propose(evidence_json, max_proposals=3, model=None):
    """
    One call over pre-gathered evidence, no tools.

    Retained as the baseline the agentic loop is measured against: same
    evidence, same output shape, no investigation.
    """
    client = _client()
    model = model or SINGLE_SHOT_MODEL

    user_message = (
        f"Here is the current evidence.\n\n<evidence>\n{evidence_json}\n</evidence>\n\n"
        f"Propose at most {max_proposals} actions. Propose nothing if the evidence "
        f"does not support acting."
    )

    supports_thinking = any(model.startswith(p) for p in ADAPTIVE_THINKING_MODELS)

    kwargs = {
        "model": model,
        "max_tokens": 8000 if supports_thinking else MAX_TOKENS,
        "system": SINGLE_SHOT_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }
    if supports_thinking:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {
            "effort": "high",
            "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA},
        }
    else:
        # Models without adaptive thinking still need a guaranteed shape: force
        # the submit tool, whose input schema is the proposal schema.
        kwargs["tools"] = [t for t in TOOL_SCHEMAS if t["name"] == TERMINAL_TOOL]
        kwargs["tool_choice"] = {"type": "tool", "name": TERMINAL_TOOL}

    try:
        response = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        raise AgentUnavailable(f"Claude API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AgentUnavailable("Could not reach the Claude API.") from e

    # A refusal returns HTTP 200 with empty or partial content, so check the stop
    # reason before reading content.
    if response.stop_reason == "refusal":
        raise AgentUnavailable("The model declined to answer this request.")

    if supports_thinking:
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise AgentUnavailable("The model returned no proposal content.")
        result = json.loads(text)
    else:
        block = next((b for b in response.content
                      if b.type == "tool_use" and b.name == TERMINAL_TOOL), None)
        if not block:
            raise AgentUnavailable("The model returned no proposal content.")
        result = block.input
    usage = {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
        "cache_read": 0,
        "cache_write": 0,
    }
    return {
        "summary": result.get("summary", ""),
        "proposals": result.get("proposals", []),
        "model": response.model,
        "mode": "single_shot",
        "steps": 1,
        "trace": [],
        "usage": usage,
        "cost_usd": estimate_cost(model, usage),
        "stop_reason": response.stop_reason,
    }
