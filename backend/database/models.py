"""
Database Models — SQLAlchemy async models for SQLite.
Stores ticker profiles, signals, and trade history.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class TickerProfile(Base):
    """
    Stores the historical gap-up analysis and extraordinary threshold for each ticker.
    Recalculated every 30 days.
    """

    __tablename__ = "ticker_profiles"

    ticker = Column(String(10), primary_key=True, index=True)
    analysis_date = Column(DateTime, default=datetime.now)
    analysis_period_months = Column(Integer, default=4)
    days_analyzed = Column(Integer, default=0)
    days_gap_up = Column(Integer, default=0)
    gap_up_frequency_pct = Column(Float, default=0.0)
    gap_up_avg_pct = Column(Float, default=0.0)
    gap_up_max_pct = Column(Float, default=0.0)
    gap_up_p75_pct = Column(Float, default=0.0)
    threshold_extraordinary_pct = Column(Float, default=0.0)
    next_recalc_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return (
            f"<TickerProfile {self.ticker} "
            f"threshold={self.threshold_extraordinary_pct:.2f}%>"
        )


class Signal(Base):
    """
    Stores LLM-generated trading signals for audit and display.
    """

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), index=True, nullable=False)
    signal = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    confidence = Column(Float, default=0.0)
    reasoning = Column(Text, default="")
    catalysts = Column(Text, default="[]")  # JSON array
    catalyst_type = Column(String(20), default="neutral")
    sentiment_score = Column(Float, default=0.0)
    risk_level = Column(String(10), default="medium")
    analysis_window = Column(String(20), default="manual")  # pre_market, mid_morning, pre_close, manual
    raw_response = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<Signal {self.ticker} {self.signal} ({self.confidence:.2f})>"


class TradeLog(Base):
    """
    Logs all executed trades for audit.
    """

    __tablename__ = "trade_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), index=True, nullable=False)
    action = Column(String(30), nullable=False)  # buy, sell, take_profit, extraordinary_gap, etc.
    side = Column(String(4), nullable=False)  # BUY, SELL
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    pnl_usd = Column(Float, nullable=True)
    order_id = Column(String(50), nullable=True)
    reason = Column(Text, default="")
    signal_id = Column(Integer, nullable=True)  # FK to Signal that triggered this
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<TradeLog {self.ticker} {self.action} {self.side} x{self.qty}>"


class PositionTracker(Base):
    """
    Tracks when positions were opened (for the 15-day rule).
    """

    __tablename__ = "position_tracker"

    ticker = Column(String(10), primary_key=True, index=True)
    opened_at = Column(DateTime, nullable=False, default=datetime.now)
    opened_price = Column(Float, nullable=True)
    opened_qty = Column(Float, nullable=True)
    signal_id = Column(Integer, nullable=True)
    notes = Column(Text, default="")

    def __repr__(self) -> str:
        return f"<PositionTracker {self.ticker} opened={self.opened_at}>"


class EquitySnapshot(Base):
    """
    Periodic snapshots of portfolio equity for charting.
    Taken at market open, mid-day, and close — plus on startup.
    """

    __tablename__ = "equity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False, default=0.0)
    invested = Column(Float, nullable=False, default=0.0)

    def __repr__(self) -> str:
        return f"<EquitySnapshot ${self.equity:.2f} @ {self.timestamp}>"
