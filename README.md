# Trading Bot — Automated Swing Trading System

LLM-powered market analysis + deterministic execution rules + Alpaca API.

## Architecture

```
[Tú: selección manual de tickers]
         ↓
    Watchlist (DB)
         ↓
┌─────────────────────────────────────┐
│  MOTOR DE ANÁLISIS (Claude + APIs)  │
│                                     │
│  9:20am — research pre-apertura     │
│  10:00am — scan mid-morning         │
│  3:30pm — scan pre-cierre           │
│                                     │
│  Inputs: noticias Benzinga, precios │
│  Output: BUY / SELL / HOLD + razón  │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  MOTOR DE REGLAS (código duro)      │
│                                     │
│  Take profit 10% → sell 100%        │
│  Gap extraordinario → sell 60%      │
│  Trailing stop en el resto          │
│  15 días en rojo → esperar +0.5%    │
│  Catalizador negativo → override    │
└─────────────────────────────────────┘
         ↓
    Alpaca API → ejecución
```

## Stack

- **Backend**: Python 3.12 + FastAPI + SQLite
- **Frontend**: Vite + React + TypeScript + Tailwind + shadcn/ui
- **LLM**: Claude API (Anthropic)
- **Broker**: Alpaca (paper trading → live)
- **Data**: Alpaca Market Data + News API (Benzinga)

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 3. Docker (optional)

```bash
docker-compose up
```

## Trading Rules (Rulebook v1.0)

| Rule              | Description                                               |
| ----------------- | --------------------------------------------------------- |
| Take Profit       | Sell 100% at +10%, no exceptions                          |
| Extraordinary Gap | Sell 60% if gap > threshold, trail remaining 40%          |
| Loss Management   | Never close in red unless new confirmed negative catalyst |
| 15-Day Rule       | After 15 days in red, wait for +0.5% and sell             |
| Entry Validation  | Must have confirmed catalyst within 1-2 months            |
| Sentiment Only    | Do NOT buy on pure sentiment without catalyst             |
| Overnight         | Hold only if 3:30pm analysis is positive with catalyst    |
| Profile Recalc    | Recalculate ticker thresholds every 30 days               |

## Configuration

All trading parameters are configurable via `.env`:

```env
TAKE_PROFIT_PCT=10.0
MAX_POSITION_DAYS_RED=15
MIN_PROFIT_TO_EXIT_RED=0.5
EXTRAORDINARY_GAP_SELL_PCT=60.0
TICKER_PROFILE_RECALC_DAYS=30
TICKER_PROFILE_MONTHS=4
THRESHOLD_CHANGE_ALERT_PCT=30.0
```
