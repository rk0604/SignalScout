# Deploying SignalScout

Three pieces: **Neon** (database, already set up), **Render** (Flask API),
**Vercel** (React frontend).

The repo is already configured for this — `render.yaml` and `frontend/vercel.json`
exist, debug defaults to off, and `flask --app app init-db` creates tables. What
remains is connecting the services and pasting environment variables, which has to
be done from your own accounts.

> **Order matters.** Deploy the backend first: the frontend needs the API URL, and
> the backend needs the frontend URL for CORS. You will set the backend's
> `FRONTEND_URL` twice — once with a placeholder, once for real (step 4).

---

## 0. Prerequisites

- Code pushed to GitHub (branch `main` is the deploy branch; `dev` is for iteration).
- Your Neon `DATABASE_URL`, in the form
  `postgresql://user:password@host/dbname?sslmode=require`.
- A JWT secret. Generate one — **do not reuse the local dev value**:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 1. Backend → Render

1. Render dashboard → **New** → **Blueprint**.
2. Connect the `SignalScout` repo and pick branch `main`. Render reads
   [`render.yaml`](../render.yaml) and proposes a service named `signalscout-api`.
3. It will prompt for the three secrets marked `sync: false`:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | your Neon connection string |
   | `SECRET_KEY` | the hex string generated above |
   | `FRONTEND_URL` | `http://localhost:5173` for now — corrected in step 4 |

4. Apply. Render installs deps, runs `flask --app app init-db` (creating
   `user_data`, `user_holdings`, `audit_log` if absent), then starts gunicorn.

Note the service URL, e.g. `https://signalscout-api.onrender.com`.

**Verify:**

```bash
curl https://signalscout-api.onrender.com/health
```

Expect `{"status":"ok"}`. Then confirm auth is enforced — this must be **401**, not 200:

```bash
curl -o /dev/null -w "%{http_code}\n" https://signalscout-api.onrender.com/get-holdings
```

> **Free-tier cold starts.** Render idles the service after ~15 minutes; the next
> request can take 30–60s. Neon also scales to zero, which is why the app enables
> `pool_pre_ping` (otherwise the first query after idle fails with
> "SSL connection has been closed unexpectedly").

---

## 2. Frontend → Vercel

1. Vercel → **Add New** → **Project** → import the `SignalScout` repo.
2. Set **Root Directory** to `frontend`. Vercel then reads
   [`frontend/vercel.json`](../frontend/vercel.json) (Vite preset, `dist` output,
   and the SPA rewrite that keeps `/dashboard` from 404ing on a direct load).
3. Add an environment variable:

   | Variable | Value |
   |---|---|
   | `VITE_API_URL` | your Render URL, e.g. `https://signalscout-api.onrender.com` |

   No trailing slash. This is baked in at **build** time, so changing it later
   requires a redeploy, not just a restart.
4. Deploy, and note the URL, e.g. `https://signalscout.vercel.app`.

---

## 3. Point CORS at the real frontend

Back in Render → `signalscout-api` → **Environment**, set:

```
FRONTEND_URL=https://signalscout.vercel.app,http://localhost:5173
```

Comma-separated, so the deployed site and local dev both work. Save; Render
redeploys. **Without this the browser blocks every API call** even though the API
itself is healthy — the tell is a CORS error in the console while `curl` succeeds.

---

## 4. Verify end to end

On the Vercel URL:

1. **Sign Up** → register an account.
2. Log in → you should land on `/dashboard`.
3. Open DevTools → Application → Local Storage: a `token` with three
   dot-separated segments should be present.
4. Network tab: `/get-holdings` returns **200** and its request carries an
   `Authorization: Bearer …` header.
5. Pin a ticker, then confirm it was recorded in the ledger (Neon SQL editor):

```sql
SELECT created_at, actor_email, action, entity FROM audit_log ORDER BY created_at DESC LIMIT 10;
```

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Build fails: `SECRET_KEY is not set` | The app refuses to start without it — add it in Render's env vars. |
| `psycopg2.OperationalError: SSL connection has been closed unexpectedly` | Neon scaled to zero. `pool_pre_ping` handles this; if it recurs, the connection string is likely missing `?sslmode=require`. |
| CORS error in console, but `curl` works | `FRONTEND_URL` on Render doesn't match the Vercel origin exactly (scheme and subdomain must match). |
| `/dashboard` 404s on refresh | The SPA rewrite isn't active — check Root Directory is `frontend` so `vercel.json` is picked up. |
| Login works, then everything 401s | `JWT_EXP_HOURS` elapsed, or `SECRET_KEY` changed between deploys, invalidating existing tokens. |
| Every request is slow the first time | Render + Neon cold start on the free tier. |
| `/fetch-recs` 500s or times out | yfinance rate limiting. Phase 3 caching addresses this; see ROADMAP. |

---

## Known gaps

- **Secrets in git history.** The pre-Neon `backend/.env` is still recoverable from
  an old commit in this public repo. Rotate anything reused, and purge with
  `git filter-repo` when convenient.
- **Token storage.** The JWT lives in `localStorage`, which is readable by any XSS
  on the page. An httpOnly cookie is the hardening step.
- **No route guard.** An unauthenticated visitor to `/dashboard` sees an empty
  shell until the first 401 bounces them. Data is safe (enforced server-side);
  this is cosmetic.
