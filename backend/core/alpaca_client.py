"""
Alpaca Client — Wrapper around alpaca-py SDK.
Handles authentication, portfolio queries, order execution, and market data.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    TrailingStopOrderRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame

from config import settings

logger = logging.getLogger("trading_bot.alpaca")


class AlpacaClient:
    """
    Unified wrapper around Alpaca's Trading and Data APIs.
    All order logic is deterministic — the LLM never touches this directly.
    """

    def __init__(self) -> None:
        self.trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=True,  # Always paper until explicitly switched
        )
        self.data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
        logger.info("Alpaca clients initialized (paper mode)")

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------
    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Return current portfolio value, cash, and daily P&L."""
        try:
            account = await asyncio.to_thread(self.trading_client.get_account)
            return {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "daily_pnl": float(account.equity) - float(account.last_equity),
                "daily_pnl_pct": (
                    (float(account.equity) - float(account.last_equity))
                    / float(account.last_equity)
                    * 100
                    if float(account.last_equity) > 0
                    else 0.0
                ),
            }
        except Exception as e:
            logger.error("Failed to get portfolio summary: %s", e)
            return {}

    async def get_open_positions(self) -> list[dict[str, Any]]:
        """Return all open positions with current P&L."""
        try:
            positions = await asyncio.to_thread(self.trading_client.get_all_positions)
            return [
                {
                    "ticker": pos.symbol,
                    "qty": float(pos.qty),
                    "avg_entry": float(pos.avg_entry_price),
                    "current_price": float(pos.current_price),
                    "market_value": float(pos.market_value),
                    "unrealized_pnl": float(pos.unrealized_pl),
                    "unrealized_pnl_pct": float(pos.unrealized_plpc) * 100,
                    "side": str(pos.side),
                }
                for pos in positions
            ]
        except Exception as e:
            logger.error("Failed to get positions: %s", e)
            return []

    async def get_position(self, ticker: str) -> Optional[dict[str, Any]]:
        """Get a single position by ticker, or None if not held."""
        try:
            pos = await asyncio.to_thread(self.trading_client.get_open_position, ticker)
            return {
                "ticker": pos.symbol,
                "qty": float(pos.qty),
                "avg_entry": float(pos.avg_entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(pos.unrealized_pl),
                "unrealized_pnl_pct": float(pos.unrealized_plpc) * 100,
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    async def buy_market(self, ticker: str, qty: float) -> dict[str, Any]:
        """Place a market buy order."""
        try:
            order = await asyncio.to_thread(
                self.trading_client.submit_order,
                MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            )
            logger.info("BUY MARKET %s x%.2f — order %s", ticker, qty, order.id)
            return {"order_id": str(order.id), "status": str(order.status)}
        except Exception as e:
            logger.error("Buy market failed for %s: %s", ticker, e)
            return {"error": str(e)}

    async def sell_market(self, ticker: str, qty: float) -> dict[str, Any]:
        """Place a market sell order."""
        try:
            order = await asyncio.to_thread(
                self.trading_client.submit_order,
                MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
            )
            logger.info("SELL MARKET %s x%.2f — order %s", ticker, qty, order.id)
            return {"order_id": str(order.id), "status": str(order.status)}
        except Exception as e:
            logger.error("Sell market failed for %s: %s", ticker, e)
            return {"error": str(e)}

    async def sell_limit(self, ticker: str, qty: float, limit_price: float) -> dict[str, Any]:
        """Place a limit sell order."""
        try:
            order = await asyncio.to_thread(
                self.trading_client.submit_order,
                LimitOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    limit_price=limit_price,
                )
            )
            logger.info(
                "SELL LIMIT %s x%.2f @ $%.2f — order %s",
                ticker, qty, limit_price, order.id,
            )
            return {"order_id": str(order.id), "status": str(order.status)}
        except Exception as e:
            logger.error("Sell limit failed for %s: %s", ticker, e)
            return {"error": str(e)}

    async def sell_trailing_stop(
        self, ticker: str, qty: float, trail_percent: float
    ) -> dict[str, Any]:
        """Place a trailing stop sell order."""
        try:
            order = await asyncio.to_thread(
                self.trading_client.submit_order,
                TrailingStopOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    trail_percent=trail_percent,
                )
            )
            logger.info(
                "SELL TRAILING STOP %s x%.2f trail %.1f%% — order %s",
                ticker, qty, trail_percent, order.id,
            )
            return {"order_id": str(order.id), "status": str(order.status)}
        except Exception as e:
            logger.error("Trailing stop failed for %s: %s", ticker, e)
            return {"error": str(e)}

    async def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        await asyncio.to_thread(self.trading_client.cancel_orders)
        logger.info("All open orders cancelled")

    async def get_recent_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent orders."""
        try:
            orders = await asyncio.to_thread(
                self.trading_client.get_orders,
                GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
            )
            return [
                {
                    "order_id": str(o.id),
                    "ticker": o.symbol,
                    "side": str(o.side),
                    "qty": float(o.qty) if o.qty else 0,
                    "filled_qty": float(o.filled_qty) if o.filled_qty else 0,
                    "status": str(o.status),
                    "created_at": str(o.created_at),
                }
                for o in orders
            ]
        except Exception as e:
            logger.error("Failed to get orders: %s", e)
            return []

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------
    async def get_historical_bars(
        self,
        ticker: str,
        timeframe: TimeFrame = TimeFrame.Day,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        months_back: int = 4,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical OHLCV bars for a ticker.
        Defaults to last `months_back` months of daily bars.
        """
        if start is None:
            start = datetime.now() - timedelta(days=months_back * 30)
        if end is None:
            end = datetime.now()

        try:
            request = StockBarsRequest(
                symbol_or_symbols=ticker,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            bars = await asyncio.to_thread(self.data_client.get_stock_bars, request)
            data = bars[ticker]
            return [
                {
                    "timestamp": str(bar.timestamp),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                }
                for bar in data
            ]
        except Exception as e:
            logger.error("Failed to get historical bars for %s: %s", ticker, e)
            return []

    async def get_latest_quote(self, ticker: str) -> Optional[dict[str, Any]]:
        """Get the latest quote for a ticker."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=ticker)
            quotes = await asyncio.to_thread(self.data_client.get_stock_latest_quote, request)
            quote = quotes[ticker]
            return {
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "bid_size": int(quote.bid_size),
                "ask_size": int(quote.ask_size),
                "timestamp": str(quote.timestamp),
            }
        except Exception as e:
            logger.error("Failed to get latest quote for %s: %s", ticker, e)
            return None

    async def get_snapshot(self, ticker: str) -> Optional[dict[str, Any]]:
        """Get a full market snapshot for a ticker (latest trade, quote, bar)."""
        try:
            request = StockSnapshotRequest(symbol_or_symbols=ticker)
            snapshots = await asyncio.to_thread(self.data_client.get_stock_snapshot, request)
            snap = snapshots[ticker]
            return {
                "latest_trade_price": float(snap.latest_trade.price) if snap.latest_trade else None,
                "latest_trade_size": int(snap.latest_trade.size) if snap.latest_trade else None,
                "bid": float(snap.latest_quote.bid_price) if snap.latest_quote else None,
                "ask": float(snap.latest_quote.ask_price) if snap.latest_quote else None,
                "daily_bar": {
                    "open": float(snap.daily_bar.open),
                    "high": float(snap.daily_bar.high),
                    "low": float(snap.daily_bar.low),
                    "close": float(snap.daily_bar.close),
                    "volume": int(snap.daily_bar.volume),
                }
                if snap.daily_bar
                else None,
                "prev_daily_bar": {
                    "open": float(snap.previous_daily_bar.open),
                    "high": float(snap.previous_daily_bar.high),
                    "low": float(snap.previous_daily_bar.low),
                    "close": float(snap.previous_daily_bar.close),
                    "volume": int(snap.previous_daily_bar.volume),
                }
                if snap.previous_daily_bar
                else None,
            }
        except Exception as e:
            logger.error("Failed to get snapshot for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Portfolio History
    # ------------------------------------------------------------------
    async def get_portfolio_history(
        self,
        period: str = "1M",
        timeframe: str = "1D",
    ) -> list[dict[str, Any]]:
        """Get historical equity values for the portfolio."""
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest

            request = GetPortfolioHistoryRequest(
                period=period,
                timeframe=timeframe,
            )
            history = await asyncio.to_thread(self.trading_client.get_portfolio_history, request)

            timestamps = history.timestamp or []
            equity = history.equity or []
            pnl = history.profit_loss or []
            pnl_pct = history.profit_loss_pct or []

            return [
                {
                    "timestamp": int(ts),
                    "equity": float(eq) if eq else 0,
                    "pnl": float(pl) if pl else 0,
                    "pnl_pct": float(pp) if pp else 0,
                }
                for ts, eq, pl, pp in zip(timestamps, equity, pnl, pnl_pct)
                if eq is not None
            ]
        except Exception as e:
            logger.error("Failed to get portfolio history: %s", e)
            return []

    # ------------------------------------------------------------------
    # Market status
    # ------------------------------------------------------------------
    async def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            clock = await asyncio.to_thread(self.trading_client.get_clock)
            return clock.is_open
        except Exception:
            return False

    async def get_market_clock(self) -> dict[str, Any]:
        """Get market clock info."""
        try:
            clock = await asyncio.to_thread(self.trading_client.get_clock)
            return {
                "is_open": clock.is_open,
                "next_open": str(clock.next_open),
                "next_close": str(clock.next_close),
            }
        except Exception as e:
            logger.error("Failed to get market clock: %s", e)
            return {}
