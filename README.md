
# SignalScout 📈

SignalScout is a full-stack financial analytics platform that enables users to explore, track, and analyze stock market signals through a clean and interactive interface. It combines real-time data scraping, financial charting, and sentiment analysis to help users make informed investment decisions.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Tech Stack](#tech-stack)
5. [Installation](#installation)
6. [Project Structure](#project-structure)
7. [Environment Variables](#environment-variables)
8. [License](#license)

---

## Overview

SignalScout allows users to input stock tickers and receive a holistic view of their performance, enriched by:

- Real-time financial charts
- Sentiment analysis from news scraping
- User-based account management and persistence
- Financial data retrieval using yFinance

---

## Features

- 📊 **Interactive Stock Charts** (candlesticks, volume, indicators)
- 📰 **News Sentiment Analysis** using web scraping + TextBlob
- 🔐 **User Authentication** (register/login with hashed passwords)
- 🧠 **Signal Detection** for buy/sell hints using basic indicators
- 🔁 **Daily Data Syncing** from external APIs

---

## Architecture

```
SignalScout/
├── backend/      # Flask API service with PostgreSQL integration
├── frontend/     # React + Vite frontend UI
├── guide.txt     # User and developer instructions
├── requirements.txt
└── README.md     # Project overview and documentation
```

---

## Tech Stack

### 🔧 Backend

- **Language:** Python
- **Framework:** Flask
- **Database:** PostgreSQL via SQLAlchemy
- **Data & Tools:** yFinance, BeautifulSoup, TextBlob, dotenv, bcrypt
- **Security:** JWT tokens, password hashing, CORS restrictions

### 🎨 Frontend

- **Framework:** React with Vite
- **Language:** TypeScript
- **Styling:** CSS, custom components
- **Charts:** `react-financial-charts`, `recharts`
- **Routing:** React Router DOM
- **Data Fetching:** Axios

---

## Installation

### 🚀 Frontend

```bash
cd frontend
npm install
npm run dev
```

Visit: `http://localhost:5173`

### 🔧 Backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt

# Ensure Postgres is running and DATABASE_URL is set in backend/.env
python app.py   # or: flask run --debug

```

Default API: `http://localhost:5000`

---
# SignalScout 📈

SignalScout is a full-stack financial analytics platform that lets users explore, track, and analyze stock market signals through a clean, interactive UI. It combines Yahoo Finance data ingestion (via `yfinance`), simple risk analytics, analyst-consensus–based recommendations, and portfolio tracking.

> **Status snapshot**  
> ✅ Working now: user auth (bcrypt), holdings tracking, analyst-consensus recommendations, risk metrics (volatility + ratios), price chart, latest news links  
> ⚙️ In code but not fully wired to UI yet: 20/50-day MA utilities  
> 🧪 Future: sentiment scoring (TextBlob polarity), JWT-based auth, caching, Docker

---

## Table of Contents

1. [Overview](#overview)  
2. [Features](#features)  
3. [How the Analytics Work](#how-the-analytics-work)  
4. [Architecture](#architecture)  
5. [Tech Stack](#tech-stack)  
6. [Installation](#installation)  
7. [Database & Models](#database--models)  
8. [API Reference](#api-reference)  
9. [Project Structure](#project-structure)  
10. [Environment Variables](#environment-variables)  
11. [Dev Tips & Troubleshooting](#dev-tips--troubleshooting)  
12. [Roadmap](#roadmap)  
13. [License](#license)

---

## Overview

SignalScout allows users to input stock tickers and receive a holistic view:

- Real-time financial charts (1y close series)
- “Risk card” with annualized volatility + key ratios
- Analyst-consensus recommendations (top list with confidence indicator)
- User account, pinned tickers, and holdings tracking
- Data retrieval with `yfinance` and news scraping (Yahoo Finance)

---

## Features

- 📊 **Interactive Stock Charts** — 1-year close price series using `recharts`
- 🧾 **Financials Snapshot** — Key line items from `yfinance.Ticker(...).financials` plus market cap, PE, dividends, OCF, latest price
- ⚠️ **Risk Analysis** — Annualized volatility + Debt/Equity, Current, Quick ratios
- 🧠 **Recommendations** — Analyst-consensus scoring from `yfinance.get_recommendations()` (see details below)
- 📌 **Pins & Portfolio** — Pin tickers to watch; track holdings, last quote, and simple ROI
- 🔐 **Auth** — Register/Login with bcrypt-hashed passwords
- 🔁 **Daily Job (optional)** — Sample cron-style script hits the recommendations endpoint

---

## How the Analytics Work

### 1) Annualized Volatility (Risk Card)
From `/fetch-risk-anal`:
- Pull daily closes from 2020-01-01 → today.
- Compute **daily returns**: `returns_t = Close_t / Close_{t-1} - 1`.
- Compute **annualized volatility**:  
  \[
  \sigma_{\text{annual}} = \text{std}(\text{daily returns}) \times \sqrt{252}
  \]
- Volatility is color-banded in the UI:
  - `< 0.15` low, `0.15–0.30` moderate, `0.30–0.50` elevated, `≥ 0.50` high
- Fetch **ratios** from `ticker.info`: `debtToEquity`, `currentRatio`, `quickRatio`. Also returns `latest_price`.

### 2) Analyst-Consensus Recommendations
From `/fetch-recs`:
- Build a candidate ticker set = curated S&P-style list **+** the user’s pinned tickers.
- For each ticker:
  - Call `ticker.get_recommendations()` (yfinance). This returns counts of `strongBuy`, `buy`, `hold`, `sell`, `strongSell` by date.
  - Take the latest row; compute totals:
    \[
    \text{sum} = \text{strongBuy} + \text{buy} + \text{hold} + \text{sell} + \text{strongSell}
    \]
  - Compute **proportions**:
    - `buy_score = (strongBuy + buy) / sum`
    - `hold_score = hold / sum`
    - `sell_score = (strongSell + sell) / sum`
  - Pick the **rating** with the max proportion; store its value as **indicator**.
- Return **Top N** (currently ~30 + pinned) by highest `indicator`.

> The backend throttles requests with `time.sleep(0.5)` per ticker to be friendlier to rate limits.

### 3) Financials Snapshot
From `/fetch-stock-data`:
- Pull `Ticker(...).financials` (wide DataFrame keyed by period), coerce to a serializable dict, and include:
  - **Additional data** (from `ticker.info` & history): `marketCap`, `trailingPE`, **sum of dividends**, `operatingCashflow`, `latest_price`.
- A CSV snapshot (`backend/stockAnalysisData.csv`) is maintained in a **key-value layout** to avoid duplicates:


### 4) Holdings & ROI
From `/get-holdings`:
- For each holding, fetch last close (`Ticker(...).history(period="1d")`), then compute:
\[
\text{ROI (\%)} = \frac{\text{last\_quote} - \text{avg\_price}}{\text{avg\_price}} \times 100
\]

> Utilities for moving averages (MA20/MA50) and crossovers exist in the backend but are not currently used for UI or recs.

---

## Architecture

```mermaid
flowchart LR
FE[Frontend (React + Vite)] -- Axios --> BE[(Flask API)]
subgraph BE_Services[Backend Services]
  BE --> YF[yfinance]
  BE --> YNEWS[Yahoo Finance News (HTML)]
  BE --> PG[(PostgreSQL)]
end

subgraph UI[Frontend Modules]
  CHART[PriceChart.jsx] --> FE
  RISK[RiskAnal.jsx] --> FE
  RECS[stock_rec.jsx] --> FE
  OVERVIEW[overView.jsx] --> FE
  HOLD[holdings.jsx] --> FE
end

CRON[daily_task.py] -->|POST /fetch-recs| BE

## License

This project is for educational and demonstration purposes.

---

📬 For demo video, check `SignalScoutFinalVideo - Made with Clipchamp.mp4` inside the repo.
