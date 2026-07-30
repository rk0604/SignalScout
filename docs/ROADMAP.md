# SignalScout — Engineering Roadmap

> **Audience:** human maintainers **and** AI coding agents.
> Each phase is self-contained: it states the goal, the exact files to touch,
> the fixes to fold in, and a machine-checkable **Done when** acceptance test.
> An agent should be able to pick up any unblocked phase without extra context.

**Status legend:** `TODO` · `IN PROGRESS` · `DONE` · `BLOCKED`

---

## North star

The end goal is an **AI agent that manages the portfolio**. This project exists to
demonstrate **reliable, auditable AI-agent workflows**. Therefore *auditability is a
substrate, not a feature*: it is built in from Phase 1, and later phases sit on top of it.

An auditable workflow must answer three questions after the fact:

1. **Who did what, when?** — every state-changing action writes an immutable ledger row.
2. **What did it know?** — every decision references the exact market-data snapshot it
   acted on, by id + timestamp (never a live re-fetch that may have since changed).
3. **Can I replay it?** — ledger + snapshots are enough to reconstruct any decision.

Two consequences reorder the backlog:

- **JWT auth** is foundational: it supplies the *identity* ("who") on every ledger row.
- **Caching yfinance** is foundational: it is the *evidence store* ("what did it know"),
  not merely a performance win.

---

## UI design language — dark Bloomberg-terminal aesthetic

The target look is a **information-dense financial terminal**: near-black canvas, amber
brand accent, monospaced tabular numerics, thin-bordered panels, minimal chrome. This is
a cross-cutting spec — every phase's UI (Phase 4 signals, Phase 5 dashboard, Phase 6
backtesting, Phase 7 realtime) must conform. Migrate the existing ad-hoc styles (`#ffcc00`, `#1a1a1a`,
per-component CSS) onto these shared tokens.

### Design tokens (define once as CSS variables, e.g. `src/index.css`)

```css
:root {
  /* Surfaces — near-black, layered */
  --bg:        #0A0A0A;  /* app canvas            */
  --panel:     #101215;  /* card / panel bg       */
  --panel-2:   #16191D;  /* raised / hover        */
  --border:    #23262B;  /* 1px hairline borders  */
  --grid:      #1B1E22;  /* chart gridlines       */

  /* Brand + data semantics */
  --amber:     #FFB000;  /* primary accent, headers, active state (Bloomberg amber) */
  --up:        #16C784;  /* gains / buy  */
  --down:      #EA3943;  /* losses / sell */
  --cyan:      #35B7F3;  /* links, secondary data */
  --hold:      #A7B0BC;  /* neutral / hold */

  /* Text */
  --text:      #E6E8EB;  /* primary text     */
  --muted:     #8A929E;  /* labels, captions */
  --dim:       #565D66;  /* de-emphasized    */
}
```

### Type system
- **Labels / headers:** sans (keep IBM Plex Sans), `text-transform: uppercase`,
  `letter-spacing: 0.06em`, small (11–13px). This is the "terminal caption" voice.
- **Numbers / data:** monospace with **`font-variant-numeric: tabular-nums`** so columns
  align — use IBM Plex Mono / JetBrains Mono / Roboto Mono. Every price, %, ratio, and
  table cell renders in mono.
- Right-align all numeric columns.

### Component patterns
- **Panels:** flat `--panel` bg, single 1px `--border`, ~2–4px radius (no heavy rounding),
  no drop shadows. Header is a thin bar: uppercase amber title, optional right-aligned
  status (`⟳ updated 2s ago`).
- **Density:** tight padding (8–12px), hairline row separators, no large empty gaps —
  fill the viewport with data (the current dashboard has large dead space; remove it).
- **Semantics:** amber = brand/active, green `--up`, red `--down`, cyan = links, muted
  gray = labels. A number's color always encodes its sign.
- **Motion:** minimal — a subtle amber glow on active/hover only; no bouncy transitions.
- **Optional flair:** a top command/status strip and function-key hints
  (`F1 HELP · F8 CHART`) reinforce the terminal metaphor without extra logic.

### Accessibility
- Verify green/red contrast on `--panel`; pair color with a `▲/▼` glyph or sign so
  meaning survives color-blindness. Support the artifact/theme toggle only insofar as the
  terminal look is intentionally dark-first (a light variant is out of scope).

---

## Cross-cutting foundation (introduced in Phase 1 / Phase 3)

### `audit_log` — append-only ledger (Phase 1)
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `actor_email` | text | derived from JWT, never from request body |
| `action` | text | e.g. `login`, `pin`, `buy`, `sell`, `agent_propose`, `agent_execute` |
| `entity` | text | e.g. ticker or resource id |
| `payload` | JSONB | full request/decision detail |
| `snapshot_ref` | UUID | FK → `market_snapshot.id` when a decision used market data |
| `request_id` | text | correlates related rows |
| `created_at` | timestamptz | server time |

**Rule:** no UPDATE or DELETE path may ever touch this table.

### `market_snapshot` — evidence store (Phase 3)
| column | type | notes |
|---|---|---|
| `id` | UUID PK | |
| `ticker` | text | |
| `kind` | text | `recs` \| `risk` \| `financials` \| `price` \| `sentiment` |
| `payload` | JSONB | the yfinance/derived result |
| `fetched_at` | timestamptz | freshness / TTL basis |

---

## Current state (already completed)

- `DONE` — `requirements.txt` fixed (backend rewritten with `Flask-SQLAlchemy`,
  `bcrypt`, `textblob`; `psycopg2` → `psycopg2-binary`; root file de-duplicated).
- `DONE` — `venv/` and `__pycache__/` untracked; `.gitignore` extended.
- `DONE` — fresh Python 3.13 venv; app boots.
- `DONE` — `db.create_all()` on startup (`backend/app.py`); Neon tables
  `user_data`, `user_holdings` created.
- `DONE` — `backend/.env` (Neon `DATABASE_URL`) + committable `backend/.env.example`.

**Known gaps not yet addressed:** `.git` history still contains the old `venv` and a
leaked `.env` (needs `git filter-repo` to purge + shrink); several small bugs are folded
into the phases below rather than fixed standalone.

---

## Phase overview

| Phase | Theme | Depends on | Effort | Status |
|---|---|---|---|---|
| 1 | Auth (JWT) + audit ledger | — | M | `DONE` |
| 2 | Deploy (Render + Vercel + Neon) | 1 | M | `IN PROGRESS` |
| 3 | Provenance & caching layer | 1 | M | `DONE` |
| 4 | Signals & sentiment (+ finish stubbed modal) | 1, 3 | M | `DONE` |
| 5 | Portfolio analytics dashboard | 3 | M | `TODO` |
| 6 | Backtesting & strategy performance | 3, 4 | M | `TODO` |
| 7 | Realtime prices (WebSocket) | 2 | L | `TODO` |
| 8 | AI agent layer (vision) | 1, 3, 6 | — | `TODO` |

**Recommended order:** 1 → 2 → 3 → 4 → 5 → 6, with 8 as the payoff (7 is optional polish).
Phase 6 gates Phase 8: an agent should only trade a strategy that has been backtested.
Fastest resume impact: **1 → 2 → 5** (secure it, ship it, make it impressive).

---

## Phase 1 — Auth (JWT) + audit ledger  `DONE`

> Shipped on `dev`. `audit_log` is live in Neon; `snapshot_ref` is present but stays
> NULL until Phase 3 creates `market_snapshot`. Token is stored in localStorage
> (httpOnly-cookie upgrade still open). No client-side route guard yet: an
> unauthenticated visitor to `/dashboard` sees an empty shell and is bounced by the
> first 401 — the server-side boundary holds, but a guard would be tidier.

**Goal:** real identity, and the append-only ledger that makes everything auditable.
Closes the "anyone can read anyone's portfolio" hole.

**Backend (`backend/app.py`)**
- Add `PyJWT` to requirements.
- On `/login` success, issue a signed JWT (`sub=email`, `iat`, `exp`); return it.
  Add `SECRET_KEY` to `.env` / `.env.example`.
- Add `@require_auth` decorator: read `Authorization: Bearer <token>`, verify, set
  `g.user_email`. **Rewrite every protected route to take email from the token**, and
  remove `email` from all request bodies / query strings.
- Create `audit_log` table; write one row from each state-changing route
  (`register`, `login`, `pin-stock`, `update-holdings`, `remove-pinned-stock`).
- **Fold in fixes:** `User.password` should not be `unique=True` (app.py:46);
  guard the `.upper()`/`.lower()`-on-`None` 500s (app.py:464, 475, 516).

**Frontend**
- Axios request interceptor attaches `Authorization` from stored token.
- Axios response interceptor: on 401 → redirect to `/`.
- Store token in localStorage for the demo (note: httpOnly cookie is the XSS-safe
  upgrade). Stop using `localStorage.email` as the auth mechanism.

**Done when:** any protected route returns 401 without a valid token; every pin/trade
produces an `audit_log` row queryable by `actor_email`.

---

## Phase 2 — Deploy  `IN PROGRESS`

> Code and config are done: `render.yaml`, `frontend/vercel.json`, debug defaults
> off, `flask init-db`, `/health`, comma-separated CORS origins, `postgres://`
> normalisation. **Remaining work is account-side and must be done by the repo
> owner** — connecting Render and Vercel and pasting env vars. Step-by-step:
> [DEPLOY.md](DEPLOY.md).

**Goal:** a live URL + config hygiene.

- **DB:** Neon (`DONE`).
- **Backend → Render** (chosen over Railway because Render holds long-lived
  WebSocket connections on the free tier, which Phase 7 needs). Add `gunicorn` + start
  command. Move `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `FRONTEND_URL` to env.
  **Turn Flask debug OFF in prod** — currently hardcoded `True` (app.py:23, app.py:736);
  Werkzeug's debugger is RCE if it binds publicly.
- **Frontend → Vercel.** Set `VITE_API_URL` to the Render URL; point backend CORS at the
  Vercel URL.

**Done when:** a stranger can open the live link, register, and log in against Neon.

---

## Phase 3 — Provenance & caching layer  `DONE`

> Shipped on `dev`. `market_snapshot` is live; `audit_log.snapshot_ref` is now
> populated for recommendation snapshots. Not yet done: the `sentiment` kind is
> defined but unused until Phase 4, and there is no snapshot pruning, so the table
> grows without bound (fine at this scale, worth a retention policy later).

**Goal:** every yfinance call becomes a timestamped, reusable snapshot.

- Create `market_snapshot` table (schema above).
- `/fetch-recs`: read fresh snapshots (TTL, e.g. 24h); recompute only on miss and store.
  First call slow, every call after instant. (No-cron equivalent of a precompute job.)
- **Fold in fixes:** the `if not stock_rec` check that returns **400 on success**
  (app.py:243 — it tests the drained dict; should test the result dict); the
  `sumVal == 0 → NaN` case (app.py:217) that poisons ranking.

**Done when:** second `/fetch-recs` returns < 1s; each result row carries a snapshot
id + `fetched_at`.

---

## Phase 4 — Signals, sentiment, stubbed modal  `DONE`

> Shipped on `dev`. Notes for whoever picks this up next:
> - **Sentiment is lexicon-based and approximate.** Most real headlines are worded
>   factually and score neutral; TextBlob knows no finance vocabulary, hence the
>   overlay in `FINANCE_SENTIMENT_TERMS`. Do not read precision into the number.
>   A finance-tuned model (e.g. FinBERT) is the real upgrade.
> - **The news source is fragile by nature.** yfinance's API is primary; the HTML
>   scrape behind it will break again whenever Yahoo changes markup.
> - **The live chart path is unverified against real data** — yfinance was rate
>   limiting throughout. Crossover logic is verified on synthetic series (golden
>   and death cross) and the route is verified serving a snapshot.
> - MA20/50 is a lagging indicator; treat signals as illustrative until Phase 6
>   backtests them.

Three low-risk, high-visibility wins that share the stock modal.

- **Finish the stubbed modal** (`frontend/.../portfolio_component/holdings.jsx:122-124`):
  replace placeholder `<h3>` text with existing `<StockChart>`, `<StockOverview>`,
  `<StockRisk>`, `<SentimentAnalysis>`. Fix the `total_return.toFixed` crash on unpinned
  holdings (holdings.jsx:98).
- **Sentiment scoring:** `get_stock_news` already scrapes headlines — run `TextBlob`
  polarity per headline, aggregate an overall score, return per-article + overall;
  frontend shows a red/green badge. Store headlines+scores as a `sentiment` snapshot.
  (Caveat: the Yahoo HTML scrape is fragile.)
- **MA20/50 crossover:** `calculate_moving_averages` / `generate_trading_signals`
  (app.py:60-70) already exist and are unused. Return MA series + crossover points from
  the chart endpoint; render two MA lines + buy/sell markers on `PriceChart.jsx`.
  Log each signal generation (these are what the Phase 8 agent consumes).

**Done when:** the "signal" in SignalScout visibly exists; the modal is complete for both
holdings and search.

---

## Phase 5 — Portfolio analytics dashboard  `TODO`

**Backend:** one `/portfolio-summary` endpoint (email from token), computed from cached
snapshots: total market value, total cost basis, total unrealized P/L ($ and %),
day change, allocation by ticker (+ sector via `ticker.info`), best/worst performer,
position count.

**Layout** — implements the terminal design language above: near-black canvas, amber
uppercase captions, monospaced tabular numerics, hairline `--border` panels, sign+color
on every number. Dark-first, high density, no dead space.

```
 PORTFOLIO ─────────────────────────────────────────── ⟳ UPDATED 2s AGO
┌───────────────┬───────────────┬───────────────┬───────────────────────┐
│ TOTAL VALUE   │ TOTAL RETURN  │ DAY CHANGE    │ POSITIONS             │
│  48,210.00    │  +6,120.00 ▲  │   −310.00 ▼   │   12                  │
│               │  +14.50%      │   −0.64%      │   3 pinned            │
├───────────────┴───────────────┴───────┬───────┴───────────────────────┤
│ ALLOCATION                            │ TOP MOVERS                     │
│   ◕  NVDA 28 · AAPL 19 · AMZN 14 …    │   ▲ NVDA   +32.10%             │
│      (donut, mono % labels)           │   ▲ AMZN   +12.00%             │
│                                       │   ▼ TSLA    −8.40%             │
├───────────────────────────────────────┴────────────────────────────────┤
│ HOLDINGS                                                                 │
│ TICKER  SHARES     AVG     LAST      VALUE     P/L $    P/L %    TREND    │
│ NVDA        8    25.00   118.00    944.00   +744.00  +372.0%   ▁▂▄▆█     │
│ AAPL       15   180.00   201.30   3019.50   +319.50   +11.8%   ▂▃▃▄▅     │
└─────────────────────────────────────────────────────────────────────────┘
```

- All numeric columns right-aligned, monospace, `tabular-nums`; color = sign.
- Row 1: four KPI stat tiles (amber caption, mono value, colored delta line).
- Row 2: allocation donut (recharts, palette from tokens) + best/worst movers list.
- Row 3: existing holdings grid rebuilt as a dense mono table with P/L columns +
  optional per-row sparkline.
- **Unlocked later:** once `market_snapshot` accumulates daily rows, a "portfolio value
  over time" line chart comes almost free.

**Done when:** `/portfolio-summary` returns correct aggregates for a real account and the
dashboard renders all four tiles + donut + table from live data.

---

## Phase 6 — Backtesting & strategy performance  `TODO`

**Goal:** measure how a strategy (or the agent's decisions) *would have performed* over
history, before risking anything live. This is the empirical, auditable proof that a
signal set is worth acting on — the "performance aspect" of the trading agent.

**Core idea:** a strategy is a pure function `signals(history) -> {date: action}`. Replay
it bar-by-bar over historical prices, simulate fills against a starting cash balance, and
record the resulting equity curve. Every run is reproducible from stored inputs.

**Backend**
- New `backtest_run` table (append-only, audit-aligned): `id, strategy, params (JSONB),
  universe, start_date, end_date, metrics (JSONB), equity_curve (JSONB), snapshot_refs,
  created_at`. A run is immutable evidence, same discipline as `audit_log`.
- Engine (`backend/backtesting/`), no look-ahead bias (only data up to bar *t* informs the
  action at *t*):
  1. Load historical bars from `market_snapshot` / yfinance (reuse Phase 3 data).
  2. Generate signals per bar (start with the Phase 4 MA20/50 crossover; pluggable so the
     Phase 8 agent's policy can be dropped in as just another strategy).
  3. Simulate: apply actions, track cash + positions, mark-to-market each bar. Model
     transaction cost + slippage (assume a fixed bps) so results aren't fantasy.
- **Metrics:** total return, CAGR, annualized volatility, **Sharpe** (and Sortino),
  **max drawdown**, win rate, trade count — **benchmarked against buy-and-hold SPY** over
  the same window (a strategy that loses to buy-and-hold is a red flag, not a success).
- Endpoint `POST /backtest` (auth from token) runs a strategy over a universe + window and
  returns metrics + equity curve; persists a `backtest_run` row.

**Frontend** (terminal design language)
- A "Backtest" panel: pick strategy + universe + date range → run.
- **Equity curve** line chart (strategy vs SPY benchmark) with drawdown shaded underneath.
- A mono metrics table (return, CAGR, Sharpe, Sortino, max DD, win rate, # trades) with the
  benchmark column beside each figure; color = strategy beat/lost vs benchmark.

**Auditability payoff:** every `backtest_run` pins the exact `snapshot_refs` it used, so a
result is reproducible and a later live agent decision can cite the backtest that justified
its policy.

**Done when:** running the MA-crossover strategy over a chosen universe/window returns
Sharpe + max drawdown + an equity curve benchmarked against SPY, and the run is persisted
as an immutable `backtest_run` row that reproduces on re-run.

---

## Phase 7 — Realtime prices (WebSocket)  `TODO`

**Goal:** live-updating quotes. **Lowest priority** — display-only; the agent reasons over
discrete snapshots, not ephemeral ticks.

- Backend `Flask-SocketIO` + background poller emitting to subscribed clients.
  Honest caveat: yfinance has no streaming feed — poll every N seconds (pseudo-realtime).
  True streaming needs Finnhub/Polygon (free tiers, real WS feeds).
- Frontend `socket.io-client` subscribes to on-screen tickers.
- Requires Render backend (Vercel serverless cannot hold socket connections) — see Phase 2.

**Done when:** on-screen quotes update without a manual refresh.

---

## Phase 8 — AI agent layer (vision)  `TODO`

Everything above is scaffolding for this. The agent gets **no direct DB write access**;
it runs a **propose → approve → execute** loop:

1. Reads signals (Phase 4) + snapshots (Phase 3), and its policy is one that has been
   validated by a Phase 6 backtest (cite the `backtest_run` that justifies it).
2. Writes a *proposed* action to `audit_log` with its reasoning + `snapshot_ref`.
3. A human (or policy) approves → a second ledger row records execution.
4. Any decision is replayable from ledger + snapshot, and its expected performance is
   traceable to a persisted backtest.

**Done when:** an agent can propose a trade, the proposal + approval + execution are three
linked `audit_log` rows, the decision is replayable from stored evidence, and the policy it
used points to a `backtest_run`.
