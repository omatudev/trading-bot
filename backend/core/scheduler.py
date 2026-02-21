"""
Trading Scheduler — Manages the daily trading cycle.
Jobs: 9:20am pre-market, 10:00am mid-morning, 3:30pm pre-close.
All times are US/Eastern (NYSE timezone).
"""

import logging
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

logger = logging.getLogger("trading_bot.scheduler")

ET = pytz.timezone("US/Eastern")


class TradingScheduler:
    """
    Manages the three daily analysis windows and ticker profile recalculation.
    """

    def __init__(
        self,
        alpaca_client: Any,
        llm_analyst: Any,
        rules_engine: Any,
        ticker_profiler: Any,
        news_scanner: Any,
        position_manager: Any,
        ws_manager: Any,
    ) -> None:
        self.alpaca = alpaca_client
        self.llm = llm_analyst
        self.rules = rules_engine
        self.profiler = ticker_profiler
        self.scanner = news_scanner
        self.positions = position_manager
        self.ws = ws_manager

        self.scheduler = AsyncIOScheduler(timezone=ET)
        self._setup_jobs()

    def _setup_jobs(self) -> None:
        """Configure all scheduled jobs."""

        # 9:20am ET — Pre-market analysis
        self.scheduler.add_job(
            self._pre_market_analysis,
            CronTrigger(hour=9, minute=20, day_of_week="mon-fri", timezone=ET),
            id="pre_market",
            name="Pre-Market Analysis (9:20am)",
            misfire_grace_time=300,
        )

        # 9:30am ET — Market open actions
        self.scheduler.add_job(
            self._market_open_actions,
            CronTrigger(hour=9, minute=30, day_of_week="mon-fri", timezone=ET),
            id="market_open",
            name="Market Open Actions (9:30am)",
            misfire_grace_time=60,
        )

        # 10:00am ET — Mid-morning scan
        self.scheduler.add_job(
            self._mid_morning_scan,
            CronTrigger(hour=10, minute=0, day_of_week="mon-fri", timezone=ET),
            id="mid_morning",
            name="Mid-Morning Scan (10:00am)",
            misfire_grace_time=300,
        )

        # 3:30pm ET — Pre-close analysis
        self.scheduler.add_job(
            self._pre_close_analysis,
            CronTrigger(hour=15, minute=30, day_of_week="mon-fri", timezone=ET),
            id="pre_close",
            name="Pre-Close Analysis (3:30pm)",
            misfire_grace_time=300,
        )

        # Daily: check for ticker profile recalculations (8:00am)
        self.scheduler.add_job(
            self._recalculate_profiles,
            CronTrigger(hour=8, minute=0, day_of_week="mon-fri", timezone=ET),
            id="profile_recalc",
            name="Ticker Profile Recalculation (8:00am)",
            misfire_grace_time=600,
        )

        # Every 30 seconds: check take profit / loss rules on open positions
        self.scheduler.add_job(
            self._check_position_rules,
            "interval",
            seconds=30,
            id="position_rules",
            name="Position Rules Check",
            misfire_grace_time=10,
        )

        # Equity snapshots: 9:30am (open), 12:00pm (mid), 4:00pm (close)
        for hour, minute, label in [(9, 30, "open"), (12, 0, "mid"), (16, 0, "close")]:
            self.scheduler.add_job(
                self._take_equity_snapshot,
                CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone=ET),
                id=f"equity_snapshot_{label}",
                name=f"Equity Snapshot ({label})",
                misfire_grace_time=300,
            )

        logger.info("Scheduled jobs configured: %d total", len(self.scheduler.get_jobs()))

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    # ------------------------------------------------------------------
    # Job implementations
    # ------------------------------------------------------------------
    async def _pre_market_analysis(self) -> None:
        """
        9:20am — Research news, catalysts, sentiment for each ticker.
        Produces BUY/SELL/HOLD signals that guide opening actions.
        """
        logger.info("═══ PRE-MARKET ANALYSIS (9:20am) ═══")

        try:
            signals = await self.scanner.scan_all_tickers()

            # Store BUY/SELL signals for execution at 9:30am
            self.positions.store_pending_signals(signals)

            await self.ws.broadcast({
                "type": "analysis_complete",
                "window": "pre_market",
                "signals": signals,
                "timestamp": datetime.now(ET).isoformat(),
            })

            logger.info("Pre-market analysis complete: %d signals generated", len(signals))

        except Exception as e:
            logger.error("Pre-market analysis failed: %s", e)

    async def _market_open_actions(self) -> None:
        """
        9:30am — Execute opening actions based on pre-market signals.
        Check for extraordinary gaps and apply sell rules.
        """
        logger.info("═══ MARKET OPEN ACTIONS (9:30am) ═══")

        try:
            await self.positions.check_extraordinary_gaps()
            await self.positions.execute_pending_signals()

            logger.info("Market open actions completed")

        except Exception as e:
            logger.error("Market open actions failed: %s", e)

    async def _mid_morning_scan(self) -> None:
        """
        10:00am — Second analysis pass. Open new positions if signals are strong.
        """
        logger.info("═══ MID-MORNING SCAN (10:00am) ═══")

        try:
            signals = await self.scanner.scan_all_tickers()

            await self.ws.broadcast({
                "type": "analysis_complete",
                "window": "mid_morning",
                "signals": signals,
                "timestamp": datetime.now(ET).isoformat(),
            })

            # Execute any BUY signals that pass the rules engine
            for signal in signals:
                if signal.get("signal") == "BUY":
                    await self.positions.process_buy_signal(signal)

            logger.info("Mid-morning scan complete")

        except Exception as e:
            logger.error("Mid-morning scan failed: %s", e)

    async def _pre_close_analysis(self) -> None:
        """
        3:30pm — Final analysis. Decide overnight holds vs closes.
        Open new positions only with strong positive signal + catalyst.
        """
        logger.info("═══ PRE-CLOSE ANALYSIS (3:30pm) ═══")

        try:
            signals = await self.scanner.scan_all_tickers()

            await self.ws.broadcast({
                "type": "analysis_complete",
                "window": "pre_close",
                "signals": signals,
                "timestamp": datetime.now(ET).isoformat(),
            })

            # Evaluate overnight holds
            await self.positions.evaluate_overnight_holds(signals)

            logger.info("Pre-close analysis complete")

        except Exception as e:
            logger.error("Pre-close analysis failed: %s", e)

    async def _check_position_rules(self) -> None:
        """
        Every 30s — Check all open positions against rules:
        - Take profit at 10%
        - Loss management (15-day rule, catalyst override)
        """
        if not await self.alpaca.is_market_open():
            return

        try:
            await self.positions.check_all_position_rules()
        except Exception as e:
            logger.error("Position rules check failed: %s", e)

    async def _recalculate_profiles(self) -> None:
        """
        8:00am daily — Check if any ticker profiles need recalculation
        (every 30 days the threshold is updated).
        """
        logger.info("Checking ticker profiles for recalculation...")

        try:
            from database.models import get_session

            async with get_session() as session:
                updated = await self.profiler.recalculate_expired_profiles(session)

            if updated:
                await self.ws.broadcast({
                    "type": "profiles_updated",
                    "tickers": updated,
                    "timestamp": datetime.now(ET).isoformat(),
                })
                logger.info("Recalculated profiles for: %s", updated)

        except Exception as e:
            logger.error("Profile recalculation failed: %s", e)

    async def _take_equity_snapshot(self) -> None:
        """
        Take a snapshot of the current portfolio equity and store it in the DB.
        """
        try:
            from database.models import EquitySnapshot, get_session

            portfolio = await self.alpaca.get_portfolio_summary()
            equity = portfolio.get("equity", 0)
            cash = portfolio.get("cash", 0)
            invested = equity - cash

            async with get_session() as session:
                snapshot = EquitySnapshot(
                    timestamp=datetime.now(ET),
                    equity=equity,
                    cash=cash,
                    invested=invested,
                )
                session.add(snapshot)
                await session.commit()

            logger.info("Equity snapshot saved: $%.2f", equity)

        except Exception as e:
            logger.error("Equity snapshot failed: %s", e)
