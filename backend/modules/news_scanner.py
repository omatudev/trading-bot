"""
News Scanner — Fetches news and feeds them to the LLM Analyst.
Uses Alpaca News API (Benzinga) as the primary source.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from config import settings

logger = logging.getLogger("trading_bot.scanner")


class NewsScanner:
    """
    Fetches news for watchlist tickers and runs LLM analysis.
    Produces structured signals for the rules engine.
    """

    def __init__(self, llm_analyst: Any, alpaca_client: Any = None) -> None:
        self.llm = llm_analyst
        self.alpaca = alpaca_client
        self._latest_signals: list[dict[str, Any]] = []

    async def scan_all_tickers(self) -> list[dict[str, Any]]:
        """
        Scan all tickers in the watchlist:
        1. Fetch news from Alpaca News API
        2. Get current price data
        3. Check if there's an open position
        4. Pass everything to LLM for analysis
        5. Return list of signals
        """
        from database.models import get_session
        from modules.ticker_profiler import TickerProfiler

        signals = []

        async with get_session() as session:
            from database.models import TickerProfile
            from sqlalchemy import select

            result = await session.execute(select(TickerProfile))
            profiles = result.scalars().all()

        if not profiles:
            logger.info("No tickers in watchlist — nothing to scan")
            return []

        for profile in profiles:
            ticker = profile.ticker
            try:
                signal = await self.analyze_ticker(ticker)
                signals.append(signal)
            except Exception as e:
                logger.error("Failed to analyze %s: %s", ticker, e)
                signals.append({
                    "ticker": ticker,
                    "signal": "HOLD",
                    "confidence": 0.0,
                    "reasoning": f"Analysis failed: {e}",
                    "error": True,
                })

        self._latest_signals = signals
        await self._save_signals(signals)

        return signals

    async def analyze_ticker(self, ticker: str) -> dict[str, Any]:
        """
        Full analysis pipeline for a single ticker:
        1. Fetch recent news
        2. Get price snapshot
        3. Check current position
        4. Run LLM analysis
        """
        # Use shared client or create one as fallback
        if self.alpaca is None:
            from core.alpaca_client import AlpacaClient
            self.alpaca = AlpacaClient()

        alpaca = self.alpaca

        # 1. Fetch news
        news = await self._fetch_news(ticker)

        # 2. Get price data
        snapshot = await alpaca.get_snapshot(ticker)
        price_data = {}
        if snapshot:
            price_data = {
                "current_price": snapshot.get("latest_trade_price"),
                "bid": snapshot.get("bid"),
                "ask": snapshot.get("ask"),
                "daily_bar": snapshot.get("daily_bar"),
                "prev_daily_bar": snapshot.get("prev_daily_bar"),
            }

            # Calculate gap percentage
            if snapshot.get("daily_bar") and snapshot.get("prev_daily_bar"):
                today_open = snapshot["daily_bar"]["open"]
                prev_close = snapshot["prev_daily_bar"]["close"]
                if prev_close > 0:
                    price_data["gap_pct"] = ((today_open - prev_close) / prev_close) * 100

        # 3. Check current position
        position = await alpaca.get_position(ticker)

        # 4. Run LLM analysis
        signal = await self.llm.analyze_ticker(
            ticker=ticker,
            news=news,
            price_data=price_data,
            position=position,
        )

        return signal

    async def get_recent_signals(
        self, session: Any, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get the most recent signals from the database."""
        from database.models import Signal
        from sqlalchemy import select

        result = await session.execute(
            select(Signal).order_by(Signal.created_at.desc()).limit(limit)
        )
        signals = result.scalars().all()

        return [
            {
                "id": s.id,
                "ticker": s.ticker,
                "signal": s.signal,
                "confidence": s.confidence,
                "reasoning": s.reasoning,
                "catalysts": s.catalysts,
                "analysis_window": s.analysis_window,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _fetch_news(self, ticker: str) -> list[dict[str, Any]]:
        """
        Fetch recent news for a ticker from Alpaca News API.
        Falls back to empty list if API fails.
        """
        try:
            from alpaca.data.historical.news import NewsClient
            from alpaca.data.requests import NewsRequest

            news_client = NewsClient(
                api_key=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret_key,
            )

            request = NewsRequest(
                symbols=ticker,
                start=datetime.now() - timedelta(days=3),
                end=datetime.now(),
                limit=15,
            )

            news_set = news_client.get_news(request)
            articles = []

            for article in news_set.news:
                articles.append({
                    "headline": article.headline,
                    "summary": article.summary or "",
                    "source": article.source or "unknown",
                    "url": article.url or "",
                    "created_at": str(article.created_at) if article.created_at else "",
                    "symbols": [s for s in (article.symbols or [])],
                })

            logger.info("Fetched %d news articles for %s", len(articles), ticker)
            return articles

        except Exception as e:
            logger.error("Failed to fetch news for %s: %s", ticker, e)
            return []

    async def _save_signals(self, signals: list[dict[str, Any]]) -> None:
        """Persist signals to database."""
        try:
            from database.models import get_session, Signal
            import json

            async with get_session() as session:
                for sig in signals:
                    db_signal = Signal(
                        ticker=sig.get("ticker", ""),
                        signal=sig.get("signal", "HOLD"),
                        confidence=sig.get("confidence", 0.0),
                        reasoning=sig.get("reasoning", ""),
                        catalysts=json.dumps(sig.get("catalysts", [])),
                        analysis_window=sig.get("analysis_window", "manual"),
                        raw_response=sig.get("raw_response", ""),
                    )
                    session.add(db_signal)
                await session.commit()
        except Exception as e:
            logger.error("Failed to save signals: %s", e)
