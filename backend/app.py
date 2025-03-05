from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask_cors import CORS
import os
from dotenv import load_dotenv
import yfinance as yf
import json
import csv
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
import bcrypt
import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm.attributes import flag_modified
import time
import requests
from bs4 import BeautifulSoup
from textblob import TextBlob

app = Flask(__name__)
app.config["DEBUG"] = True  # Enables hot reloading
load_dotenv()
# path and env variable load
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Restrict CORS to only allow requests from the frontend
CORS(app, resources={r"/*": {"origins": FRONTEND_URL}}, supports_credentials=True)

# ------------------------------------------------------- Configure PostgreSQL database URI -------------------------------------------------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError("DATABASE_URL is not set or loaded correctly.")

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = "user_data"
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), unique=True, nullable=False)

class Holdings(db.Model):
    __tablename__ = "user_holdings"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=False, nullable=False)
    ticker = db.Column(db.String(120), unique=False, nullable=False)
    avg_price = db.Column(db.Numeric(precision=10, scale=2), unique=False, nullable=False)
    num_shares = db.Column(db.Integer, unique=False, nullable=False)
    value = db.Column(db.Numeric(precision=10, scale=2), unique=False, nullable=False)
    pinned = db.Column(db.Boolean, unique=False, nullable=False, default=False)

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

    user1 = User(email=data['email'].lower(), phone=data['phone'], password=hashed_password)
    
    try:
        db.session.add(user1)  
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
            return jsonify({"message": "Successful login"}), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------ trading routes -------------------------------------------------------------------------------

# gets a specific stock's data
@app.route('/fetch-stock-data', methods=['POST'])
def fetch_specific_stock_data():
    request_data = request.get_json()
    print("Received request:", request_data)

    if "ticker" not in request_data:
        return jsonify({"error": "Missing 'ticker' in request"}), 400

    stock = yf.Ticker(request_data["ticker"])

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
    storeDataInCSV(financials_dict, additional_data, request_data['ticker'])

    return jsonify({
        "financials": financials_dict,
        "additional_data": additional_data
    }), 200

# use this route to fetch 30 recommendations of stock to buyimport time
@app.route('/fetch-recs', methods=['POST'])
def fetchRecommendations():  
    rec_arr = {}  # Stores calculated buy/hold/sell values
    stock_rec = {}  # Stores final stock recommendations
    request_data = request.get_json() 
    email_in = request_data['email'].lower() # Get the email
    
    # Add pinned stocks to the list
    pinnedStocks = fetchPinnedStocks(email_in)
    combined_recs = sp500_tickers + pinnedStocks
    num_of_pins = len(pinnedStocks)
    
    remove_duplicates = set(combined_recs)
    unique_list_recs = list(remove_duplicates)
    
    for stock in unique_list_recs:
        ticker = yf.Ticker(stock)
        
        # Add a small delay to prevent API rate limiting
        time.sleep(0.5)  # Pause for 0.5 sec before fetching next stock

        stock_consideration = ticker.get_recommendations()

        # Ensure data exists and is not empty
        if stock_consideration is None or stock_consideration.empty:
            print(f"Skipping {stock}: No recommendation data available.")
            continue

        # Check if required columns exist before accessing them
        required_columns = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
        missing_columns = [col for col in required_columns if col not in stock_consideration.columns]

        if missing_columns:
            print(f"Skipping {stock}: Missing columns {missing_columns}")
            continue  # Skip this stock if required columns are missing

        # Compute sum of recommendations
        stock_consideration['sum_col'] = (
            stock_consideration['strongBuy'].fillna(0) + 
            stock_consideration['buy'].fillna(0) + 
            stock_consideration['hold'].fillna(0) + 
            stock_consideration['sell'].fillna(0) + 
            stock_consideration['strongSell'].fillna(0)
        )

        # Select latest recommendation row
        latest_rec = stock_consideration.iloc[0]
        sumVal = latest_rec.get('sum_col', 1)  # Avoid division by zero

        # Calculate buy, hold, sell evaluations
        rec_arr = {
            'buy': (latest_rec.get('strongBuy', 0) + latest_rec.get('buy', 0)) / sumVal,
            'hold': latest_rec.get('hold', 0) / sumVal,
            'sell': (latest_rec.get('strongSell', 0) + latest_rec.get('sell', 0)) / sumVal
        }

        # Make decision based on highest rating
        decision = max(rec_arr, key=rec_arr.get)

        # Store structured data
        stock_rec[stock] = {
            "rating": decision,
            "indicator": rec_arr[decision]
        }   

    stock_recommendations_to_send = {}  # Dictionary of recommendations to send 
    for _ in range(30+num_of_pins):
        if not stock_rec:  # Ensure stock_rec is not empty
            break
        max_stock = max(stock_rec, key=lambda x: stock_rec[x]["indicator"])
        stock_recommendations_to_send[max_stock] = stock_rec.pop(max_stock)

    # Early return if no stock recommendations were found
    if not stock_rec:
        return jsonify({"message": "Could not retrieve stock recommendations at this moment"}), 400

    return jsonify(stock_recommendations_to_send), 200

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
def getRiskAnalysis():
    request_data = request.get_json()
    print("Received request in risk anal:", request_data) # AMZN
    risk_analysis_to_send = {}
    
    if not isinstance(request_data, dict) or 'stock' not in request_data:
        return jsonify({"error": "Invalid request format. Expected {'stock': 'TICKER'}"}), 400
    
    stock = request_data['stock']
    ticker = yf.Ticker(stock)
    #fetch the data from 2020-01-01 to present day
    today = date.today()
    data = yf.download(stock, start="2020-01-01", end=today) #get the data from 2020 start to present 
    
    if data.empty:
        return jsonify({"error": "Invalid stock ticker or no data available for the given period"}), 400

    if 'Close' in data.columns:
        data['Returns'] = data['Close'].pct_change() #"By what percentage did the stock price change compared to the previous day?"

        # calculate voltaility by averaging the daily percent change in closing price
        volatility = data['Returns'].std() * (252**0.5)  # Annualized volatility
        risk_analysis_to_send['volatility'] = volatility 
        
        # get important ratios
        info = ticker.info
        debt_to_equity = info.get('debtToEquity', "") # 61.175 - AMZN
        current_ratio = info.get('currentRatio', "")# 1.089 - AMZN
        quick_ratio = info.get('quickRatio', "") #0.827 - AMZN
        latest_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        #send to frontend
        risk_analysis_to_send['debtToEquity'] = debt_to_equity 
        risk_analysis_to_send['currentRatio'] = current_ratio 
        risk_analysis_to_send['quickRatio'] = quick_ratio 
        risk_analysis_to_send['latest_price'] = latest_price
        
    # print(risk_analysis_to_send)
    return jsonify(risk_analysis_to_send), 200

# -------------------------------------------------------- Holdings route ------------------------------------------------------------------------------------------------------------

#use this route to update the user's holdings
@app.route('/update-holdings', methods=['POST'])
def updateHoldings():
    """
    This route updates a user's holdings:
      - Buying new shares (shares > 0)
      - Selling existing shares (shares < 0)
      - Creating a completely new holding (with nonzero shares)
      {
        "email": "rishabk2004@gmail.com",
        "holdingsUpdate": {
            "ticker": "ICE",
            "price": "85.5",
            "num_shares": 10
        }
        }
    """
    request_data = request.get_json()

    email_in = request_data.get("email", "").lower()
    holdings_data = request_data.get("holdingsUpdate", {})

    ticker_in = holdings_data.get("ticker", "").upper()
    price = float(holdings_data.get("price", 0))
    shares = int(holdings_data.get("num_shares", 0))

    # shares: 5, price: 173.84, ticker_in: ICE, email_in: rishabk2004@gmail.com

    print(f'shares: {shares}, price: {price}, ticker_in: {ticker_in}, email_in: {email_in}')

    # Basic validation
    if not email_in or not ticker_in or price is None or shares is None:
        return jsonify({"error": "Email, ticker, price, and num_shares are required"}), 400

    try:
        existing_holding = Holdings.query.filter_by(email=email_in, ticker=ticker_in).first()
        if existing_holding:
            # ============== SELL (shares < 0) ============== 
            if shares < 0:
                abs_shares = abs(shares)
                if existing_holding.num_shares < abs_shares:
                    return jsonify({"error": "Not enough shares to sell"}), 400

                existing_holding.num_shares -= abs_shares
                if existing_holding.num_shares == 0:
                    # All sold, remove holding
                    db.session.delete(existing_holding)
                else:
                    existing_holding.value = float(existing_holding.num_shares * existing_holding.avg_price)
                    # Mark columns as modified for SQLAlchemy
                    flag_modified(existing_holding, "num_shares")
                    flag_modified(existing_holding, "value")

                db.session.commit()
                return jsonify({
                    "message": "Shares sold successfully",
                    "data": {
                        "ticker":existing_holding.ticker
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
def pinStock():
    request_data = request.get_json()
    email = request_data['email'].lower()
    ticker = request_data['query'].upper() # get the queried ticker and user email 
    
    # Early return to handle incomplete request
    if email == None or ticker == None:
        return jsonify({"message": "invalid credentials"}), 400
    
    # check if an holding already exists
    existing_holding = Holdings.query.filter_by(email=email, ticker=ticker).first()
    if existing_holding:
        return jsonify({"message": "holding exists already, cant pin it again"}), 401
    
    new_pinned_holding = Holdings(email=email, ticker=ticker, avg_price=0.0, num_shares=0, value=0.0, pinned=True)
    db.session.add(new_pinned_holding)
    db.session.commit()
    return jsonify({
                "message": "New pinned stock added successfully",
                "data": ticker  # or [ticker_in], if your front end expects an array
            }), 200
    
# use this route to get the pinned stocks
@app.route('/fetch-pins', methods=['GET'])
def fetchUserPins():
    email = request.args.get('userEmail').lower()    
    holdings = Holdings.query.filter_by(email=email).all()
    
    pinned_list = [h.ticker for h in holdings if h.pinned == True]
    # print(pinned_list) # ['ASTS', 'ABT', 'BDX', 'AVGO', 'NVDA', 'AMZN', 'TSLA']
    return pinned_list
#return this array {stock :stock.ticker, pinned: stock.pinned}
    
# gets the user's current stock holdings
@app.route('/get-holdings', methods=['GET'])
def get_holdings():
    email = request.args.get('userEmail').lower()
    if not email:
        return jsonify({"error": "Missing email parameter"}), 400
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
def remove_pin():
    query = request.args.get('query').upper()
    email = request.args.get('email').lower()

    # Early return in case of incorrect credentials
    if not email or not query:
        return jsonify({"error": "Missing email or ticker parameter"}), 400

    # Find the holding
    # print('this is the query to be removed: ',query)
    holding = Holdings.query.filter_by(email=email, ticker=query).first()

    # Ensure holding exists before checking attributes
    if holding:
        if holding.avg_price == 0.0:  
            db.session.delete(holding)
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
if __name__ == "__main__":
    app.run(debug=True)