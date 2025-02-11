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

app = Flask(__name__)
load_dotenv()
# path and env variable load
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Restrict CORS to only allow requests from the frontend
CORS(app, resources={r"/*": {"origins": FRONTEND_URL}}, supports_credentials=True)

# ----------------------------------------------- helper functions -------------------------------------------------------------------------------
def load_data():
    """Loads stock price data from CSV (for simplicity)"""
    return pd.read_csv(DATA_PATH, parse_dates=["Date"], index_col="Date")

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


# ----------------------------------------------- auth routes -------------------------------------------------------------------------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    return jsonify(data), 200

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    return jsonify(data), 200

# ------------------------------------------------ trading routes -------------------------------------------------------------------------------

# gets the user's current stock holdings
@app.route('/get-holdings', methods=['POST'])
def get_holdings():
    return jsonify({"holdings": "AAPL"}), 200

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
    }

    
    # store this data in csv for better retrieval
    storeDataInCSV(financials_dict, additional_data, request_data['ticker'])

    return jsonify({
        "financials": financials_dict,
        "additional_data": additional_data
    }), 200

# use this route to fetch data 
@app.route('/fetch-recs', methods=['POST'])
def fetchRecommendations():  
    rec_arr = {}  # Stores calculated buy/hold/sell values
    stock_rec = {}  # Stores final stock recommendations

    for stock in sp500_tickers:
        ticker = yf.Ticker(stock)
        # print(ticker.eps_trend)
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

    stock_recommendations_to_send = {}
    for _ in range(30):
        if not stock_rec:  # Ensure stock_rec is not empty
            break
        max_stock = max(stock_rec, key=lambda x: stock_rec[x]["indicator"])
        stock_recommendations_to_send[max_stock] = stock_rec.pop(max_stock)
    
    # print(stock_recommendations_to_send)
    # Early return if no stock recommendations were found
    if not stock_rec:
        return jsonify({"message": "Could not retrieve stock recommendations at this moment"}), 400

    return jsonify(stock_recommendations_to_send), 200

# route to get the risk analysis for a stock
@app.route('/fetch-risk-anal', methods=['POST'])
def getRiskAnalysis():
    request_data = request.get_json()
    print("Received request in risk anal:", request_data) # AMZN
    risk_analysis_to_send = {}
    
    if not isinstance(request_data, dict) or 'stock' not in request_data:
        return jsonify({"error": "Invalid request format. Expected {'stock': 'TICKER'}"}), 400
    
    stock = request_data['stock']
    #fetch the data 
    today = date.today()
    data = yf.download(stock, start="2020-01-01", end=today) #get the data from 2020 start to present 
   
    print('data:', data.columns) # to access data[('Close', 'AMZN')]
    
    if data.empty:
        return jsonify({"error": "Invalid stock ticker or no data available for the given period"}), 400

    if 'Close' in data.columns:
        data['Returns'] = data['Close'].pct_change() #"By what percentage did the stock price change compared to the previous day?"
        print('returns: ',data['Returns'])
        print('Close:', data['Close']) # gets the closing price on each day 1284 rows for 'AMZN'
        volatility = data['Returns'].std() * (252**0.5)  # Annualized volatility
        # how to interpret volatility:
        # AMZN = 0.357 === 35.7% ----> so every year the stock will go 35.7% up or down,
        # voltaltility of (<.15 == stable), (15-30% == moderate risk), (30-50% == high risk), (>50% == extreme risk)
        print('volatility: ', volatility)
        
        risk_analysis_to_send['volatility'] = volatility 
    
    return jsonify(risk_analysis_to_send), 200
    



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