"""
Main FastAPI application — entry point for the trading bot.
Handles REST endpoints, WebSocket connections, and scheduler startup.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Set

from fastapi import Depends, FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from core.auth import (
    create_jwt,
    require_auth,
    verify_google_token,
    verify_ws_token,
)
from core.alpaca_client import AlpacaClient
from core.llm_analyst import LLMAnalyst
from core.rules_engine import RulesEngine
from core.scheduler import TradingScheduler
from database.models import init_db, get_session
from modules.ticker_profiler import TickerProfiler
from modules.news_scanner import NewsScanner
from modules.position_manager import PositionManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("trading_bot")
logger.info(f"DB URL: {settings.database_url}")

# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Manages active WebSocket connections for the dashboard."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("Dashboard client connected. Total: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.info("Dashboard client disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, data: dict) -> None:
        """Send JSON payload to all connected clients."""
        message = json.dumps(data, default=str)
        disconnected: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.active_connections.discard(conn)


ws_manager = ConnectionManager()

# ---------------------------------------------------------------------------
# Shared service instances
# ---------------------------------------------------------------------------
alpaca_client = AlpacaClient()
llm_analyst = LLMAnalyst()
rules_engine = RulesEngine(alpaca_client=alpaca_client)
ticker_profiler = TickerProfiler(alpaca_client=alpaca_client)
news_scanner = NewsScanner(llm_analyst=llm_analyst, alpaca_client=alpaca_client)
position_manager = PositionManager(
    alpaca_client=alpaca_client,
    rules_engine=rules_engine,
    llm_analyst=llm_analyst,
    ws_manager=ws_manager,
)


async def _take_initial_snapshot() -> None:
    """Take an equity snapshot on startup so the chart has data from day 1."""
    try:
        from database.models import EquitySnapshot

        portfolio = await alpaca_client.get_portfolio_summary()
        equity = portfolio.get("equity", 0)
        cash = portfolio.get("cash", 0)
        invested = equity - cash

        async with get_session() as session:
            snapshot = EquitySnapshot(
                timestamp=datetime.now(),
                equity=equity,
                cash=cash,
                invested=invested,
            )
            session.add(snapshot)
            await session.commit()

        logger.info("✅ Initial equity snapshot: $%.2f", equity)
    except Exception as e:
        logger.error("Failed to take initial snapshot: %s", e)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init DB, start scheduler, connect Alpaca."""
    logger.info("🚀 Starting Trading Bot...")

    # 1. Initialize database
    await init_db()
    logger.info("✅ Database initialized")

    # 2. Load persisted settings from DB (survives container restarts)
    await _load_settings_db()

    # 3. Load persisted position open dates
    await position_manager._load_position_dates()

    # 4. Take initial equity snapshot (so chart has data from day 1)
    await _take_initial_snapshot()

    # 5. Start the trading scheduler (9:20am, 10:00am, 3:30pm jobs)
    scheduler = TradingScheduler(
        alpaca_client=alpaca_client,
        llm_analyst=llm_analyst,
        rules_engine=rules_engine,
        ticker_profiler=ticker_profiler,
        news_scanner=news_scanner,
        position_manager=position_manager,
        ws_manager=ws_manager,
    )
    scheduler.start()
    logger.info("✅ Scheduler started")

    # 3. Start portfolio broadcast loop
    broadcast_task = asyncio.create_task(_portfolio_broadcast_loop())

    yield

    # Shutdown
    logger.info("🛑 Shutting down Trading Bot...")
    scheduler.stop()
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass


async def _portfolio_broadcast_loop() -> None:
    """Broadcast portfolio data to all connected dashboards every 5 seconds."""
    while True:
        try:
            if ws_manager.active_connections:
                portfolio = await alpaca_client.get_portfolio_summary()
                positions = await alpaca_client.get_open_positions()
                await ws_manager.broadcast({
                    "type": "portfolio_update",
                    "portfolio": portfolio,
                    "positions": positions,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            logger.error("Portfolio broadcast error: %s", e)
        await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Trading Bot API",
    description="Automated swing trading with LLM analysis + Alpaca execution",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth Endpoint (public)
# ---------------------------------------------------------------------------
class GoogleAuthRequest(BaseModel):
    token: str


@app.post("/api/auth/google")
async def google_auth(body: GoogleAuthRequest):
    """Exchange a Google id_token for a JWT."""
    payload = verify_google_token(body.token)
    email = payload.get("email", "")
    if email != settings.allowed_email:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Access denied — email not authorized",
        )
    jwt_token = create_jwt(email)
    return {
        "token": jwt_token,
        "email": email,
        "name": payload.get("name", ""),
        "picture": payload.get("picture", ""),
    }


# ---------------------------------------------------------------------------
# REST Endpoints (protected)
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/portfolio")
async def get_portfolio(_=Depends(require_auth)):
    """Get current portfolio summary."""
    portfolio = await alpaca_client.get_portfolio_summary()
    positions = await alpaca_client.get_open_positions()
    return {"portfolio": portfolio, "positions": positions}


@app.get("/api/watchlist")
async def get_watchlist(_=Depends(require_auth)):
    """Get all tickers in the watchlist with their profiles."""
    async with get_session() as session:
        profiles = await ticker_profiler.get_all_profiles(session)
    return {"watchlist": profiles}


@app.post("/api/watchlist/{ticker}")
async def add_to_watchlist(ticker: str, _=Depends(require_auth)):
    """Add a ticker to the watchlist — runs historical analysis automatically."""
    ticker = ticker.upper().strip()
    logger.info("Adding %s to watchlist...", ticker)
    async with get_session() as session:
        profile = await ticker_profiler.create_profile(ticker, session)
    return {"message": f"{ticker} added to watchlist", "profile": profile}


@app.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, _=Depends(require_auth)):
    """Remove a ticker from the watchlist."""
    ticker = ticker.upper().strip()
    async with get_session() as session:
        await ticker_profiler.delete_profile(ticker, session)
    return {"message": f"{ticker} removed from watchlist"}


@app.get("/api/signals")
async def get_signals(_=Depends(require_auth)):
    """Get the latest LLM signals."""
    async with get_session() as session:
        signals = await news_scanner.get_recent_signals(session, limit=20)
    return {"signals": signals}


@app.get("/api/settings")
async def get_settings(_=Depends(require_auth)):
    """Get current bot settings (rules + schedule)."""
    return {
        "rules": {
            "take_profit_pct": settings.take_profit_pct,
            "extraordinary_gap_sell_pct": settings.extraordinary_gap_sell_pct,
            "max_position_days_red": settings.max_position_days_red,
            "min_profit_to_exit_red": settings.min_profit_to_exit_red,
        },
        "schedule": {
            "pre_open": settings.schedule_pre_open,
            "open": settings.schedule_open,
            "mid": settings.schedule_mid,
            "pre_close": settings.schedule_pre_close,
        },
    }


@app.put("/api/settings")
async def update_settings(body: dict, _=Depends(require_auth)):
    """Update bot settings (rules + schedule) at runtime."""
    rules = body.get("rules", {})
    schedule = body.get("schedule", {})

    # Update rules in-memory
    if "take_profit_pct" in rules:
        settings.take_profit_pct = float(rules["take_profit_pct"])
    if "extraordinary_gap_sell_pct" in rules:
        settings.extraordinary_gap_sell_pct = float(rules["extraordinary_gap_sell_pct"])
    if "max_position_days_red" in rules:
        settings.max_position_days_red = int(rules["max_position_days_red"])
    if "min_profit_to_exit_red" in rules:
        settings.min_profit_to_exit_red = float(rules["min_profit_to_exit_red"])

    # Update schedule in-memory
    if "pre_open" in schedule:
        settings.schedule_pre_open = schedule["pre_open"]
    if "open" in schedule:
        settings.schedule_open = schedule["open"]
    if "mid" in schedule:
        settings.schedule_mid = schedule["mid"]
    if "pre_close" in schedule:
        settings.schedule_pre_close = schedule["pre_close"]

    # Persist to database (survives container restarts)
    await _persist_settings_db()

    logger.info("Settings updated: rules=%s, schedule=%s", rules, schedule)
    return await get_settings()


async def _persist_settings_db() -> None:
    """Save current settings to the database so they survive container restarts."""
    from database.models import BotSetting
    from sqlalchemy.dialects.postgresql import insert as pg_upsert

    settings_map = {
        "take_profit_pct": str(settings.take_profit_pct),
        "extraordinary_gap_sell_pct": str(settings.extraordinary_gap_sell_pct),
        "max_position_days_red": str(settings.max_position_days_red),
        "min_profit_to_exit_red": str(settings.min_profit_to_exit_red),
        "schedule_pre_open": settings.schedule_pre_open,
        "schedule_open": settings.schedule_open,
        "schedule_mid": settings.schedule_mid,
        "schedule_pre_close": settings.schedule_pre_close,
    }

    async with get_session() as session:
        for key, value in settings_map.items():
            stmt = pg_upsert(BotSetting).values(key=key, value=value)
            stmt = stmt.on_conflict_do_update(
                index_elements=["key"],
                set_={"value": value},
            )
            await session.execute(stmt)
        await session.commit()


async def _load_settings_db() -> None:
    """Load persisted settings from the database on startup."""
    from database.models import BotSetting
    from sqlalchemy import select

    try:
        async with get_session() as session:
            result = await session.execute(select(BotSetting))
            rows = result.scalars().all()

        if not rows:
            return

        for row in rows:
            if row.key == "take_profit_pct":
                settings.take_profit_pct = float(row.value)
            elif row.key == "extraordinary_gap_sell_pct":
                settings.extraordinary_gap_sell_pct = float(row.value)
            elif row.key == "max_position_days_red":
                settings.max_position_days_red = int(row.value)
            elif row.key == "min_profit_to_exit_red":
                settings.min_profit_to_exit_red = float(row.value)
            elif row.key == "schedule_pre_open":
                settings.schedule_pre_open = row.value
            elif row.key == "schedule_open":
                settings.schedule_open = row.value
            elif row.key == "schedule_mid":
                settings.schedule_mid = row.value
            elif row.key == "schedule_pre_close":
                settings.schedule_pre_close = row.value

        logger.info("✅ Settings loaded from database")
    except Exception as e:
        logger.warning("Could not load settings from DB (first run?): %s", e)
@app.post("/api/analyze/{ticker}")
async def manual_analysis(ticker: str, _=Depends(require_auth)):
    """Trigger a manual LLM analysis for a specific ticker."""
    ticker = ticker.upper().strip()
    signal = await news_scanner.analyze_ticker(ticker)
    # Persist signal to DB
    signal["analysis_window"] = "manual"
    await news_scanner._save_signals([signal])
    return {"signal": signal}


@app.get("/api/bars/{ticker}")
async def get_bars(ticker: str, days: int = 30, tf: str = "day", _=Depends(require_auth)):
    """Get historical bars for charting.
    
    tf options: 'min' (1-minute), '5min', '15min', 'hour', 'day'
    """
    ticker = ticker.upper().strip()
    from datetime import timedelta
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "min": TimeFrame.Minute,
        "5min": TimeFrame(5, TimeFrameUnit.Minute),
        "15min": TimeFrame(15, TimeFrameUnit.Minute),
        "hour": TimeFrame.Hour,
        "day": TimeFrame.Day,
    }
    timeframe = tf_map.get(tf, TimeFrame.Day)

    start = datetime.now() - timedelta(days=days)
    bars = await alpaca_client.get_historical_bars(
        ticker=ticker,
        timeframe=timeframe,
        start=start,
    )
    return {"ticker": ticker, "bars": bars}


@app.get("/api/portfolio/history")
async def get_portfolio_history(period: str = "1M", _=Depends(require_auth)):
    """Get portfolio equity history from our own snapshots."""
    from database.models import EquitySnapshot
    from sqlalchemy import select
    from datetime import timedelta

    # Map period to timedelta
    period_map = {
        "1D": timedelta(days=1),
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "6M": timedelta(days=180),
        "1A": timedelta(days=365),
    }
    delta = period_map.get(period)
    if delta:
        since = datetime.now() - delta
    else:
        since = datetime(2000, 1, 1)  # "all"

    async with get_session() as session:
        result = await session.execute(
            select(EquitySnapshot)
            .where(EquitySnapshot.timestamp >= since)
            .order_by(EquitySnapshot.timestamp.asc())
        )
        snapshots = result.scalars().all()

    return {
        "history": [
            {
                "timestamp": int(s.timestamp.timestamp()),
                "equity": s.equity,
                "cash": s.cash,
                "invested": s.invested,
            }
            for s in snapshots
        ]
    }


@app.get("/api/trades")
async def get_trades(_=Depends(require_auth)):
    """Get trade history."""
    from database.models import TradeLog
    from sqlalchemy import select

    async with get_session() as session:
        result = await session.execute(
            select(TradeLog).order_by(TradeLog.created_at.desc()).limit(50)
        )
        trades = result.scalars().all()
    return {
        "trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "action": t.action,
                "side": t.side,
                "qty": t.qty,
                "price": t.price,
                "pnl_pct": t.pnl_pct,
                "pnl_usd": t.pnl_usd,
                "reason": t.reason,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trades
        ]
    }


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default="")):
    """Dashboard WebSocket — requires JWT token as query param."""
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send commands later
            data = await websocket.receive_text()
            logger.debug("WS received: %s", data)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
