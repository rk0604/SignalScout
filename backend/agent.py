"""
AI portfolio agent — the propose half of a propose → approve → execute loop.

Design constraint: **the agent never writes to the portfolio.** It reads
evidence (cached market snapshots, MA crossover signals, backtest results,
current holdings) and returns structured proposals. A human approves, and only
then does the existing holdings path execute the trade.

Every proposal carries the snapshot it reasoned over and the backtest that
validated its strategy, so a decision can be audited after the fact rather than
taken on faith.
"""

import os
import json

import anthropic

MODEL = "claude-opus-5"

# The response shape is constrained by schema rather than parsed out of prose,
# so a malformed proposal fails at the API boundary instead of downstream.
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
            "items": {
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
                        "description": "Which specific inputs drove this (e.g. 'MA20/50 golden cross 2026-05-02').",
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
            },
        },
    },
    "required": ["summary", "proposals"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are a portfolio analyst for SignalScout. You propose trades; you never execute them — a human reviews every proposal before anything happens.

Ground rules:
- Reason ONLY from the evidence in the user message. Do not use remembered prices,
  news, or company facts; the evidence block is the entire world you can see.
- If the evidence is thin or contradictory, say so and propose fewer actions, or
  none. An empty proposal list is a valid and often correct answer.
- Cite the specific evidence behind each proposal in `evidence_used`. A rationale
  that cannot point at provided evidence should not be proposed.
- State what would make each proposal wrong in `risks`.
- Signals here are lagging indicators validated on limited history. Treat backtest
  results as weak evidence, not proof, and never imply a predicted outcome.
- Size proposals conservatively relative to existing position sizes.

You are not a licensed financial adviser and this is not financial advice; you are
producing an analyst's recommendation for a human to accept or reject."""


class AgentUnavailable(RuntimeError):
    """Raised when the agent cannot run (missing key, upstream failure)."""


def build_evidence(portfolio, signals, sentiment, backtests):
    """
    Assemble the evidence block the agent reasons over.

    Kept as explicit JSON rather than prose so the same inputs can be replayed
    later and produce a comparable decision.
    """
    return json.dumps(
        {
            "portfolio": portfolio,
            "ma_crossover_signals": signals,
            "news_sentiment": sentiment,
            "backtest_results": backtests,
        },
        indent=2,
        default=str,
    )


def propose(evidence_json, max_proposals=3):
    """
    Ask the model for trade proposals over the given evidence.

    Returns the parsed proposal dict plus usage metadata. Raises
    AgentUnavailable when the agent cannot run at all.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise AgentUnavailable(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env to enable the agent."
        )

    client = anthropic.Anthropic()

    user_message = (
        f"Here is the current evidence.\n\n<evidence>\n{evidence_json}\n</evidence>\n\n"
        f"Propose at most {max_proposals} actions. Propose nothing if the evidence "
        f"does not support acting."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": PROPOSAL_SCHEMA},
            },
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIStatusError as e:
        raise AgentUnavailable(f"Claude API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise AgentUnavailable("Could not reach the Claude API.") from e

    # A refusal returns HTTP 200 with empty or partial content, so check the stop
    # reason before reading content.
    if response.stop_reason == "refusal":
        raise AgentUnavailable("The model declined to answer this request.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise AgentUnavailable("The model returned no proposal content.")

    result = json.loads(text)
    return {
        "summary": result.get("summary", ""),
        "proposals": result.get("proposals", []),
        "model": response.model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }
