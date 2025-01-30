from flask import Flask, jsonify, request
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask_cors import CORS
import os
from dotenv import load_dotenv

app = Flask(__name__)

# path and env variable load
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
DATA_PATH = "data/stock_prices.csv"

# Restrict CORS to only allow requests from the frontend
CORS(app, resources={r"/*": {"origins": FRONTEND_URL}})

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


# ----------------------------------------------- routes -------------------------------------------------------------------------------

@app.route('/get-holdings', methods=['POST'])
def get_holdings():
    return jsonify({"holdings": "AAPL"}), 200

@app.route("/signals", methods=["GET"])
def get_signals():
    df = load_data()
    df = calculate_moving_averages(df)
    signals = generate_trading_signals(df)

    return jsonify(signals.to_dict(orient="records"))

if __name__ == "__main__":
    app.run(debug=True)
