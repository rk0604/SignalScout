# SignalScout 📈

Portfolio analytics with an **auditable AI trading agent**. SignalScout tracks a
stock portfolio, backtests trading strategies against historical prices, and
runs an AI agent that investigates with tools and proposes trades — where every
proposal, the evidence behind it, and every human decision is recorded in an
append-only audit ledger.

The emphasis is on **reliable, auditable agent workflows**: the agent never
executes a trade, every backtest it runs is stored and reproducible, and its
whole investigation (which tools it called, what came back) is reviewable.

---

## Contents

1. [Features](#features)
2. [Tech stack](#tech-stack)
3. [Quickstart (fresh machine)](#quickstart-fresh-machine)
4. [Database setup](#database-setup)
5. [Environment variables](#environment-variables)
6. [The AI agent](#the-ai-agent)
7. [Backtesting](#backtesting)
8. [Project structure](#project-structure)
9. [Troubleshooting](#troubleshooting)
10. [Deployment](#deployment)

---

## Features

- **Portfolio dashboard** — holdings, allocation, day change, live quotes over WebSocket
- **Research** — per-ticker price + moving-average chart, risk metrics, fundamentals, news sentiment, analyst consensus
- **Backtesting** — five strategies from a trend-following crossover up to cross-sectional momentum, priced with costs + slippage against a fair benchmark, with a human notes layer on each run
- **AI agent** — a tool-using loop (`claude-*`) that checks signals, commissions its own backtests, and proposes trades; a human approves, and only then does anything execute
- **Audit ledger** — append-only record of every state change (sign-ins, trades, agent proposals, tool calls, decisions) with the evidence snapshot behind each
- **Auth** — JWT bearer tokens, bcrypt-hashed passwords; identity is always derived from the token, never the request body

---

## Tech stack

**Backend:** Flask 3, Flask-SQLAlchemy, Flask-SocketIO, PyJWT, bcrypt, yfinance
(+ curl_cffi), pandas/numpy, TextBlob, anthropic, gunicorn
**Frontend:** React 18, Vite 6, React Router 7, recharts, axios, socket.io-client
**Database:** PostgreSQL (built for [Neon](https://neon.tech) serverless)

---

## Quickstart (fresh machine)

Prerequisites: **Python 3.11+**, **Node 18+**, and a **PostgreSQL connection
string** (a free Neon database works out of the box).

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows:        venv\Scripts\activate
# macOS/Linux:    source venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` from the template and fill it in:

```bash
cp .env.example .env
```

At minimum set `DATABASE_URL` and `SECRET_KEY`. Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then start the backend — **the database schema is created automatically on
first boot** (see [Database setup](#database-setup)):

```bash
python app.py
```

API runs at `http://127.0.0.1:5000`. Health check: `GET /health`.

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_URL defaults to http://127.0.0.1:5000
npm run dev
```

App runs at `http://localhost:5173`. Register an account and sign in.

> The agent is optional. Without `ANTHROPIC_API_KEY` set, the **Agent** page's
> Propose button returns a friendly 503 and everything else works normally.

---

## Database setup

**No manual SQL is required — setup is autonomous.** On startup (`python app.py`)
and via the CLI command below, the app runs `db.create_all()` plus a set of
additive migrations, which create every table and add any columns introduced
after a table already existed. Point `DATABASE_URL` at an empty database and it
provisions itself.

To provision without starting the server (useful in CI or a deploy step):

```bash
cd backend
flask --app app init-db
```

Tables created: `user_data`, `user_holdings`, `market_snapshot`,
`backtest_run`, `agent_proposal`, `agent_run`, `audit_log`.

### Maintenance: snapshot retention

`market_snapshot` is both a cache and an evidence store, so it grows over time.
Prune stale cache rows while **preserving any cited as evidence** (by a backtest,
proposal, or audit row) — pruning never breaks reproducibility:

```bash
flask --app app prune-snapshots --days 90 --dry-run   # preview
flask --app app prune-snapshots --days 90             # delete
```

Run it manually, or on a schedule (e.g. Render Cron) once deployed.

### Optional: provision by hand

If you'd rather run raw SQL against Neon (e.g. to inspect or pre-create the
schema), [`backend/schema.sql`](backend/schema.sql) contains the full
`CREATE TABLE` DDL. It's generated from the models and is idempotent
(`CREATE TABLE IF NOT EXISTS`), but the boot-time path above is the source of
truth — you never *need* to run it.

```bash
psql "$DATABASE_URL" -f backend/schema.sql
```

---

## Environment variables

Backend (`backend/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ | Postgres connection string. `postgres://` is normalised to `postgresql://` automatically. |
| `SECRET_KEY` | ✅ | Signs JWTs. The app refuses to start without it. |
| `ANTHROPIC_API_KEY` | — | Enables the AI agent. Without it, agent routes return 503 and nothing else is affected. |
| `FRONTEND_URL` | — | Allowed CORS origin(s), comma-separated. Defaults to `http://localhost:5173`. |
| `JWT_EXP_HOURS` | — | Token lifetime in hours (default 24). |
| `QUOTE_POLL_SECONDS` | — | Seconds between realtime quote pushes (default 30). |
| `FLASK_DEBUG` | — | `1` enables the reloader/debugger locally. Leave unset in production. |

Frontend (`frontend/.env`):

| Variable | Required | Purpose |
|---|---|---|
| `VITE_API_URL` | ✅ | Backend origin. Defaults to `http://127.0.0.1:5000` locally; set to the deployed API in production. |

---

## The AI agent

The agent runs a **propose → approve → execute** loop and never touches the
portfolio directly.

- **Agentic mode (default):** the agent gets read-only tools
  (`list_strategies`, `run_backtest`, `get_holdings`, `get_quote`,
  `get_signals`, `get_sentiment`) plus a terminal `submit_proposals`. It starts
  from your positions only and must investigate — including running its own
  backtests — before proposing. The full tool trace is stored as an `agent_run`
  and shown on the Agent page.
- **Single-shot mode:** one call over pre-gathered evidence, kept as a baseline.
- **Model routing:** choose Haiku (cheapest, default), Sonnet, or Opus per run.
  A typical agentic run on Haiku costs roughly **$0.03–0.05**.

Every proposal is written with the snapshots it saw and the backtest that
validated its reasoning; approvals/rejections are appended to the audit ledger.

---

## Backtesting

A strategy is a pure function of price history (`closes → position per bar`),
so runs are deterministic and reproducible. Signals are shifted one bar forward
to prevent look-ahead bias, and every run is priced with commission + slippage
against a fair benchmark (buy-and-hold, or equal-weight for a universe).

| Level | Strategy | Kind |
|---|---|---|
| L1 | Moving-average crossover | Trend following |
| L2 | RSI mean reversion | Mean reversion |
| L3 | Bollinger-band reversion | Mean reversion |
| L4 | Time-series momentum + vol targeting | Systematic |
| L5 | Cross-sectional momentum | Systematic (multi-asset) |

Strategy definitions and their parameter schemas live in
[`backend/backtesting.py`](backend/backtesting.py) (`STRATEGY_SPECS`) and are
served to the UI via `GET /strategies`, so the form, validation, and the
agent's tool all read from one definition.

---

## Project structure

```
signalscout/
├── backend/
│   ├── app.py            # Flask app: routes, models, auth, sockets, migrations
│   ├── agent.py          # AI agent: tool-use loop + single-shot baseline
│   ├── backtesting.py    # Strategies + single-asset and portfolio simulators
│   ├── schema.sql        # Optional manual DDL (auto-generated from models)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/pages/        # Overview, Research, Backtest, Agent, Activity
│   ├── src/components/   # stock drawer, agent trace, backtest notes, layout
│   ├── src/api/          # axios client + realtime socket
│   └── .env.example
└── docs/
    ├── ROADMAP.md
    └── DEPLOY.md         # Render + Vercel deployment guide
```

---

## Troubleshooting

- **`SECRET_KEY is not set`** — add it to `backend/.env`; generate one with the command above.
- **`DATABASE_URL is not set`** — the backend needs a Postgres URL to start.
- **Agent returns 503** — `ANTHROPIC_API_KEY` isn't set (or is invalid). This is expected until you add it; restart the backend after editing `.env`, since env is read only at startup.
- **yfinance rate limits / empty data** — `curl_cffi` (in requirements) lets yfinance impersonate a browser and avoids most 429s. If you still get rate-limited, wait a few minutes; cached snapshots keep the app usable.
- **Neon “SSL connection closed”** — expected when Neon scales to zero; the pool is configured with `pool_pre_ping` to reconnect transparently.

---

## Deployment

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for the Render (backend) + Vercel
(frontend) walkthrough. In production, run `flask --app app init-db` once as a
release step, or let the first boot provision the schema.
