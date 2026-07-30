from flask import Flask, jsonify, request, g
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask_cors import CORS
import os
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
from functools import wraps

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
    "sentiment": 3600,
}

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
    """Generates buy/sell signals based on MA crossovers"""
    df["Signal"] = np.where(df["MA_20"] > df["MA_50"], "Buy", "Sell")
    df["Crossover"] = df["Signal"].ne(df["Signal"].shift())  # Detect changes
    return df[df["Crossover"]]


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
        existing_holding = Holdings.query.filter_by(email=email_in, ticker=ticker_in).first()
        if existing_holding:
            # ============== SELL (shares < 0) ============== 
            if shares < 0:
                abs_shares = abs(shares)
                if existing_holding.num_shares < abs_shares:
                    return jsonify({"error": "Not enough shares to sell"}), 400

                existing_holding.num_shares -= abs_shares
                sold_ticker = existing_holding.ticker
                if existing_holding.num_shares == 0:
                    # All sold, remove holding
                    db.session.delete(existing_holding)
                else:
                    existing_holding.value = float(existing_holding.num_shares * existing_holding.avg_price)
                    # Mark columns as modified for SQLAlchemy
                    flag_modified(existing_holding, "num_shares")
                    flag_modified(existing_holding, "value")

                write_audit("sell", entity=ticker_in, payload={
                    "shares_sold": abs_shares,
                    "price": price,
                    "shares_remaining": existing_holding.num_shares,
                })
                db.session.commit()
                return jsonify({
                    "message": "Shares sold successfully",
                    "data": {
                        "ticker": sold_ticker
                    }
                    }), 200

            # ============== BUY (shares > 0) ==============
            else:
                original_shares = existing_holding.num_shares
                existing_holding.num_shares += shares

                # Weighted average price
                new_avg_price = (
                    (float(existing_holding.avg_price) * original_shares) +
                    (shares * float(price))
                ) / existing_holding.num_shares

                existing_holding.avg_price = new_avg_price
                existing_holding.value = float(existing_holding.num_shares * existing_holding.avg_price)

                flag_modified(existing_holding, "num_shares")
                flag_modified(existing_holding, "avg_price")
                flag_modified(existing_holding, "value")

                write_audit("buy", entity=ticker_in, payload={
                    "shares_bought": shares,
                    "price": price,
                    "shares_held": existing_holding.num_shares,
                    "new_avg_price": float(new_avg_price),
                })
                db.session.commit()

                return jsonify({
                    "message": "Holding updated successfully",
                    "data": {
                        "email": existing_holding.email,
                        "ticker": existing_holding.ticker,
                        "avg_price": existing_holding.avg_price,
                        "num_shares": existing_holding.num_shares,
                        "value": existing_holding.value,
                        "pinned": existing_holding.pinned
                    }
                }), 200

        else:
            # ============== New Holding (with nonzero shares) ==============
            if shares < 0:
                return jsonify({"error": "Cannot sell a stock you do not own"}), 400

            value_of_shares = float(price) * shares
            new_holding = Holdings(
                email=email_in,
                ticker=ticker_in,
                avg_price=float(price),
                num_shares=shares,
                value=value_of_shares,
                pinned=True  # or True, depending on your logic
            )
            db.session.add(new_holding)
            write_audit("buy_new", entity=ticker_in, payload={
                "shares_bought": shares,
                "price": price,
                "value": value_of_shares,
            })
            db.session.commit()

            return jsonify({
                "message": "New holding added successfully",
                "data": {
                    "email": new_holding.email,
                    "ticker": new_holding.ticker,
                    "avg_price": new_holding.avg_price,
                    "num_shares": new_holding.num_shares,
                    "value": new_holding.value,
                    "pinned": new_holding.pinned
                }
            }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Database Error: {str(e)}")
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    
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

    # Fetch latest stock price for each holding
    for i, hold in enumerate(holdings_list):
        if hold['pinned'] == False:
            continue # dont return this stock as user has pinned it BUT not bought it
        
        # print('hold object: ',hold) #{'ticker': 'ASTS', 'num_shares': 8, 'avg_price': 25.0, 'value': 200.0, 'pinned': True}
        stock = yf.Ticker(hold['ticker'])  # Fetch stock data
        
        data = stock.history(period="1d")  # Get last trading day's data
        if not data.empty:
            last_quote = data["Close"].iloc[-1]  # Get the latest closing price
            holdings_list[i]["last_quote"] = float(last_quote)  # Append to the correct stock
            
            price_diff = (last_quote - holdings_list[i]['avg_price'])
            total_return = ((price_diff/holdings_list[i]['avg_price'])*100)
            holdings_list[i]['total_return'] = total_return
        else:
            holdings_list[i]["last_quote"] = None  # Handle missing data
    # print('holdings list: ', holdings_list)
    return jsonify({"holdings": holdings_list}), 200

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

def get_stock_news(ticker):
    """
    Scrapes Yahoo Finance news headlines and links using the stock ticker.
    """
    url = f"https://finance.yahoo.com/quote/{ticker}/news/"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    news_data = []

    # Yahoo Finance wraps news articles inside <h3> tags with links
    for item in soup.find_all("h3"):
        headline = item.get_text()
        link_parent = item.find_parent("a")  # Get the <a> tag
        
        if link_parent and "href" in link_parent.attrs:
            link = link_parent["href"]  # Full URL
            
            news_data.append({"headline": headline, "link": link})

    news_data = news_data[:5]
    return news_data

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
    
    news_data = get_stock_news(stock)
    if not news_data:
        return jsonify({"error": "No news found"}), 404
    
    return jsonify({
        "ticker": stock,
        "news": news_data
    })
    
# fetches the data for making the price chart
@app.route('/get-chart-data', methods=['GET'])
@require_auth
def fetchPriceChartData():
    stock = request.args.get("stock", "").upper()  # Get stock ticker from query param

    if not stock:
        return jsonify({"error": "Stock ticker is required"}), 400

    # Serve from the snapshot store when fresh (see SNAPSHOT_TTL_SECONDS).
    cached, _ = get_snapshot("price", ticker=stock)
    if cached is not None:
        return jsonify(cached), 200

    try:
        stock_data = yf.Ticker(stock)
        hist = stock_data.history(period="1y")  # Fetch 1 year of historical data

        if hist.empty:
            return jsonify({"error": "Invalid stock symbol or no data available"}), 400

        # Format data for frontend
        data = [{"date": str(index.date()), "price": row["Close"]} for index, row in hist.iterrows()]

        put_snapshot("price", data, ticker=stock)
        db.session.commit()
        return jsonify(data)
    except Exception as e:
        db.session.rollback()
        # Fall back to stale data rather than breaking the chart entirely.
        stale, _ = get_snapshot("price", ticker=stock, max_age_seconds=30 * 24 * 3600)
        if stale is not None:
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

    print(f"✅ Data for {stock} stored successfully in key-value format.")

    

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
@app.cli.command("init-db")
def init_db_command():
    """
    Create any missing tables (idempotent).

    Under gunicorn the module is imported rather than executed, so the
    __main__ block below never runs. Production deploys call this instead:
        flask --app app init-db
    """
    db.create_all()
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
    # Bind configuration comes from the environment so the same entrypoint works
    # locally and on a host that injects PORT.
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")), debug=DEBUG)