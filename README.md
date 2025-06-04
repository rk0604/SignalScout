
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
pip install -r requirements.txt
python app.py
```

Default API: `http://localhost:5000`

---

## Project Structure

### Backend Highlights

- `app.py`: Entry point with route handlers
- `daily_task.py`: Automated daily sync jobs for stock data
- Uses environment variables via `dotenv`
- Configured for CORS-safe frontend interaction

### Frontend Highlights

- `App.tsx`, `Home.tsx`, `Dashboard.tsx`: UI layout and routes
- `components/`: Modular charting and forms
- Hooks and context for state and navigation

---

## Environment Variables

Create `.env` files in both frontend and backend directories.

### Example for backend:

```
FRONTEND_URL=http://localhost:5173
DATABASE_URL=postgresql://username:password@localhost/dbname
SECRET_KEY=your_secret_key
```

---

## License

This project is for educational and demonstration purposes.

---

📬 For demo video, check `SignalScoutFinalVideo - Made with Clipchamp.mp4` inside the repo.
