from flask import Flask, jsonify, request, g
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask_cors import CORS
import os
import sys

# On Windows the console defaults to cp1252, so any print() containing an emoji
# or other non-Latin-1 character raises UnicodeEncodeError — which, inside a
# request handler, turns a successful response into a 500. Force UTF-8 so
# logging can never crash a route.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
from dotenv import load_dotenv
import yfinance as yf
import json
import csv
from datetime import datetime, date, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
import bcrypt
import uuid
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm.attributes import flag_modified
import time
import requests
from bs4 import BeautifulSoup
from textblob import TextBlob
import jwt
import re
from functools import wraps
from threading import Lock
from flask_socketio import SocketIO, emit, join_room, leave_room
import click
import backtesting
import agent

app = Flask(__name__)
load_dotenv()

# Debug must default to OFF: Werkzeug's debugger allows arbitrary code execution,
# so it must never be enabled on a publicly reachable deployment. Opt in locally
# with FLASK_DEBUG=1.
DEBUG = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
app.config["DEBUG"] = DEBUG

# Allowed browser origins for CORS. Accepts a comma-separated list so local dev
# and the deployed frontend can be permitted at the same time.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in FRONTEND_URL.split(",") if o.strip()]

# JWT signing secret. Fail loudly rather than silently signing with a default,
# which would let anyone forge a token.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is not set. See backend/.env.example.")
JWT_EXP_HOURS = int(os.getenv("JWT_EXP_HOURS", "24"))
JWT_ALGORITHM = "HS256"

# Restrict CORS to only allow requests from the frontend.
# Authorization must be an allowed request header so the browser will send the bearer token.
CORS(
    app,
    resources={r"/*": {"origins": ALLOWED_ORIGINS}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

# ------------------------------------------------------- Configure PostgreSQL database URI -------------------------------------------------------------------
DATABASE_URL = os.getenv('DATABASE_URL', '')
# Several hosts (and Neon's copy button) hand out "postgres://", a scheme
# SQLAlchemy 2.x no longer recognises. Normalise it so deploys don't fail here.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Neon (and other serverless Postgres) drop idle connections when the compute
# scales to zero. pool_pre_ping tests a connection before use and transparently
# reconnects; pool_recycle avoids handing out connections older than 5 minutes.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError("DATABASE_URL is not set or loaded correctly.")

db = SQLAlchemy(app)

# Realtime transport. Same origin allowlist as the HTTP API so the socket is
# not a wider door than the REST surface.
socketio = SocketIO(app, cors_allowed_origins=ALLOWED_ORIGINS, async_mode="threading")

class User(db.Model):
    __tablename__ = "user_data"
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(120), unique=True, nullable=False)
    # NOT unique: two users may legitimately choose the same password, and the
    # stored value is a salted bcrypt hash anyway.
    password = db.Column(db.String(255), nullable=False)

class Holdings(db.Model):
    __tablename__ = "user_holdings"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=False, nullable=False)
    ticker = db.Column(db.String(120), unique=False, nullable=False)
    avg_price = db.Column(db.Numeric(precision=10, scale=2), unique=False, nullable=False)
    num_shares = db.Column(db.Integer, unique=False, nullable=False)
    value = db.Column(db.Numeric(precision=10, scale=2), unique=False, nullable=False)
    pinned = db.Column(db.Boolean, unique=False, nullable=False, default=False)

class MarketSnapshot(db.Model):
    """
    Timestamped record of data fetched from an external provider.

    Two jobs at once:
      1. Cache — avoid refetching (and re-rate-limiting) the same data.
      2. Evidence — a decision can cite the exact snapshot it was based on via
         AuditLog.snapshot_ref, so it stays reproducible even after the upstream
         data changes.

    Rows are never mutated; a refresh inserts a new row and the newest wins.
    """
    __tablename__ = "market_snapshot"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = db.Column(db.String(32), nullable=True, index=True)  # NULL for universe-wide
    kind = db.Column(db.String(32), nullable=False, index=True)   # recs|risk|financials|price|sentiment
    payload = db.Column(JSONB, nullable=False)
    fetched_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        server_default=db.func.now(), index=True
    )

class BacktestRun(db.Model):
    """
    Immutable record of one backtest.

    Same discipline as AuditLog: a run is evidence. It stores the parameters,
    the resulting metrics, the equity curve and the snapshots the prices came
    from, so a result can be reproduced and a later agent decision can cite the
    backtest that justified its policy.
    """
    __tablename__ = "backtest_run"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_email = db.Column(db.String(120), nullable=True, index=True)
    strategy = db.Column(db.String(64), nullable=False)
    params = db.Column(JSONB, nullable=True)
    universe = db.Column(JSONB, nullable=True)      # tickers included
    start_date = db.Column(db.String(10), nullable=True)
    end_date = db.Column(db.String(10), nullable=True)
    metrics = db.Column(JSONB, nullable=True)       # return, Sharpe, drawdown, ...
    equity_curve = db.Column(JSONB, nullable=True)  # [{date, equity, benchmark}]
    trades = db.Column(JSONB, nullable=True)
    snapshot_refs = db.Column(JSONB, nullable=True) # market_snapshot ids used
    # A human's own note on the run — why it was worth testing, what to make of
    # the result. The metrics are the machine's record; this is the analyst's.
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

class AgentProposal(db.Model):
    """
    A trade the agent proposed, and what a human decided about it.

    The agent has no write access to holdings: it can only create rows here.
    Execution happens after a human approves, and every transition is also
    mirrored into audit_log so the decision trail is immutable even though this
    row's status changes.
    """
    __tablename__ = "agent_proposal"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_email = db.Column(db.String(120), nullable=False, index=True)
    ticker = db.Column(db.String(32), nullable=False)
    action = db.Column(db.String(16), nullable=False)   # buy | sell | hold
    shares = db.Column(db.Integer, nullable=False, default=0)
    rationale = db.Column(db.Text, nullable=True)
    confidence = db.Column(db.String(16), nullable=True)
    evidence_used = db.Column(JSONB, nullable=True)
    risks = db.Column(db.Text, nullable=True)
    # Provenance: what the agent saw, and what validated the strategy.
    snapshot_refs = db.Column(JSONB, nullable=True)
    backtest_run_id = db.Column(UUID(as_uuid=True), nullable=True)
    # The investigation this proposal came out of, so a reviewer can see the
    # tool calls that led here rather than just the conclusion.
    agent_run_id = db.Column(UUID(as_uuid=True), nullable=True)
    model = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="pending")  # pending|approved|rejected|executed|failed
    decided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    decision_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

class AgentRun(db.Model):
    """
    One invocation of the agent, with the trail of how it got there.

    The agentic mode investigates before it concludes, so the interesting record
    is not just the proposals but the sequence of tool calls behind them: which
    strategies it backtested, what came back, what it did next. Storing that
    makes a run reviewable rather than a black box, and storing tokens and cost
    makes the price of a decision visible.
    """
    __tablename__ = "agent_run"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_email = db.Column(db.String(120), nullable=False, index=True)
    model = db.Column(db.String(64), nullable=True)
    mode = db.Column(db.String(16), nullable=False, default="agentic")  # agentic | single_shot
    status = db.Column(db.String(16), nullable=False, default="running")  # running|completed|failed
    steps = db.Column(db.Integer, nullable=False, default=0)
    trace = db.Column(JSONB, nullable=True)          # [{step, tool, args, result, ms}]
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    cost_usd = db.Column(db.Float, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

class AuditLog(db.Model):
    """
    Append-only ledger of every state-changing action.

    This is the audit substrate the project is built around: it answers
    "who did what, when, and on what evidence". Nothing in the codebase may
    UPDATE or DELETE rows in this table.
    """
    __tablename__ = "audit_log"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_email = db.Column(db.String(120), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False)      # login, pin, buy, sell, ...
    entity = db.Column(db.String(120), nullable=True)      # ticker or resource id
    payload = db.Column(JSONB, nullable=True)              # full detail of the action
    snapshot_ref = db.Column(UUID(as_uuid=True), nullable=True)  # -> market_snapshot (Phase 3)
    request_id = db.Column(db.String(64), nullable=True)   # correlates rows from one request
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )

# ----------------------------------------------- auth & audit helpers -------------------------------------------------------------------------------

@app.before_request
def assign_request_id():
    """Give every request an id so related audit rows can be correlated."""
    g.request_id = str(uuid.uuid4())

def create_access_token(email: str) -> str:
    """Issue a signed JWT carrying the user's identity."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iat": now,
        "exp": now + timedelta(hours=JWT_EXP_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def require_auth(view):
    """
    Gate a route behind a valid bearer token.

    The authenticated email is placed on `g.user_email`. Routes must read the
    identity from there and never from the request body/query string, otherwise
    any caller could act as any user.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or malformed Authorization header"}), 401

        token = auth_header.split(" ", 1)[1].strip()
        try:
            claims = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        email = (claims.get("sub") or "").lower()
        if not email:
            return jsonify({"error": "Token missing subject"}), 401

        g.user_email = email
        return view(*args, **kwargs)

    return wrapper

# ----------------------------------------------- snapshot cache helpers -------------------------------------------------------------------------------

# Default freshness per kind of data. Prices move constantly; financial
# statements and analyst consensus change slowly.
SNAPSHOT_TTL_SECONDS = {
    "recs": 24 * 3600,
    "financials": 24 * 3600,
    "risk": 6 * 3600,
    "price": 3600,
    "price_history": 24 * 3600,
    "quote": 900,
    "sentiment": 3600,
}

# Backtests need years, not the single year the chart route stores: a strategy
# that ranks on a 252-bar lookback produces nothing at all on 252 bars of data.
BACKTEST_HISTORY_START = "2015-01-01"
BACKTEST_HISTORY_TTL = 24 * 3600

def get_snapshot(kind, ticker=None, max_age_seconds=None):
    """
    Return the newest snapshot for (kind, ticker) if it is still fresh.

    Returns (payload, snapshot_id) on a hit, or (None, None) on a miss.
    """
    if max_age_seconds is None:
        max_age_seconds = SNAPSHOT_TTL_SECONDS.get(kind, 3600)

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    row = (
        MarketSnapshot.query
        .filter(
            MarketSnapshot.kind == kind,
            MarketSnapshot.ticker == ticker,
            MarketSnapshot.fetched_at >= cutoff,
        )
        .order_by(MarketSnapshot.fetched_at.desc())
        .first()
    )
    if row is None:
        return None, None
    return row.payload, str(row.id)

def json_safe(value):
    """
    Convert pandas/numpy values into plain JSON types.

    yfinance returns numpy scalars, Timestamps and NaN, none of which
    json.dumps (and therefore JSONB) accepts.
    """
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if (np.isnan(f) or np.isinf(f)) else f  # NaN/Inf are not valid JSON
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return str(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)  # last resort so a snapshot never fails to serialize

def put_snapshot(kind, payload, ticker=None):
    """Insert a new snapshot and return its id (committed by the caller)."""
    row = MarketSnapshot(kind=kind, ticker=ticker, payload=json_safe(payload))
    db.session.add(row)
    db.session.flush()  # populate row.id without ending the transaction
    return str(row.id)

def get_last_quote(ticker):
    """
    Latest close for a ticker, preferring stored data over a network call.

    Tried in order: a fresh quote snapshot, the tail of a fresh price snapshot,
    then yfinance. Returns None if every source fails, so a rate-limited
    provider degrades one number instead of breaking the whole portfolio view.
    """
    cached, _ = get_snapshot("quote", ticker=ticker)
    if isinstance(cached, dict) and cached.get("price") is not None:
        return cached["price"]

    # The chart endpoint may already have stored a year of closes.
    price_snap, _ = get_snapshot("price", ticker=ticker)
    if isinstance(price_snap, dict) and price_snap.get("series"):
        return price_snap["series"][-1].get("price")

    try:
        data = yf.Ticker(ticker).history(period="1d")
        if data.empty:
            return None
        price = float(data["Close"].iloc[-1])
        put_snapshot("quote", {"price": price}, ticker=ticker)
        return price
    except Exception as e:
        print(f"Quote lookup failed for {ticker}: {e}")
        return None

def get_quote_pair(ticker):
    """
    (last_close, previous_close) for a ticker, preferring stored data.

    The previous close is what makes a day change computable. Either element
    may be None when the data is unavailable.
    """
    # A price snapshot holds a year of closes; its tail gives both values.
    price_snap, _ = get_snapshot("price", ticker=ticker)
    if isinstance(price_snap, dict) and price_snap.get("series"):
        series = price_snap["series"]
        last = series[-1].get("price")
        prev = series[-2].get("price") if len(series) > 1 else None
        return last, prev

    cached, _ = get_snapshot("quote", ticker=ticker)
    if isinstance(cached, dict) and cached.get("price") is not None:
        return cached["price"], cached.get("prev_price")

    try:
        data = yf.Ticker(ticker).history(period="5d")
        if data.empty:
            return None, None
        closes = [float(c) for c in data["Close"].tolist()]
        last = closes[-1]
        prev = closes[-2] if len(closes) > 1 else None
        put_snapshot("quote", {"price": last, "prev_price": prev}, ticker=ticker)
        return last, prev
    except Exception as e:
        print(f"Quote pair lookup failed for {ticker}: {e}")
        return None, None

def write_audit(action, entity=None, payload=None, actor_email=None, snapshot_ref=None):
    """
    Append one row to the audit ledger.

    Committed by the caller alongside the change it describes, so the ledger
    entry and the state change succeed or fail together.
    """
    entry = AuditLog(
        actor_email=actor_email or getattr(g, "user_email", None),
        action=action,
        entity=entity,
        payload=payload,
        snapshot_ref=snapshot_ref,
        request_id=getattr(g, "request_id", None),
    )
    db.session.add(entry)
    return entry

# ----------------------------------------------- helper functions -------------------------------------------------------------------------------

def calculate_moving_averages(df):
    """Calculates 20-day and 50-day moving averages"""
    df["MA_20"] = df["Close"].rolling(window=20).mean()
    df["MA_50"] = df["Close"].rolling(window=50).mean()
    return df

def generate_trading_signals(df):
    """
    Generates buy/sell signals based on MA20/MA50 crossovers.

    Only rows where both averages exist are considered. Without that filter the
    first 49 days compare MA_20 against NaN, which evaluates False and labels
    them "Sell", producing a fake crossover the moment MA_50 becomes valid.
    The first valid row is also excluded: it has no prior state to cross from.
    """
    both_valid = df["MA_20"].notna() & df["MA_50"].notna()
    valid = df[both_valid].copy()
    if valid.empty:
        return valid.assign(Signal=[], Crossover=[])

    valid["Signal"] = np.where(valid["MA_20"] > valid["MA_50"], "Buy", "Sell")
    # A crossover is a change from the previous valid row; the first row's
    # shift() is NaN, so drop it explicitly rather than reporting a crossover.
    valid["Crossover"] = valid["Signal"].ne(valid["Signal"].shift())
    valid.iloc[0, valid.columns.get_loc("Crossover")] = False

    return valid[valid["Crossover"]]


# ----------------------------------------------- auth routes -------------------------------------------------------------------------------------------------------------------------------------------------
#{'email': 'Rishabk2004@gmail.com', 'password': 'password', 'phone': '2017058617'}
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    print(data)
    
    # Validate required fields else early return 
    if not data.get('email') or not data.get('phone') or not data.get('password'):
        return jsonify({"error": "Missing required fields"}), 400

    password = data['password'].encode('utf-8')  
    hashed_password = bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')  # Convert bytes to string

    email = data['email'].lower()
    user1 = User(email=email, phone=data['phone'], password=hashed_password)

    try:
        db.session.add(user1)
        write_audit("register", entity=email, payload={"email": email}, actor_email=email)
        db.session.commit()
        return jsonify({"message": "Successfully registered the user"}), 200
    except Exception as e:
        db.session.rollback()  # Rollback in case of error
        return jsonify({"error": str(e)}), 500

@app.route("/login", methods=["POST"])
def login():
    data = request.json

    try: 
        # Validate required fields
        if not data.get('email') or not data.get('password'):
            return jsonify({"error": "Missing required fields"}), 400
        
        email = data['email'].lower()
        password = data['password'].encode('utf-8')

        # Fetch the user by email
        user = User.query.filter_by(email=email).first()  

        # Check if user exists
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Validate password using bcrypt.checkpw()
        if bcrypt.checkpw(password, user.password.encode('utf-8')):
            token = create_access_token(email)
            write_audit("login", entity=email, actor_email=email)
            db.session.commit()
            return jsonify({
                "message": "Successful login",
                "token": token,
                "email": email,
                "expires_in": JWT_EXP_HOURS * 3600,
            }), 200
        else:
            # Failed attempts are part of the audit trail too.
            write_audit("login_failed", entity=email, actor_email=email)
            db.session.commit()
            return jsonify({"error": "Invalid email or password"}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------ trading routes -------------------------------------------------------------------------------

# gets a specific stock's data
@app.route('/fetch-stock-data', methods=['POST'])
@require_auth
def fetch_specific_stock_data():
    request_data = request.get_json(silent=True) or {}
    print("Received request:", request_data)

    if "ticker" not in request_data:
        return jsonify({"error": "Missing 'ticker' in request"}), 400

    ticker_symbol = (request_data["ticker"] or "").upper()
    if not ticker_symbol:
        return jsonify({"error": "Missing 'ticker' in request"}), 400

    # Financial statements change quarterly; serve a fresh snapshot when present.
    cached, _ = get_snapshot("financials", ticker=ticker_symbol)
    if cached is not None:
        return jsonify(cached), 200

    stock = yf.Ticker(ticker_symbol)

    # Fetch financials
    financials = stock.financials
    if financials is None or financials.empty:
        print("No financials found for", request_data["ticker"])
        return jsonify({"error": f"No financial data available for {request_data['ticker']}"}), 404

    # Convert DataFrame index to string
    financials.index = financials.index.astype(str)

    # Convert DataFrame to dictionary and replace NaN values
    financials_dict = financials.replace({np.nan: None}).to_dict()
    financials_dict = {str(date): data for date, data in financials_dict.items()}  # Ensure keys are strings

    stock_info = stock.info
    additional_data = {
        "Market Cap": stock_info.get("marketCap"),
        "PE Ratio": stock_info.get("trailingPE"),  # P/E Ratio
        "Dividends Paid": stock.dividends.sum() if not stock.dividends.empty else None,
        "Operating Cash Flow": stock_info.get("operatingCashflow"),
        "latest_price": stock.history(period="1d")["Close"].iloc[-1]
    }


    # store this data in csv for better retrieval
    storeDataInCSV(financials_dict, additional_data, ticker_symbol)

    result = {
        "financials": financials_dict,
        "additional_data": additional_data
    }
    put_snapshot("financials", result, ticker=ticker_symbol)
    db.session.commit()

    return jsonify(result), 200

def score_recommendations(stock_consideration):
    """
    Turn a yfinance recommendations frame into {"rating", "indicator"}.

    Returns None when the data is unusable, so callers can skip the ticker.
    """
    if stock_consideration is None or stock_consideration.empty:
        return None

    required_columns = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
    if any(col not in stock_consideration.columns for col in required_columns):
        return None

    # Row 0 is the current period ("0m"); later rows are prior months.
    latest = stock_consideration.iloc[0]
    counts = {col: float(latest.get(col) or 0) for col in required_columns}
    total = sum(counts.values())

    # No analyst coverage at all: a zero total would otherwise produce NaN
    # proportions and corrupt the ranking below.
    if total <= 0:
        return None

    scores = {
        'buy': (counts['strongBuy'] + counts['buy']) / total,
        'hold': counts['hold'] / total,
        'sell': (counts['strongSell'] + counts['sell']) / total,
    }
    decision = max(scores, key=scores.get)
    return {"rating": decision, "indicator": scores[decision], "analyst_count": int(total)}

# use this route to fetch the top stock recommendations
@app.route('/fetch-recs', methods=['POST'])
@require_auth
def fetchRecommendations():
    email_in = g.user_email  # identity comes from the verified token, not the body
    request_data = request.get_json(silent=True) or {}
    force_refresh = bool(request_data.get("refresh"))

    pinnedStocks = fetchPinnedStocks(email_in)
    num_of_pins = len(pinnedStocks)
    top_n = 30 + num_of_pins

    # ---- 1. Try the cached universe-wide snapshot -------------------------------
    # Scoring the whole universe takes >60s of throttled yfinance calls, so the
    # result is snapshotted and reused. The snapshot is user-independent; each
    # user's pins are merged in afterwards.
    scored = None
    snapshot_id = None
    if not force_refresh:
        scored, snapshot_id = get_snapshot("recs")

    # ---- 2. On a miss, fetch and score -----------------------------------------
    if scored is None:
        scored = {}
        rate_limited = False
        universe = sorted(set(sp500_tickers) | set(pinnedStocks))

        for stock in universe:
            try:
                # Throttle to stay under yfinance's rate limits.
                time.sleep(0.5)
                result = score_recommendations(yf.Ticker(stock).get_recommendations())
            except Exception as exc:
                # A single bad ticker must not fail the whole request. Rate
                # limiting affects everything that follows, so stop early.
                if "Rate limit" in str(exc) or "Too Many Requests" in str(exc):
                    print(f"Rate limited while fetching {stock}; stopping early.")
                    rate_limited = True
                    break
                print(f"Skipping {stock}: {exc}")
                continue

            if result is not None:
                scored[stock] = result

        if not scored:
            # Nothing usable. Fall back to a stale snapshot rather than showing
            # the user an empty dashboard.
            stale, stale_id = get_snapshot("recs", max_age_seconds=30 * 24 * 3600)
            if stale:
                scored, snapshot_id = stale, stale_id
            else:
                status = 429 if rate_limited else 503
                return jsonify({
                    "error": "Could not retrieve stock recommendations at this moment",
                    "reason": "rate_limited" if rate_limited else "no_data",
                }), status
        else:
            snapshot_id = put_snapshot("recs", scored)
            write_audit(
                "recs_snapshot",
                entity=f"{len(scored)} tickers",
                payload={"ticker_count": len(scored), "partial": rate_limited},
                snapshot_ref=snapshot_id,
            )
            db.session.commit()

    # ---- 3. Rank and return the top N ------------------------------------------
    # NOTE: rank over a copy. The previous implementation popped from the source
    # dict and then tested that (now-drained) dict for emptiness, which returned
    # a 400 error even when recommendations had been found successfully.
    ranked = sorted(scored.items(), key=lambda kv: kv[1]["indicator"], reverse=True)

    # Returned as a list, not a dict: jsonify sorts object keys alphabetically,
    # which would silently discard the ranking computed above.
    top = [
        {"ticker": ticker, **data}
        for ticker, data in ranked[:top_n]
    ]

    return jsonify({
        "recommendations": top,
        "snapshot_ref": snapshot_id,
        "cached": not force_refresh and bool(snapshot_id),
    }), 200

#use this function to retrieve the users' pinned stocks
def fetchPinnedStocks(email: str) -> list: # return a list of tickers
    #retrieve all the user's holdings
    if not email:
        return [] #return empty list if no email 
    holdings = Holdings.query.filter_by(email=email).all()
    if not holdings:
        return [] #return empty list if holdings is empty
    
    # filter for the holdings that that are pinned, ideally redundant. should by default return all user holdings
    # as even if a stock is not held by the user, it can still be pinned
    pinned_stocks_to_recommend = [h.ticker for h in holdings if h.pinned == True]
    return pinned_stocks_to_recommend    
    

# --------------------------------------------------------- RISK ANALYSIS STOCK -------------------------------------------------------------------------------------------

# route to get the risk analysis for a stock
@app.route('/fetch-risk-anal', methods=['POST'])
@require_auth
def getRiskAnalysis():
    request_data = request.get_json(silent=True) or {}
    print("Received request in risk anal:", request_data) # AMZN
    risk_analysis_to_send = {}
    
    if not isinstance(request_data, dict) or 'stock' not in request_data:
        return jsonify({"error": "Invalid request format. Expected {'stock': 'TICKER'}"}), 400
    
    stock = (request_data['stock'] or "").upper()
    if not stock:
        return jsonify({"error": "Invalid request format. Expected {'stock': 'TICKER'}"}), 400

    # Serve a fresh snapshot if we have one; volatility over 5+ years of closes
    # barely moves intraday, so this is a cheap win.
    cached, _ = get_snapshot("risk", ticker=stock)
    if cached is not None:
        return jsonify(cached), 200

    try:
        ticker = yf.Ticker(stock)
        #fetch the data from 2020-01-01 to present day
        today = date.today()
        data = yf.download(stock, start="2020-01-01", end=today) #get the data from 2020 start to present
    except Exception as e:
        stale, _ = get_snapshot("risk", ticker=stock, max_age_seconds=30 * 24 * 3600)
        if stale is not None:
            return jsonify(stale), 200
        status = 429 if ("Rate limit" in str(e) or "Too Many Requests" in str(e)) else 500
        return jsonify({"error": str(e)}), status

    if data.empty:
        return jsonify({"error": "Invalid stock ticker or no data available for the given period"}), 400

    if 'Close' in data.columns:
        closes = data['Close']
        # yfinance may return MultiIndex columns for a single ticker, which would
        # make the result a Series rather than a scalar. Squeeze to one column.
        if hasattr(closes, "columns"):
            closes = closes.iloc[:, 0]

        returns = closes.pct_change() #"By what percentage did the stock price change compared to the previous day?"

        # calculate voltaility by averaging the daily percent change in closing price
        volatility = float(returns.std() * (252**0.5))  # Annualized volatility
        risk_analysis_to_send['volatility'] = volatility

        # get important ratios
        try:
            info = ticker.info
            risk_analysis_to_send['debtToEquity'] = info.get('debtToEquity', "")  # 61.175 - AMZN
            risk_analysis_to_send['currentRatio'] = info.get('currentRatio', "")  # 1.089 - AMZN
            risk_analysis_to_send['quickRatio'] = info.get('quickRatio', "")      # 0.827 - AMZN
            risk_analysis_to_send['latest_price'] = float(closes.iloc[-1])
        except Exception as e:
            # Volatility is the important number; ship it even if the ratio
            # lookup gets rate limited.
            print(f"Ratio lookup failed for {stock}: {e}")
            risk_analysis_to_send.setdefault('latest_price', float(closes.iloc[-1]))

        put_snapshot("risk", risk_analysis_to_send, ticker=stock)
        db.session.commit()

    # print(risk_analysis_to_send)
    return jsonify(risk_analysis_to_send), 200

# -------------------------------------------------------- Holdings route ------------------------------------------------------------------------------------------------------------

#use this route to update the user's holdings
@app.route('/update-holdings', methods=['POST'])
@require_auth
def updateHoldings():
    """
    This route updates the authenticated user's holdings:
      - Buying new shares (shares > 0)
      - Selling existing shares (shares < 0)
      - Creating a completely new holding (with nonzero shares)
      {
        "holdingsUpdate": {
            "ticker": "ICE",
            "price": "85.5",
            "num_shares": 10
        }
        }
    """
    request_data = request.get_json(silent=True) or {}

    email_in = g.user_email  # from the token; callers cannot act as another user
    holdings_data = request_data.get("holdingsUpdate", {}) or {}

    ticker_in = (holdings_data.get("ticker") or "").upper()
    try:
        price = float(holdings_data.get("price", 0))
        shares = int(holdings_data.get("num_shares", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "price must be a number and num_shares an integer"}), 400

    print(f'shares: {shares}, price: {price}, ticker_in: {ticker_in}, email_in: {email_in}')

    # Basic validation
    if not ticker_in:
        return jsonify({"error": "ticker is required"}), 400
    if shares == 0:
        return jsonify({"error": "num_shares must be non-zero"}), 400
    if price < 0:
        return jsonify({"error": "price cannot be negative"}), 400

    try:
        # Trade math lives in apply_holding_change so the manual route and the
        # agent's execution path can never disagree about a cost basis.
        result = apply_holding_change(email_in, ticker_in, shares, price)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        print(f"Database Error: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    try:
        write_audit(result["action"], entity=ticker_in, payload=result)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Database Error: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    messages = {
        "sell": "Shares sold successfully",
        "buy": "Holding updated successfully",
        "buy_new": "New holding added successfully",
    }
    return jsonify({
        "message": messages.get(result["action"], "Holding updated"),
        "data": {"ticker": result["ticker"], **result},
    }), 200

    
#pin-holdings
@app.route('/pin-stock', methods=['POST'])
@require_auth
def pinStock():
    request_data = request.get_json(silent=True) or {}
    email = g.user_email
    ticker = (request_data.get('query') or "").upper()  # ticker from body, identity from token

    # Early return to handle incomplete request
    if not ticker:
        return jsonify({"message": "ticker is required"}), 400

    # check if an holding already exists
    existing_holding = Holdings.query.filter_by(email=email, ticker=ticker).first()
    if existing_holding:
        return jsonify({"message": "holding exists already, cant pin it again"}), 401

    new_pinned_holding = Holdings(email=email, ticker=ticker, avg_price=0.0, num_shares=0, value=0.0, pinned=True)
    db.session.add(new_pinned_holding)
    write_audit("pin", entity=ticker)
    db.session.commit()
    return jsonify({
                "message": "New pinned stock added successfully",
                "data": ticker  # or [ticker_in], if your front end expects an array
            }), 200
    
# use this route to get the pinned stocks
@app.route('/fetch-pins', methods=['GET'])
@require_auth
def fetchUserPins():
    holdings = Holdings.query.filter_by(email=g.user_email).all()

    pinned_list = [h.ticker for h in holdings if h.pinned == True]
    # print(pinned_list) # ['ASTS', 'ABT', 'BDX', 'AVGO', 'NVDA', 'AMZN', 'TSLA']
    return jsonify(pinned_list), 200
#return this array {stock :stock.ticker, pinned: stock.pinned}
    
# gets the user's current stock holdings
@app.route('/get-holdings', methods=['GET'])
@require_auth
def get_holdings():
    email = g.user_email
    # print('get holdings for: ',email)

    holdings = Holdings.query.filter_by(email=email).all()
    
    # Convert holdings to JSON (example: modify based on your DB schema)
    holdings_list = [
    {
        "ticker": h.ticker,
        "num_shares": h.num_shares,
        "avg_price": float(h.avg_price),
        "value": float(h.value),
        "pinned": bool(h.pinned),
    } for h in holdings if h.num_shares != 0] # check for whether a stock is pinned or simply a holding 

    # Attach the latest quote and return for each holding.
    # Every holding gets last_quote and total_return keys, even when the data is
    # unavailable: previously the loop skipped some rows entirely and the
    # frontend then called .toFixed() on an undefined total_return.
    for hold in holdings_list:
        hold["last_quote"] = None
        hold["total_return"] = None

        last_quote = get_last_quote(hold["ticker"])
        if last_quote is None:
            continue

        hold["last_quote"] = float(last_quote)
        # avg_price is 0 for a pinned-but-unowned ticker; guard the division.
        if hold["avg_price"]:
            price_diff = last_quote - hold["avg_price"]
            hold["total_return"] = (price_diff / hold["avg_price"]) * 100

    db.session.commit()  # persist any quote snapshots created above
    # print('holdings list: ', holdings_list)
    return jsonify({"holdings": holdings_list}), 200

# ---------------------------------------------- AI agent (propose / approve / execute) ------------------------------------------------------------

def apply_holding_change(email, ticker, shares, price):
    """
    Apply a buy (shares > 0) or sell (shares < 0) to a user's position.

    Single implementation of the cost-basis math, shared by the manual trade
    route and the agent's execution path — two copies would eventually disagree
    about a user's average price. Mutates the session; the caller commits.
    Raises ValueError on anything the caller should surface as a 400.
    """
    ticker = (ticker or "").upper()
    if not ticker:
        raise ValueError("ticker is required")
    if not shares:
        raise ValueError("num_shares must be non-zero")
    if price is None:
        raise ValueError(f"No price available for {ticker}")
    price = float(price)
    if price < 0:
        raise ValueError("price cannot be negative")

    existing = Holdings.query.filter_by(email=email, ticker=ticker).first()

    # ---- sell ----
    if shares < 0:
        if not existing:
            raise ValueError("Cannot sell a stock you do not own")
        sold = abs(int(shares))
        if existing.num_shares < sold:
            raise ValueError("Not enough shares to sell")

        existing.num_shares -= sold
        remaining = existing.num_shares
        if remaining == 0:
            db.session.delete(existing)
        else:
            existing.value = float(remaining * existing.avg_price)
            flag_modified(existing, "num_shares")
            flag_modified(existing, "value")

        return {"action": "sell", "ticker": ticker, "shares_sold": sold,
                "price": price, "shares_remaining": remaining}

    # ---- buy ----
    shares = int(shares)
    if not existing:
        db.session.add(Holdings(
            email=email, ticker=ticker, avg_price=price,
            num_shares=shares, value=price * shares, pinned=True,
        ))
        return {"action": "buy_new", "ticker": ticker, "shares_bought": shares,
                "price": price, "avg_price": price}

    original = existing.num_shares
    existing.num_shares += shares
    # Weighted average cost basis across the old and new lots.
    existing.avg_price = (
        (float(existing.avg_price) * original) + (shares * price)
    ) / existing.num_shares
    existing.value = float(existing.num_shares * existing.avg_price)
    flag_modified(existing, "num_shares")
    flag_modified(existing, "avg_price")
    flag_modified(existing, "value")

    return {"action": "buy", "ticker": ticker, "shares_bought": shares,
            "price": price, "shares_held": existing.num_shares,
            "avg_price": float(existing.avg_price)}

def gather_agent_evidence(email):
    """
    Collect what the agent is allowed to reason over, all from stored data.

    Deliberately reads snapshots rather than calling providers live: the agent's
    inputs must be the same ones recorded against its proposal, or the decision
    is not reproducible.
    """
    snapshot_refs = []

    holdings = Holdings.query.filter_by(email=email).all()
    portfolio = []
    tickers = []
    for h in holdings:
        if not h.num_shares:
            continue
        last, _ = get_quote_pair(h.ticker)
        portfolio.append({
            "ticker": h.ticker,
            "shares": int(h.num_shares),
            "avg_price": float(h.avg_price),
            "last_quote": last,
        })
        tickers.append(h.ticker)

    signals = {}
    sentiment = {}
    for ticker in tickers:
        price_snap, price_id = get_snapshot("price", ticker=ticker, max_age_seconds=7 * 24 * 3600)
        if isinstance(price_snap, dict):
            signals[ticker] = price_snap.get("signals", [])[-3:]  # most recent crossovers
            if price_id:
                snapshot_refs.append(price_id)

        sent_snap, sent_id = get_snapshot("sentiment", ticker=ticker, max_age_seconds=7 * 24 * 3600)
        if isinstance(sent_snap, dict):
            sentiment[ticker] = sent_snap.get("overall_sentiment")
            if sent_id:
                snapshot_refs.append(sent_id)

    runs = (BacktestRun.query
            .filter_by(actor_email=email)
            .order_by(BacktestRun.created_at.desc())
            .limit(5).all())
    backtests = [
        {
            "id": str(r.id),
            "strategy": r.strategy,
            # Strategies are parameterised, so the name alone is ambiguous:
            # a 20/50 crossover and a 5/200 one are very different rules.
            "params": r.params,
            "universe": r.universe,
            "window": f"{r.start_date} to {r.end_date}",
            "metrics": {
                k: r.metrics.get(k) for k in
                ("total_return_pct", "sharpe", "max_drawdown_pct", "beat_benchmark")
            } if r.metrics else None,
        } for r in runs
    ]

    return {
        "portfolio": portfolio,
        "signals": signals,
        "sentiment": sentiment,
        "backtests": backtests,
        "snapshot_refs": list(dict.fromkeys(snapshot_refs)),
        "latest_backtest_id": str(runs[0].id) if runs else None,
    }

def build_agent_tools(email):
    """
    The agent's tool belt, bound to one user.

    Every tool is read-only with one exception: run_backtest creates a stored
    BacktestRun, which is additive evidence rather than a change to the
    portfolio. There is deliberately no tool that can move a position — the
    agent's only route to a trade is a proposal a human approves.

    Returns (execute, state) where `state` accumulates what the run touched so
    the resulting proposals can cite it.
    """
    state = {"backtest_ids": {}, "snapshot_refs": [], "last_backtest_id": None}

    def _remember_snapshot(snapshot_id):
        if snapshot_id and snapshot_id not in state["snapshot_refs"]:
            state["snapshot_refs"].append(snapshot_id)

    def tool_list_strategies(_args):
        return {"strategies": [
            {
                "id": key,
                "label": spec["label"],
                "family": spec["family"],
                "multi_asset": spec["multi_asset"],
                "summary": spec["summary"],
                "params": {
                    name: {k: v for k, v in meta.items() if k in ("type", "default", "min", "max", "options")}
                    for name, meta in spec["params"].items()
                },
            }
            for key, spec in sorted(backtesting.STRATEGY_SPECS.items(),
                                    key=lambda kv: kv[1]["complexity"])
        ]}

    def tool_run_backtest(args):
        # The full result carries a multi-thousand-point equity curve; the agent
        # only needs the verdict, so send a digest and keep the id for citation.
        result = execute_backtest(
            email,
            strategy=args.get("strategy"),
            params=args.get("params"),
            ticker=args.get("ticker"),
            universe=args.get("universe"),
        )
        keep = ("total_return_pct", "cagr_pct", "sharpe", "sortino",
                "max_drawdown_pct", "trade_count", "win_rate_pct",
                "excess_return_pct", "beat_benchmark")
        run_id = result["backtest_run_id"]
        for t in result["universe"]:
            state["backtest_ids"][t] = run_id
        state["last_backtest_id"] = run_id
        for ref in result.get("snapshot_refs") or []:
            _remember_snapshot(ref)
        return {
            "backtest_run_id": run_id,
            "strategy": result["strategy"],
            "params": result["params"],
            "universe": result["universe"],
            "window": f"{result['start_date']} to {result['end_date']}",
            "bars": result["bars"],
            "metrics": {k: result["metrics"].get(k) for k in keep},
            "benchmark": {k: result["benchmark_metrics"].get(k) for k in keep[:6]},
            "note": "Benchmark is buy-and-hold (single ticker) or equal-weight (universe).",
        }

    def tool_get_holdings(_args):
        rows = Holdings.query.filter_by(email=email).all()
        out = []
        for h in rows:
            if not h.num_shares:
                continue
            last, prev = get_quote_pair(h.ticker)
            out.append({
                "ticker": h.ticker,
                "shares": int(h.num_shares),
                "avg_price": float(h.avg_price),
                "last_quote": last,
                "prev_close": prev,
            })
        return {"holdings": out}

    def tool_get_quote(args):
        ticker = (args.get("ticker") or "").upper().strip()
        if not ticker:
            return {"error": "ticker is required"}
        last, prev = get_quote_pair(ticker)
        if last is None:
            return {"ticker": ticker, "error": "No quote available"}
        return {
            "ticker": ticker, "price": last, "prev_close": prev,
            "change_pct": ((last - prev) / prev * 100) if prev else None,
        }

    def tool_get_signals(args):
        ticker = (args.get("ticker") or "").upper().strip()
        snap, snap_id = get_snapshot("price", ticker=ticker, max_age_seconds=7 * 24 * 3600)
        if not isinstance(snap, dict):
            return {"ticker": ticker, "signals": [], "note": "No stored price data for this ticker."}
        _remember_snapshot(snap_id)
        return {"ticker": ticker, "signals": (snap.get("signals") or [])[-5:],
                "snapshot_ref": snap_id}

    def tool_get_sentiment(args):
        ticker = (args.get("ticker") or "").upper().strip()
        snap, snap_id = get_snapshot("sentiment", ticker=ticker, max_age_seconds=7 * 24 * 3600)
        if not isinstance(snap, dict):
            return {"ticker": ticker, "note": "No stored sentiment for this ticker."}
        _remember_snapshot(snap_id)
        return {
            "ticker": ticker,
            "overall_sentiment": snap.get("overall_sentiment"),
            "headlines": [n.get("headline") for n in (snap.get("news") or [])[:8]],
            "snapshot_ref": snap_id,
        }

    registry = {
        "list_strategies": tool_list_strategies,
        "run_backtest": tool_run_backtest,
        "get_holdings": tool_get_holdings,
        "get_quote": tool_get_quote,
        "get_signals": tool_get_signals,
        "get_sentiment": tool_get_sentiment,
    }

    def execute(name, args):
        fn = registry.get(name)
        if not fn:
            return {"error": f"Unknown tool '{name}'"}
        try:
            return fn(args or {})
        except BacktestError as e:
            # A rejected backtest is useful information for the agent: it can
            # correct the parameters and try again rather than the run failing.
            return {"error": str(e), **e.extra}

    return execute, state

@app.route('/agent/propose', methods=['POST'])
@require_auth
def agent_propose():
    """
    Run the agent and record its proposals as pending.

    In agentic mode the agent investigates with tools first — commissioning its
    own backtests and reading signals — and the whole investigation is stored as
    an AgentRun so the conclusion can be reviewed step by step. Nothing is
    executed here; proposals are created pending regardless of mode.
    """
    email = g.user_email
    body = request.get_json(silent=True) or {}
    mode = (body.get("mode") or "agentic").lower()
    if mode not in ("agentic", "single_shot"):
        return jsonify({"error": "mode must be 'agentic' or 'single_shot'"}), 400
    model = body.get("model") or None

    evidence = gather_agent_evidence(email)
    if not evidence["portfolio"]:
        return jsonify({
            "error": "No holdings to analyse. Buy or pin a position first.",
        }), 400

    # The two modes get deliberately different starting context: single-shot is
    # handed everything because it cannot go and look, while the agentic loop
    # gets positions only and has to retrieve the rest. Pre-loading evidence for
    # a tool-using agent would leave it nothing to investigate.
    if mode == "agentic":
        evidence_json = agent.build_starting_context(evidence["portfolio"])
    else:
        evidence_json = agent.build_evidence(
            evidence["portfolio"], evidence["signals"],
            evidence["sentiment"], evidence["backtests"],
        )

    run = AgentRun(actor_email=email, mode=mode,
                   model=model or (agent.DEFAULT_MODEL if mode == "agentic"
                                   else agent.SINGLE_SHOT_MODEL))
    db.session.add(run)
    db.session.commit()  # the run exists even if the model call fails

    execute_tool, tool_state = build_agent_tools(email)
    try:
        if mode == "agentic":
            result = agent.run_agentic(evidence_json, execute_tool, model=model)
        else:
            result = agent.propose(evidence_json, model=model)
    except agent.AgentUnavailable as e:
        run.status = "failed"
        run.error = str(e)
        run.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"error": str(e), "reason": "agent_unavailable",
                        "agent_run_id": str(run.id)}), 503

    usage = result.get("usage") or {}
    run.model = result.get("model") or run.model
    run.status = "completed"
    run.steps = result.get("steps") or 0
    run.trace = json_safe(result.get("trace") or [])
    run.input_tokens = usage.get("input", 0) + usage.get("cache_read", 0) + usage.get("cache_write", 0)
    run.output_tokens = usage.get("output", 0)
    run.cost_usd = result.get("cost_usd")
    run.summary = result.get("summary")
    run.completed_at = datetime.now(timezone.utc)

    # Every tool call is its own ledger entry: the investigation is auditable at
    # the same granularity as the decision it produced.
    for step in result.get("trace") or []:
        write_audit(
            "agent_tool_call",
            entity=step.get("tool"),
            payload=json_safe({"agent_run_id": str(run.id), **step}),
            actor_email=email,
        )

    # Snapshots the agent actually touched, on top of the starting evidence.
    snapshot_refs = list(dict.fromkeys(
        (evidence["snapshot_refs"] or []) + (tool_state["snapshot_refs"] or [])
    ))

    created = []
    for p in result["proposals"]:
        ticker = (p.get("ticker") or "").upper()
        # Prefer a backtest the agent ran on this very ticker; fall back to the
        # last one it ran, then to the user's most recent.
        backtest_id = (tool_state["backtest_ids"].get(ticker)
                       or tool_state["last_backtest_id"]
                       or evidence["latest_backtest_id"])
        row = AgentProposal(
            actor_email=email,
            ticker=ticker,
            action=p.get("action", "hold"),
            shares=int(p.get("shares") or 0),
            rationale=p.get("rationale"),
            confidence=p.get("confidence"),
            evidence_used=p.get("evidence_used"),
            risks=p.get("risks"),
            snapshot_refs=snapshot_refs,
            backtest_run_id=backtest_id,
            agent_run_id=run.id,
            model=result.get("model"),
        )
        db.session.add(row)
        db.session.flush()

        write_audit(
            "agent_propose",
            entity=row.ticker,
            payload={
                "proposal_id": str(row.id),
                "agent_run_id": str(run.id),
                "action": row.action,
                "shares": row.shares,
                "confidence": row.confidence,
                "rationale": row.rationale,
                "evidence_used": row.evidence_used,
                "risks": row.risks,
                "model": row.model,
                "backtest_run_id": str(backtest_id) if backtest_id else None,
            },
            snapshot_ref=snapshot_refs[0] if snapshot_refs else None,
        )
        created.append(row)

    db.session.commit()

    return jsonify({
        "summary": result["summary"],
        "model": result.get("model"),
        "mode": mode,
        "usage": usage,
        "cost_usd": result.get("cost_usd"),
        "steps": result.get("steps"),
        "trace": result.get("trace"),
        "stop_reason": result.get("stop_reason"),
        "agent_run_id": str(run.id),
        "evidence_snapshot_refs": snapshot_refs,
        "proposals": [serialize_proposal(r) for r in created],
    }), 200

@app.route('/agent/runs', methods=['GET'])
@require_auth
def list_agent_runs():
    """Past agent runs for this user, newest first, with their traces."""
    runs = (AgentRun.query
            .filter_by(actor_email=g.user_email)
            .order_by(AgentRun.created_at.desc())
            .limit(25).all())
    return jsonify({"runs": [serialize_agent_run(r) for r in runs]}), 200

def serialize_agent_run(row):
    return {
        "id": str(row.id),
        "mode": row.mode,
        "model": row.model,
        "status": row.status,
        "steps": row.steps,
        "trace": row.trace,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cost_usd": row.cost_usd,
        "summary": row.summary,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

def serialize_proposal(row):
    return {
        "id": str(row.id),
        "ticker": row.ticker,
        "action": row.action,
        "shares": row.shares,
        "rationale": row.rationale,
        "confidence": row.confidence,
        "evidence_used": row.evidence_used,
        "risks": row.risks,
        "snapshot_refs": row.snapshot_refs,
        "backtest_run_id": str(row.backtest_run_id) if row.backtest_run_id else None,
        "agent_run_id": str(row.agent_run_id) if row.agent_run_id else None,
        "model": row.model,
        "status": row.status,
        "decision_note": row.decision_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }

@app.route('/audit-log', methods=['GET'])
@require_auth
def get_audit_log():
    """
    The authenticated user's own ledger entries, newest first.

    Read-only by construction — there is no endpoint that mutates audit_log.
    Optional ?action= filters to one action type.
    """
    q = AuditLog.query.filter_by(actor_email=g.user_email)

    action = request.args.get("action")
    if action:
        q = q.filter(AuditLog.action == action)

    try:
        limit = min(int(request.args.get("limit", 100)), 500)
    except (TypeError, ValueError):
        limit = 100

    rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return jsonify({"entries": [
        {
            "id": str(r.id),
            "action": r.action,
            "entity": r.entity,
            "payload": r.payload,
            "snapshot_ref": str(r.snapshot_ref) if r.snapshot_ref else None,
            "request_id": r.request_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows
    ]}), 200

@app.route('/agent/proposals', methods=['GET'])
@require_auth
def agent_list_proposals():
    rows = (AgentProposal.query
            .filter_by(actor_email=g.user_email)
            .order_by(AgentProposal.created_at.desc())
            .limit(50).all())
    return jsonify({"proposals": [serialize_proposal(r) for r in rows]}), 200

@app.route('/agent/decide', methods=['POST'])
@require_auth
def agent_decide():
    """
    Approve or reject a pending proposal.

    Approval is what authorises execution — the agent cannot reach this path,
    and a proposal that is not pending cannot be decided twice.
    """
    body = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id")
    decision = (body.get("decision") or "").lower()
    note = body.get("note")

    if decision not in ("approve", "reject"):
        return jsonify({"error": "decision must be 'approve' or 'reject'"}), 400

    row = AgentProposal.query.filter_by(id=proposal_id, actor_email=g.user_email).first()
    if not row:
        return jsonify({"error": "Proposal not found"}), 404
    if row.status != "pending":
        return jsonify({"error": f"Proposal already {row.status}"}), 409

    row.decided_at = datetime.now(timezone.utc)
    row.decision_note = note

    # Carry the agent's reasoning onto the decision itself, so the ledger entry
    # is self-contained: reviewing an approve/reject later shows *what* was
    # decided and the reasoning it was decided on, without joining back to the
    # proposal row.
    reasoning = {
        "action": row.action,
        "shares": row.shares,
        "confidence": row.confidence,
        "rationale": row.rationale,
        "evidence_used": row.evidence_used,
        "risks": row.risks,
        "backtest_run_id": str(row.backtest_run_id) if row.backtest_run_id else None,
        "model": row.model,
    }

    if decision == "reject":
        row.status = "rejected"
        write_audit("agent_reject", entity=row.ticker,
                    payload={"proposal_id": str(row.id), "note": note, **reasoning},
                    snapshot_ref=(row.snapshot_refs or [None])[0])
        db.session.commit()
        return jsonify({"proposal": serialize_proposal(row)}), 200

    # ---- approved ----
    row.status = "approved"
    write_audit("agent_approve", entity=row.ticker,
                payload={"proposal_id": str(row.id), "note": note, **reasoning},
                snapshot_ref=(row.snapshot_refs or [None])[0])

    if row.action == "hold" or row.shares == 0:
        # Nothing to execute; approval is the end of the loop.
        row.status = "executed"
        db.session.commit()
        return jsonify({"proposal": serialize_proposal(row), "executed": False}), 200

    try:
        executed = apply_holding_change(
            g.user_email, row.ticker,
            shares=row.shares if row.action == "buy" else -row.shares,
            price=get_quote_pair(row.ticker)[0],
        )
    except ValueError as e:
        row.status = "failed"
        row.decision_note = f"{note or ''} (execution failed: {e})".strip()
        write_audit("agent_execute_failed", entity=row.ticker,
                    payload={"proposal_id": str(row.id), "error": str(e)})
        db.session.commit()
        return jsonify({"error": str(e), "proposal": serialize_proposal(row)}), 400

    row.status = "executed"
    write_audit("agent_execute", entity=row.ticker,
                payload={"proposal_id": str(row.id), **executed})
    db.session.commit()

    return jsonify({"proposal": serialize_proposal(row), "executed": True,
                    "result": executed}), 200

# ---------------------------------------------- Backtesting --------------------------------------------------------------------------------------

def load_closes_for_backtest(ticker, start=None, end=None):
    """
    Closing prices for a backtest, preferring stored snapshots.

    Returns (Series, snapshot_refs). Reusing a snapshot means the run cites the
    exact prices it saw, which is what makes it reproducible later.
    """
    snapshot_refs = []

    def _from_snapshot(snap, snap_id):
        rows = snap["series"]
        idx = pd.to_datetime([r["date"] for r in rows])
        if snap_id:
            snapshot_refs.append(snap_id)
        return pd.Series([r["price"] for r in rows], index=idx, dtype=float)

    # "price_history" holds the deep series backtests need. The chart route's
    # "price" snapshot only covers a year — not enough for a strategy that
    # ranks on a 252-bar lookback — so it is a last resort, not a fallback we
    # reach for before trying to fetch properly.
    snap, snap_id = get_snapshot("price_history", ticker=ticker,
                                 max_age_seconds=BACKTEST_HISTORY_TTL)
    if isinstance(snap, dict) and snap.get("series"):
        closes = _from_snapshot(snap, snap_id)
    else:
        try:
            hist = yf.download(ticker, start=BACKTEST_HISTORY_START, end=date.today(),
                               progress=False, auto_adjust=True)
            if hist.empty:
                raise ValueError(f"No price history available for {ticker}")
            col = hist["Close"]
            if hasattr(col, "columns"):  # yfinance may return MultiIndex columns
                col = col.iloc[:, 0]
            closes = col.astype(float).dropna()
            series = [{"date": str(i.date()), "price": float(v)} for i, v in closes.items()]
            snapshot_refs.append(
                put_snapshot("price_history", {"ticker": ticker, "series": series}, ticker=ticker)
            )
        except Exception:
            # Rate limited or delisted: a year of chart data still beats failing
            # outright, and the bar-count check will reject it if it is too short.
            shallow, shallow_id = get_snapshot("price", ticker=ticker,
                                               max_age_seconds=30 * 24 * 3600)
            if not (isinstance(shallow, dict) and shallow.get("series")):
                raise
            closes = _from_snapshot(shallow, shallow_id)

    if start:
        closes = closes[closes.index >= pd.to_datetime(start)]
    if end:
        closes = closes[closes.index <= pd.to_datetime(end)]

    return closes, snapshot_refs

def load_universe_closes(tickers, start=None, end=None):
    """
    Aligned closing prices for a universe, as a DataFrame of dates by ticker.

    Each ticker reuses the same snapshot path as a single-asset run, so a
    portfolio backtest cites exactly the same evidence. Tickers with no data
    are reported rather than silently dropped — a universe that quietly shrank
    would change the result without explaining why.
    """
    series_map = {}
    snapshot_refs = []
    missing = []

    for ticker in tickers:
        try:
            closes, refs = load_closes_for_backtest(ticker, start, end)
        except Exception:
            missing.append(ticker)
            continue
        if closes is None or closes.empty:
            missing.append(ticker)
            continue
        series_map[ticker] = closes
        snapshot_refs.extend(refs)

    if len(series_map) < 2:
        raise ValueError(
            "Need at least two tickers with price history. "
            f"No data for: {', '.join(missing) or 'none'}"
        )

    # Inner join on dates so every name is priced on every bar the basket
    # trades; a ragged frame would make weights and returns disagree.
    frame = pd.DataFrame(series_map).dropna()
    if frame.shape[0] < 2:
        raise ValueError("Tickers do not share enough overlapping history")

    return frame, list(dict.fromkeys(snapshot_refs)), missing

@app.route('/strategies', methods=['GET'])
@require_auth
def list_strategies():
    """
    The strategy catalogue: labels, families and parameter schemas.

    Served rather than duplicated in the frontend so the form controls, the
    validation and the agent's proposal schema all read from one definition.
    """
    out = []
    for key, spec in sorted(backtesting.STRATEGY_SPECS.items(),
                            key=lambda kv: kv[1]["complexity"]):
        # Parameters go out as an ordered array: jsonify sorts object keys, which
        # would scramble the authored field order the form renders from.
        out.append({
            **{k: v for k, v in spec.items() if k != "params"},
            "id": key,
            "params": [{"name": name, **meta} for name, meta in spec["params"].items()],
        })
    return jsonify({"strategies": out}), 200

class BacktestError(ValueError):
    """A backtest that cannot run, with the HTTP status the API should return."""

    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra

def execute_backtest(actor_email, strategy, params=None, ticker=None, universe=None,
                     start=None, end=None, starting_cash=10000.0):
    """
    Run a backtest, persist it as evidence, and return the full result.

    Shared by the HTTP route and the agent's run_backtest tool so a backtest the
    agent commissions is the same artifact, stored the same way, as one a human
    runs — there is no second implementation that could drift.

    Raises BacktestError for anything the caller should report rather than crash.
    """
    try:
        strategy, params = backtesting.coerce_params(strategy or "ma_crossover", params)
    except ValueError as e:
        raise BacktestError(str(e), known=sorted(backtesting.STRATEGY_FUNCS)) from e

    spec = backtesting.STRATEGY_SPECS[strategy]

    try:
        starting_cash = float(starting_cash)
    except (TypeError, ValueError) as e:
        raise BacktestError("starting_cash must be a number") from e
    if starting_cash <= 0:
        raise BacktestError("starting_cash must be positive")

    missing = []
    try:
        if spec["multi_asset"]:
            names = [t.strip().upper() for t in (universe or []) if t and t.strip()]
            names = list(dict.fromkeys(names))
            if len(names) < spec.get("min_universe", 2):
                raise BacktestError(
                    f"{spec['label']} needs at least {spec.get('min_universe', 2)} "
                    f"tickers to rank against each other."
                )
            closes, snapshot_refs, missing = load_universe_closes(names, start, end)
        else:
            ticker = (ticker or "").upper().strip()
            if not ticker:
                raise BacktestError("ticker is required")
            closes, snapshot_refs = load_closes_for_backtest(ticker, start, end)
    except BacktestError:
        raise
    except ValueError as e:
        raise BacktestError(str(e)) from e
    except Exception as e:
        status = 429 if ("Rate limit" in str(e) or "Too Many Requests" in str(e)) else 500
        raise BacktestError(str(e), status=status) from e

    bars = closes.shape[0]
    needed = backtesting.required_bars(strategy, params)
    if bars < needed:
        raise BacktestError(
            f"{spec['label']} needs about {needed} bars of history to warm up, "
            f"but only {bars} are available. Shorten the lookback or widen the date range.",
            bars=bars, required_bars=needed,
        )

    try:
        if spec["multi_asset"]:
            result = backtesting.run_portfolio_backtest(
                closes, strategy=strategy, params=params, starting_cash=starting_cash
            )
        else:
            result = backtesting.run_backtest(
                closes, strategy=strategy, params=params,
                starting_cash=starting_cash, ticker=ticker
            )
    except ValueError as e:
        raise BacktestError(str(e)) from e

    run = BacktestRun(
        actor_email=actor_email,
        strategy=strategy,
        params=json_safe({**params, "starting_cash": starting_cash,
                          "cost_bps": result["cost_bps"],
                          "slippage_bps": result["slippage_bps"]}),
        universe=result["universe"],
        start_date=result["start_date"],
        end_date=result["end_date"],
        metrics=json_safe({**result["metrics"], "benchmark": result["benchmark_metrics"]}),
        equity_curve=json_safe(result["equity_curve"]),
        trades=json_safe(result["trades"]),
        snapshot_refs=snapshot_refs,
    )
    db.session.add(run)
    db.session.flush()

    write_audit(
        "backtest_run",
        entity=", ".join(result["universe"]) or "-",
        payload={
            "backtest_run_id": str(run.id),
            "strategy": strategy,
            "params": json_safe(params),
            "total_return_pct": result["metrics"]["total_return_pct"],
            "beat_benchmark": result["metrics"]["beat_benchmark"],
        },
        actor_email=actor_email,
        snapshot_ref=snapshot_refs[0] if snapshot_refs else None,
    )
    db.session.commit()

    result["backtest_run_id"] = str(run.id)
    result["ticker"] = ", ".join(result["universe"])
    result["snapshot_refs"] = snapshot_refs
    if missing:
        result["missing_tickers"] = missing
    return result

@app.route('/backtest', methods=['POST'])
@require_auth
def run_backtest_route():
    """
    Backtest a strategy and persist the run.

    Single-asset strategies take `ticker`; cross-sectional ones take a
    `universe` list and run on the portfolio engine. Either way the run is
    immutable evidence: the parameters actually used, metrics, equity curve
    and the snapshots the prices came from, so it can be reproduced and cited.
    """
    body = request.get_json(silent=True) or {}
    try:
        result = execute_backtest(
            g.user_email,
            strategy=body.get("strategy"),
            params=body.get("params"),
            ticker=body.get("ticker"),
            universe=body.get("universe"),
            start=body.get("start"),
            end=body.get("end"),
            starting_cash=body.get("starting_cash", 10000),
        )
    except BacktestError as e:
        return jsonify({"error": str(e), **e.extra}), e.status
    return jsonify(result), 200

@app.route('/backtest-runs', methods=['GET'])
@require_auth
def list_backtest_runs():
    """Past runs for this user, newest first (curve and trades omitted)."""
    runs = (BacktestRun.query
            .filter_by(actor_email=g.user_email)
            .order_by(BacktestRun.created_at.desc())
            .limit(25).all())

    return jsonify({"runs": [
        {
            "id": str(r.id),
            "strategy": r.strategy,
            "params": r.params,
            "universe": r.universe,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "metrics": r.metrics,
            "notes": r.notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in runs
    ]}), 200

@app.route('/backtest-runs/<run_id>/note', methods=['POST'])
@require_auth
def set_backtest_note(run_id):
    """
    Attach or update a human note on one of the user's backtest runs.

    The run's numbers are immutable; the note is the one mutable, human layer on
    top — and the edit itself is recorded in the audit log, so even the notes
    have a trail.
    """
    try:
        uuid.UUID(str(run_id))
    except (ValueError, AttributeError):
        return jsonify({"error": "Invalid run id"}), 400

    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip()
    if len(note) > 2000:
        return jsonify({"error": "Note is too long (2000 characters max)."}), 400

    run = BacktestRun.query.filter_by(id=run_id, actor_email=g.user_email).first()
    if not run:
        return jsonify({"error": "Backtest run not found"}), 404

    run.notes = note or None
    write_audit(
        "backtest_note",
        entity=", ".join(run.universe or []) or run.strategy,
        payload={"backtest_run_id": str(run.id), "note": note,
                 "cleared": not bool(note)},
    )
    db.session.commit()
    return jsonify({"id": str(run.id), "notes": run.notes}), 200

# ---------------------------------------------- Portfolio analytics ------------------------------------------------------------------------------

@app.route('/portfolio-summary', methods=['GET'])
@require_auth
def portfolio_summary():
    """
    Aggregate view of the authenticated user's portfolio.

    Individual holdings are tracked elsewhere; this rolls them up into the
    numbers a dashboard needs: value, cost basis, unrealized P/L, day change,
    allocation weights and the best/worst performer.
    """
    holdings = Holdings.query.filter_by(email=g.user_email).all()
    owned = [h for h in holdings if h.num_shares and h.num_shares != 0]

    positions = []
    total_value = 0.0
    total_cost = 0.0
    prev_value = 0.0            # portfolio value at yesterday's close
    day_change_known = False    # False if no holding had a previous close

    for h in owned:
        shares = int(h.num_shares)
        avg_price = float(h.avg_price)
        cost_basis = avg_price * shares

        last, prev = get_quote_pair(h.ticker)
        # Fall back to cost basis so an unavailable quote doesn't zero out the
        # portfolio; the position is flagged so the UI can mark it stale.
        market_price = float(last) if last is not None else avg_price
        market_value = market_price * shares

        pl_abs = market_value - cost_basis
        pl_pct = (pl_abs / cost_basis * 100) if cost_basis else None

        if prev is not None:
            prev_value += float(prev) * shares
            day_change_known = True
        else:
            prev_value += market_value  # contributes zero day change

        total_value += market_value
        total_cost += cost_basis

        positions.append({
            "ticker": h.ticker,
            "num_shares": shares,
            "avg_price": avg_price,
            "last_quote": float(last) if last is not None else None,
            "market_value": market_value,
            "cost_basis": cost_basis,
            "pl_abs": pl_abs,
            "pl_pct": pl_pct,
            "quote_available": last is not None,
        })

    # Allocation weights, largest first.
    for p in positions:
        p["weight"] = (p["market_value"] / total_value * 100) if total_value else 0.0
    positions.sort(key=lambda p: p["market_value"], reverse=True)

    ranked = [p for p in positions if p["pl_pct"] is not None]
    ranked.sort(key=lambda p: p["pl_pct"], reverse=True)

    total_return_abs = total_value - total_cost
    day_change_abs = (total_value - prev_value) if day_change_known else None

    summary = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "total_value": total_value,
        "total_cost": total_cost,
        "total_return_abs": total_return_abs,
        "total_return_pct": (total_return_abs / total_cost * 100) if total_cost else None,
        "day_change_abs": day_change_abs,
        "day_change_pct": (day_change_abs / prev_value * 100) if (day_change_known and prev_value) else None,
        "position_count": len(positions),
        "pinned_count": sum(1 for h in holdings if h.pinned and (not h.num_shares)),
        "positions": positions,
        "best": ranked[0] if ranked else None,
        "worst": ranked[-1] if len(ranked) > 1 else None,
        "stale_quotes": [p["ticker"] for p in positions if not p["quote_available"]],
    }

    db.session.commit()  # persist any quote snapshots fetched above
    return jsonify(summary), 200

#use this route to see if a user can unpin a stock
@app.route('/remove-pinned-stock', methods=['GET'])
@require_auth
def remove_pin():
    query = (request.args.get('query') or "").upper()
    email = g.user_email

    # Early return in case of incorrect credentials
    if not query:
        return jsonify({"error": "Missing ticker parameter"}), 400

    # Find the holding
    # print('this is the query to be removed: ',query)
    holding = Holdings.query.filter_by(email=email, ticker=query).first()

    # Ensure holding exists before checking attributes
    if holding:
        if holding.avg_price == 0.0:
            db.session.delete(holding)
            write_audit("unpin", entity=query)
            db.session.commit()
            return jsonify({"message": f"Holding for {query} deleted successfully"}), 200
        else:
            return jsonify({"error": "Cannot unpin a stock that is actively held"}), 401
    else:
        return jsonify({"error": "Holding not found"}), 404
    
# ---------------------------------------------- Sentiment Analysis Routes --------------------------------------------------------------------------

MAX_HEADLINES = 20

def _extract_news_item(item):
    """
    Pull (headline, link) out of one yfinance news entry.

    The payload shape has changed across yfinance versions: older releases
    return flat {title, link} dicts, newer ones nest under "content" with
    canonicalUrl/clickThroughUrl. Handle both rather than pinning a version.
    """
    content = item.get("content") or item
    headline = content.get("title") or item.get("title")
    link = (
        item.get("link")
        or (content.get("canonicalUrl") or {}).get("url")
        or (content.get("clickThroughUrl") or {}).get("url")
    )
    if not headline:
        return None
    return {"headline": headline.strip(), "link": link or ""}

def get_news_via_yfinance(ticker):
    """Preferred source: yfinance's news API, which is maintained upstream."""
    items = yf.Ticker(ticker).news or []
    out = []
    for item in items:
        parsed = _extract_news_item(item)
        if parsed:
            out.append(parsed)
    return out[:MAX_HEADLINES]

def get_news_via_scrape(ticker):
    """
    Fallback: scrape the quote page.

    Kept only as a backstop. Yahoo's markup changes without notice, and the
    old /news/ path now 404s, so this is best-effort by nature.
    """
    url = f"https://finance.yahoo.com/quote/{ticker}/"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    news_data = []
    seen = set()
    # Headlines have moved between h3 and h2 over time; accept either, and take
    # the enclosing anchor as the link.
    for item in soup.find_all(["h3", "h2"]):
        headline = item.get_text(strip=True)
        if not headline or headline in seen:
            continue

        link_parent = item.find_parent("a")
        link = link_parent["href"] if (link_parent and link_parent.has_attr("href")) else ""
        if link.startswith("/"):
            link = f"https://finance.yahoo.com{link}"

        # The quote page is full of headings that are not news: "Trading
        # disclosure", "U.S. markets closed", bare percentages. A real headline
        # links to an article and reads like a sentence, so require both.
        if not link or len(headline) < 25 or not re.search(r"[A-Za-z]{3,}\s+\w", headline):
            continue

        seen.add(headline)
        news_data.append({"headline": headline, "link": link})

    return news_data[:MAX_HEADLINES]

def get_stock_news(ticker):
    """
    Latest headlines for a ticker, preferring the yfinance API over scraping.
    """
    try:
        items = get_news_via_yfinance(ticker)
        if items:
            return items
        print(f"yfinance returned no news for {ticker}; falling back to scrape.")
    except Exception as e:
        # Rate limits and upstream changes both land here.
        print(f"yfinance news failed for {ticker}: {e}; falling back to scrape.")

    return get_news_via_scrape(ticker)

# TextBlob's lexicon is general-purpose and scores most market vocabulary as
# neutral ("record earnings beat" -> 0.0), which would make the score useless
# here. This overlay nudges polarity using terms that actually carry direction
# in financial headlines. Values are deliberately modest so TextBlob still
# drives the base reading.
FINANCE_SENTIMENT_TERMS = {
    # bullish
    "soar": 0.5, "soars": 0.5, "surge": 0.45, "surges": 0.45, "rally": 0.4,
    "rallies": 0.4, "jump": 0.35, "jumps": 0.35, "climb": 0.3, "climbs": 0.3,
    "beat": 0.4, "beats": 0.4, "tops": 0.35, "upgrade": 0.45, "upgraded": 0.45,
    "outperform": 0.4, "record": 0.3, "profit": 0.3, "growth": 0.3,
    "bullish": 0.5, "strong": 0.3, "gain": 0.3, "gains": 0.3, "raises": 0.3,
    # bearish
    "plunge": -0.5, "plunges": -0.5, "slump": -0.45, "slumps": -0.45,
    "tumble": -0.45, "tumbles": -0.45, "sink": -0.4, "sinks": -0.4,
    "fall": -0.3, "falls": -0.3, "drop": -0.3, "drops": -0.3, "slide": -0.3,
    "miss": -0.4, "misses": -0.4, "downgrade": -0.45, "downgraded": -0.45,
    "underperform": -0.4, "loss": -0.35, "losses": -0.35, "recall": -0.35,
    "bearish": -0.5, "weak": -0.35, "lawsuit": -0.35, "probe": -0.3,
    "investigation": -0.3, "cuts": -0.3, "warns": -0.35, "halts": -0.3,
    "crash": -0.5, "crashes": -0.5, "plummet": -0.55, "plummets": -0.55,
    "selloff": -0.4, "layoffs": -0.4, "bankruptcy": -0.6, "fraud": -0.55,
    "delisted": -0.5, "halted": -0.35, "shortfall": -0.35,
    # more bullish
    "highs": 0.35, "breakout": 0.4, "approval": 0.35, "approved": 0.35,
    "wins": 0.35, "boosts": 0.35, "jumped": 0.35, "doubled": 0.3,
}

def finance_lexicon_adjustment(text):
    """Sum the overlay weights for finance terms present in the text."""
    words = re.findall(r"[a-z']+", text.lower())
    return sum(FINANCE_SENTIMENT_TERMS.get(w, 0.0) for w in words)

def score_headline(headline):
    """
    Score one headline in [-1, 1].

    TextBlob supplies the base polarity; the finance overlay corrects for market
    vocabulary it does not know. Both parts are returned so the score can be
    audited rather than taken on faith.
    """
    blob = TextBlob(headline)
    base = float(blob.sentiment.polarity)
    adjustment = finance_lexicon_adjustment(headline)
    # tanh keeps the result inside [-1, 1] without hard clipping. A plain clamp
    # pinned every headline with two or three loaded words to exactly +/-1 and
    # threw away the difference between "rallies" and "soars on record beat".
    combined = float(np.tanh(base + adjustment))
    return {
        "polarity": round(combined, 4),
        "textblob_polarity": round(base, 4),
        "lexicon_adjustment": round(adjustment, 4),
        "subjectivity": round(float(blob.sentiment.subjectivity), 4),
        "label": sentiment_label(combined),
    }

def sentiment_label(polarity):
    """Bucket a polarity score into a human-readable label."""
    if polarity >= 0.15:
        return "positive"
    if polarity <= -0.15:
        return "negative"
    return "neutral"

@app.route("/get-sentiment-analysis", methods=["GET"])
@require_auth
def fetchSentiAnal():
    """
    API endpoint that takes a stock ticker and returns sentiment analysis along with Yahoo Finance news links.
    """
    stock = request.args.get("stock", "").upper()

    if not stock:
        return jsonify({"error": "Please provide a stock ticker"}), 400

    print("Received request in fetchSentiAnal:", stock)  # Debugging

    # Headlines plus their scores are snapshotted: the Yahoo page changes
    # constantly, so a score is only reproducible if the text it came from is
    # stored alongside it.
    cached, _ = get_snapshot("sentiment", ticker=stock)
    if cached is not None:
        return jsonify(cached), 200

    try:
        news_data = get_stock_news(stock)
    except Exception as e:
        print(f"News scrape failed for {stock}: {e}")
        stale, _ = get_snapshot("sentiment", ticker=stock, max_age_seconds=30 * 24 * 3600)
        if stale is not None:
            return jsonify(stale), 200
        return jsonify({"error": "Could not retrieve news at this moment"}), 503

    if not news_data:
        return jsonify({"error": "No news found"}), 404

    for item in news_data:
        item["sentiment"] = score_headline(item["headline"])

    scores = [item["sentiment"]["polarity"] for item in news_data]
    overall = sum(scores) / len(scores)

    result = {
        "ticker": stock,
        "news": news_data,
        "overall_sentiment": {
            "polarity": round(overall, 4),
            "label": sentiment_label(overall),
            "headline_count": len(news_data),
            "positive": sum(1 for s in scores if s >= 0.15),
            "neutral": sum(1 for s in scores if -0.15 < s < 0.15),
            "negative": sum(1 for s in scores if s <= -0.15),
        },
    }

    snapshot_id = put_snapshot("sentiment", result, ticker=stock)
    db.session.commit()
    result["snapshot_ref"] = snapshot_id
    return jsonify(result), 200

# fetches the data for making the price chart
@app.route('/get-chart-data', methods=['GET'])
@require_auth
def fetchPriceChartData():
    stock = request.args.get("stock", "").upper()  # Get stock ticker from query param

    if not stock:
        return jsonify({"error": "Stock ticker is required"}), 400

    # Serve from the snapshot store when fresh (see SNAPSHOT_TTL_SECONDS).
    # Older snapshots stored a bare list; only the current {series, signals}
    # shape is reusable, so a legacy payload is treated as a miss.
    cached, _ = get_snapshot("price", ticker=stock)
    if isinstance(cached, dict) and "series" in cached:
        return jsonify(cached), 200

    try:
        stock_data = yf.Ticker(stock)
        hist = stock_data.history(period="1y")  # Fetch 1 year of historical data

        if hist.empty:
            return jsonify({"error": "Invalid stock symbol or no data available"}), 400

        # Attach the 20/50-day moving averages, then find their crossovers.
        hist = calculate_moving_averages(hist)
        crossovers = generate_trading_signals(hist)

        # Format data for frontend. MA values are None until enough history
        # accumulates, which recharts renders as a gap rather than a zero.
        series = [
            {
                "date": str(index.date()),
                "price": round(float(row["Close"]), 4),
                "ma20": None if pd.isna(row["MA_20"]) else round(float(row["MA_20"]), 4),
                "ma50": None if pd.isna(row["MA_50"]) else round(float(row["MA_50"]), 4),
            }
            for index, row in hist.iterrows()
        ]

        signals = [
            {
                "date": str(index.date()),
                "price": round(float(row["Close"]), 4),
                # "Buy" == golden cross (MA20 crossing above MA50), "Sell" == death cross.
                "signal": row["Signal"],
            }
            for index, row in crossovers.iterrows()
        ]

        data = {
            "ticker": stock,
            "series": series,
            "signals": signals,
            "signal_strategy": "ma20_50_crossover",
        }

        snapshot_id = put_snapshot("price", data, ticker=stock)
        # Signals are what a later agent would act on, so record their
        # generation against the exact price snapshot they came from.
        if signals:
            write_audit(
                "signals_generated",
                entity=stock,
                payload={
                    "strategy": "ma20_50_crossover",
                    "signal_count": len(signals),
                    "latest": signals[-1],
                },
                snapshot_ref=snapshot_id,
            )
        db.session.commit()
        data["snapshot_ref"] = snapshot_id
        return jsonify(data)
    except Exception as e:
        db.session.rollback()
        # Fall back to stale data rather than breaking the chart entirely.
        stale, _ = get_snapshot("price", ticker=stock, max_age_seconds=30 * 24 * 3600)
        if isinstance(stale, dict) and "series" in stale:
            return jsonify(stale), 200
        status = 429 if ("Rate limit" in str(e) or "Too Many Requests" in str(e)) else 500
        return jsonify({"error": str(e)}), status


# --------------------------------------------------------------------------- helper functions -------------------------------------------------------------------------
def growthEstimate(stock):
    print(stock)

def load_existing_data():
    """
    Reads the CSV file and loads existing data into a set for quick lookup.
    The set stores (Ticker, Year, Metric) tuples to check for duplicates.
    """
    existing_entries = set()
    file_path = 'stockAnalysisData.csv'
    
    if os.path.exists(file_path):  # Only read if the file exists
        with open(file_path, mode='r', newline="") as file:
            reader = csv.reader(file)
            next(reader, None)  # Skip headers

            for row in reader:
                if len(row) >= 3:  # Ensure the row has enough elements
                    ticker, year, metric = row[:3]
                    existing_entries.add((ticker, year, metric))
    
    return existing_entries

# takes in financials & additionalData dict {}
def storeDataInCSV(financials, additionalData, stock):
    file_path = 'stockAnalysisData.csv'
    file_exists = os.path.exists(file_path)

    # load the existing data
    existing_entries = load_existing_data() 

    # Ensure financials is valid otherwise early return 
    if not financials or not isinstance(financials, dict):
        print(f"Skipping {stock}: No financial data available.")
        return

    with open(file_path, mode='a', newline="") as file:
        writer = csv.writer(file, quotechar='"', quoting=csv.QUOTE_MINIMAL)

        # Define headers for key-value pair storage
        headers = ["Ticker", "Year", "Metric", "Value"]

        # Write headers if file does not exist
        if not file_exists:
            writer.writerow(headers)

        new_entries = []
        # Write each financial metric as a separate key-value pair
        for year, metrics in financials.items():
            # Format year as YYYY-MM-DD
            formatted_year = datetime.strptime(year, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d") if " " in year else year
            
            for metric, value in metrics.items():
                entry_key = (stock, formatted_year, metric)
                if entry_key not in existing_entries:  # Only write if not in existing data
                    writer.writerow([stock, formatted_year, metric, value if value is not None else "N/A"])
                    new_entries.append(entry_key)

        # Also store additional data in key-value format
        for field, value in additionalData.items():
            entry_key_2 = (stock, "N/A", field)
            if entry_key_2 not in existing_entries:
                writer.writerow([stock, "N/A", field, value if value is not None else "N/A"])
                new_entries.append(entry_key_2)

    print(f"Data for {stock} stored successfully in key-value format.")

    

#----------------------------------------------------------- global list of sp500 companies -----------------------------------------------------------------------------------------------------
sp500_tickers = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK.B", "NVDA", "JPM",
    "JNJ", "UNH", "HD", "PG", "V", "BAC", "MA", "DIS", "PYPL", "VZ",
    "ADBE", "NFLX", "CMCSA", "PFE", "KO", "T", "PEP", "CSCO", "XOM",
    "ABT", "CRM", "ACN", "AVGO", "COST", "WMT", "MCD", "MDT", "DHR", "BMY",
    "TXN", "NEE", "UNP", "QCOM", "HON", "LLY", "IBM", "LIN", "MRK",
    "LOW", "ORCL", "PM", "SBUX", "MMM", "CAT", "AMGN", "CVX", "GS", "BLK",
    "CHTR", "AXP", "SPGI", "NOW", "ISRG", "AMD", "GE", "LMT", "BA", "DE",
    "SYK", "BKNG", "PLD", "MO", "ADI", "MDLZ", "AMT", "C", "TMO", "GILD",
    "INTU", "SYF", "FIS", "HUM", "DUK", "EL", "MMC", "SO", "APD",
    "TJX", "CB", "PNC", "BDX", "ICE", "NSC", "SHW", "CL", "CCI",
    "CI", "EW", "ZTS", "FDX", "AON", "WM", "D", "ITW", "EMR",
    "ETN", "ECL", "STZ", "ADP", "FISV", "SLB", "PSA", "MCO", "ILMN",
    "MNST", "AEP", "KMB", "AIG", "BK", "LRCX", "REGN", "BSX", "GM",
    "HCA", "PSX", "MPC", "KLAC", "GME", "ASTS", "PLTR",

    # Additional Large-Cap Stocks
    # "SNOW", "UBER", "LYFT", "SQ", "ROKU", "TWLO", "FSLY", "SHOP", "TEAM",
    # "ZM", "DOCU", "CRWD", "PANW", "ZS", "OKTA", "NET", "MDB", "DDOG",
    
    # # Financial Sector
    # "WFC", "USB", "MS", "TFC", "CME", "TRV", "ALL", "PGR", "MET",

    # # Energy Sector
    # "OXY", "COP", "MRO", "EOG", "FANG", "HAL", "BKR", "VLO",

    # # Healthcare & Biotech
    # "BIIB", "MRNA", "VRTX", "DXCM", "IDXX", "ALGN", "BAX", "WST", "PKI",
    
    # # Industrials
    # "CSX", "CP", "CNI", "ROP", "IEX", "XYL", "TT", "AME", "ODFL",
    
    # # Consumer Goods & Retail
    # "NKE", "LULU", "TGT", "BBY", "DLTR", "ULTA", "YUM", "DG", "KHC",

    # # Real Estate
    # "EQIX", "WY", "AVB", "EQR", "O", "BXP", "VTR", "ESS", "HST",

    # # Emerging Tech & Growth Stocks
    # "AFRM", "HOOD", "RBLX", "SPCE", "DNA", "SOFI", "LCID", "RIVN", "FSR", "CHPT",
    # "RUN", "ENPH", "SEDG", "BLNK", "BE", "PLUG", "FCEL", "LTHM",

    # # Semiconductor Stocks
    # "ASML", "NXPI", "ON", "WDC", "MU", "STM", "MPWR", "COHR", "LITE", "SLAB",

    # # AI & Cloud Computing
    # "AI", "SMCI", "ARM",  "TSM", "INTC", "MRVL",

    # # Additional Notable Stocks
    # "TSLA", "RACE", "NIO", "XPEV", "LI", "BYDDF", "F", "GM", "STLA",
    # "PARA", "CMG", "DPZ", "PENN", "DKNG", "MTCH", "BILI", "SE"
]


# ------------------------------------------------------ run python server ------------------------------------------------------
# ---------------------------------------------- Realtime quotes (WebSocket) ----------------------------------------------------------------------

# Rooms are keyed by ticker; a client joins the rooms for the symbols on screen.
_quote_thread = None
_quote_thread_lock = Lock()
QUOTE_POLL_SECONDS = int(os.getenv("QUOTE_POLL_SECONDS", "30"))

def _authenticate_socket(auth):
    """
    Resolve a socket connection to a user via the same JWT as the HTTP API.

    Without this the socket would be an unauthenticated side channel around
    the auth added in Phase 1.
    """
    token = None
    if isinstance(auth, dict):
        token = auth.get("token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    return (claims.get("sub") or "").lower() or None

def _broadcast_quotes():
    """
    Background loop: poll subscribed tickers and emit changed quotes.

    yfinance has no streaming feed, so this is polling on an interval rather
    than true tick data. A real-time feed (Finnhub, Polygon) would replace the
    body of this loop without changing the client contract.
    """
    while True:
        socketio.sleep(QUOTE_POLL_SECONDS)
        try:
            with app.app_context():
                rooms = socketio.server.manager.rooms.get("/", {})
                # Room names that look like tickers are the subscriptions;
                # every client also sits in a room named after its own sid.
                tickers = [r for r in rooms.keys() if r and r.isupper()]
                for ticker in tickers:
                    last, prev = get_quote_pair(ticker)
                    if last is None:
                        continue
                    change = (last - prev) if prev is not None else None
                    socketio.emit("quote", {
                        "ticker": ticker,
                        "price": last,
                        "prev_close": prev,
                        "change_abs": change,
                        "change_pct": (change / prev * 100) if (change is not None and prev) else None,
                        "at": datetime.now(timezone.utc).isoformat(),
                    }, room=ticker)
                db.session.commit()  # persist snapshots created while polling
        except Exception as e:
            print(f"Quote broadcast error: {e}")

@socketio.on("connect")
def socket_connect(auth):
    email = _authenticate_socket(auth)
    if not email:
        return False  # refuse the connection

    global _quote_thread
    with _quote_thread_lock:
        if _quote_thread is None:
            _quote_thread = socketio.start_background_task(_broadcast_quotes)

    emit("connected", {"email": email, "poll_seconds": QUOTE_POLL_SECONDS})
    return True

@socketio.on("subscribe")
def socket_subscribe(data):
    """Join the rooms for the tickers a client currently has on screen."""
    tickers = (data or {}).get("tickers") or []
    joined = []
    for t in tickers[:25]:  # cap so one client cannot subscribe to everything
        ticker = str(t).upper().strip()
        if ticker:
            join_room(ticker)
            joined.append(ticker)
    emit("subscribed", {"tickers": joined})

@socketio.on("unsubscribe")
def socket_unsubscribe(data):
    for t in (data or {}).get("tickers") or []:
        leave_room(str(t).upper().strip())

def apply_light_migrations():
    """
    Additive, idempotent schema tweaks for columns added after a table already
    exists in a deployed database.

    db.create_all() creates missing tables but never alters an existing one, so
    a column added to a model later has to be added explicitly. Each statement
    is guarded so running this repeatedly is safe.
    """
    from sqlalchemy import text
    statements = [
        "ALTER TABLE backtest_run ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE agent_proposal ADD COLUMN IF NOT EXISTS agent_run_id UUID",
    ]
    with db.engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

def collect_referenced_snapshot_ids():
    """
    Every market_snapshot id cited as evidence somewhere.

    A snapshot has two lives: a freshness cache, and immutable evidence a
    decision was based on. The second must never be pruned or the decision stops
    being reproducible — so retention has to know exactly which snapshots are
    still pointed at, across the audit ledger, backtests and proposals.
    """
    referenced = set()

    for (sid,) in (db.session.query(AuditLog.snapshot_ref)
                   .filter(AuditLog.snapshot_ref.isnot(None)).distinct()):
        referenced.add(str(sid))

    for model in (BacktestRun, AgentProposal):
        for (arr,) in (db.session.query(model.snapshot_refs)
                       .filter(model.snapshot_refs.isnot(None))):
            for ref in (arr or []):
                referenced.add(str(ref))

    return referenced

def prune_snapshots(days=90, dry_run=False):
    """
    Delete cache snapshots older than `days`, preserving any cited as evidence.

    Returns a summary. Evidence snapshots are kept regardless of age; only stale,
    uncited cache rows are removed, so the audit trail stays fully reproducible.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    referenced = collect_referenced_snapshot_ids()

    old = MarketSnapshot.query.filter(MarketSnapshot.fetched_at < cutoff).all()
    victims = [s for s in old if str(s.id) not in referenced]

    summary = {
        "cutoff": cutoff.isoformat(),
        "retention_days": days,
        "older_than_cutoff": len(old),
        "kept_as_evidence": len(old) - len(victims),
        "prunable": len(victims),
        "dry_run": dry_run,
    }
    if not dry_run and victims:
        for s in victims:
            db.session.delete(s)
        db.session.commit()
        summary["deleted"] = len(victims)
    return summary

@app.cli.command("prune-snapshots")
@click.option("--days", default=90, show_default=True,
              help="Delete cache snapshots older than this many days.")
@click.option("--dry-run", is_flag=True,
              help="Report what would be deleted without deleting anything.")
def prune_snapshots_command(days, dry_run):
    """Prune stale market_snapshot rows, keeping any cited as evidence."""
    summary = prune_snapshots(days=days, dry_run=dry_run)
    for k, v in summary.items():
        print(f"  {k}: {v}")

@app.cli.command("init-db")
def init_db_command():
    """
    Create any missing tables and apply additive migrations (idempotent).

    Under gunicorn the module is imported rather than executed, so the
    __main__ block below never runs. Production deploys call this instead:
        flask --app app init-db
    """
    db.create_all()
    apply_light_migrations()
    print("Database initialized.")

@app.route("/health", methods=["GET"])
def health():
    """Unauthenticated liveness probe for the host's health checks."""
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    # Create tables if they don't exist yet (safe/idempotent) so a fresh
    # database (e.g. a new Neon project) is initialized on first boot.
    with app.app_context():
        db.create_all()
        apply_light_migrations()
    # Served through SocketIO so websocket upgrades are handled; it falls back
    # to the normal WSGI server for plain HTTP requests.
    # Bind configuration comes from the environment so the same entrypoint works
    # locally and on a host that injects PORT.
    socketio.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=DEBUG,
        allow_unsafe_werkzeug=True,  # dev server only; gunicorn is used in prod
    )