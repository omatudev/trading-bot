"""
Position Manager — Manages open positions and executes trade actions.
Bridges the LLM signals, rules engine, and Alpaca execution.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("trading_bot.positions")


class PositionManager:
    """
    Manages open positions: checks rules, executes signals, handles gaps.
    This is the orchestration layer between analysis and execution.
    """

    def __init__(
        self,
        alpaca_client: Any,
        rules_engine: Any,
        llm_analyst: Any,
        ws_manager: Any,
    ) -> None:
        self.alpaca = alpaca_client
        self.rules = rules_engine
        self.llm = llm_analyst
        self.ws = ws_manager

        # In-memory tracking of pending signals from pre-market
        self._pending_signals: list[dict[str, Any]] = []

        # Track when positions were opened (ticker -> datetime)
        self._position_open_dates: dict[str, datetime] = {}

    # ------------------------------------------------------------------
    # Trade logging helper
    # ------------------------------------------------------------------
    async def _log_trade(
        self,
        ticker: str,
        action: str,
        side: str,
        qty: float,
        price: float | None = None,
        pnl_pct: float | None = None,
        pnl_usd: float | None = None,
        reason: str = "",
        order_id: str | None = None,
    ) -> None:
        """Persist a trade to the TradeLog table for audit."""
        try:
            from database.models import get_session, TradeLog

            async with get_session() as session:
                log = TradeLog(
                    ticker=ticker,
                    action=action,
                    side=side,
                    qty=qty,
                    price=price,
                    pnl_pct=pnl_pct,
                    pnl_usd=pnl_usd,
                    order_id=order_id,
                    reason=reason,
                )
                session.add(log)
                await session.commit()
        except Exception as e:
            logger.error("Failed to log trade for %s: %s", ticker, e)

    # ------------------------------------------------------------------
    # Position open/close tracking persistence
    # ------------------------------------------------------------------
    async def _track_position_open(
        self,
        ticker: str,
        price: float | None = None,
        qty: float | None = None,
    ) -> None:
        """Persist position open date to DB + in-memory dict."""
        self._position_open_dates[ticker] = datetime.now()
        try:
            from database.models import get_session, PositionTracker
            from sqlalchemy import select

            async with get_session() as session:
                existing = await session.execute(
                    select(PositionTracker).where(PositionTracker.ticker == ticker)
                )
                if existing.scalar_one_or_none():
                    return  # already tracked
                tracker = PositionTracker(
                    ticker=ticker,
                    opened_at=datetime.now(),
                    opened_price=price,
                    opened_qty=qty,
                )
                session.add(tracker)
                await session.commit()
        except Exception as e:
            logger.error("Failed to track position open for %s: %s", ticker, e)

    async def _track_position_close(self, ticker: str) -> None:
        """Remove position from tracker on close."""
        self._position_open_dates.pop(ticker, None)
        try:
            from database.models import get_session, PositionTracker
            from sqlalchemy import select, delete

            async with get_session() as session:
                await session.execute(
                    delete(PositionTracker).where(PositionTracker.ticker == ticker)
                )
                await session.commit()
        except Exception as e:
            logger.error("Failed to remove position tracker for %s: %s", ticker, e)

    async def _load_position_dates(self) -> None:
        """Load persisted position open dates into memory on startup."""
        try:
            from database.models import get_session, PositionTracker
            from sqlalchemy import select

            async with get_session() as session:
                result = await session.execute(select(PositionTracker))
                trackers = result.scalars().all()
                for t in trackers:
                    self._position_open_dates[t.ticker] = t.opened_at
            if self._position_open_dates:
                logger.info(
                    "Loaded %d position dates from DB", len(self._position_open_dates)
                )
        except Exception as e:
            logger.error("Failed to load position dates: %s", e)

    # ------------------------------------------------------------------
    # Extraordinary gap check (runs at market open)
    # ------------------------------------------------------------------
    async def check_extraordinary_gaps(self) -> None:
        """
        At market open (9:30am), check each open position for extraordinary gaps.
        If gap > threshold → sell 60%, trail the remaining 40%.
        """
        positions = await self.alpaca.get_open_positions()

        for pos in positions:
            ticker = pos["ticker"]

            try:
                # Get the ticker's threshold
                from database.models import get_session
                from modules.ticker_profiler import TickerProfiler

                async with get_session() as session:
                    from database.models import TickerProfile
                    from sqlalchemy import select

                    result = await session.execute(
                        select(TickerProfile).where(TickerProfile.ticker == ticker)
                    )
                    profile = result.scalar_one_or_none()

                if not profile:
                    continue

                # Get the snapshot to compute today's gap
                snapshot = await self.alpaca.get_snapshot(ticker)
                if not snapshot or not snapshot.get("daily_bar") or not snapshot.get("prev_daily_bar"):
                    continue

                today_open = snapshot["daily_bar"]["open"]
                prev_close = snapshot["prev_daily_bar"]["close"]

                if prev_close <= 0:
                    continue

                gap_pct = ((today_open - prev_close) / prev_close) * 100

                # Check against threshold
                action = self.rules.should_sell_extraordinary_gap(
                    ticker=ticker,
                    gap_up_pct=gap_pct,
                    threshold_pct=profile.threshold_extraordinary_pct,
                )

                if action["action"] == "extraordinary_gap_sell":
                    total_qty = pos["qty"]
                    sell_qty = int(total_qty * (action["sell_pct"] / 100))
                    remaining_qty = total_qty - sell_qty

                    if sell_qty > 0:
                        # Sell 60% immediately
                        result = await self.alpaca.sell_market(ticker, sell_qty)
                        await self._log_trade(
                            ticker, "extraordinary_gap_sell", "SELL", sell_qty,
                            price=today_open, reason=f"Gap {gap_pct:.2f}% > threshold {profile.threshold_extraordinary_pct:.2f}%",
                        )
                        logger.info(
                            "EXTRAORDINARY GAP SELL: %s — sold %d of %d shares (gap: %.2f%%)",
                            ticker,
                            sell_qty,
                            int(total_qty),
                            gap_pct,
                        )

                        # Place trailing stop on remaining 40%
                        if remaining_qty > 0:
                            await self.alpaca.sell_trailing_stop(
                                ticker, remaining_qty, trail_percent=2.0
                            )

                        await self.ws.broadcast({
                            "type": "trade_executed",
                            "action": "extraordinary_gap_sell",
                            "ticker": ticker,
                            "qty_sold": sell_qty,
                            "gap_pct": gap_pct,
                            "threshold_pct": profile.threshold_extraordinary_pct,
                            "timestamp": datetime.now().isoformat(),
                        })

            except Exception as e:
                logger.error("Gap check failed for %s: %s", ticker, e)

    # ------------------------------------------------------------------
    # Check all position rules (runs every 30s during market hours)
    # ------------------------------------------------------------------
    async def check_all_position_rules(self) -> None:
        """
        Check all open positions against rules engine:
        - Take profit at 10%
        - Loss management (15-day rule, catalyst override)
        """
        positions = await self.alpaca.get_open_positions()

        for pos in positions:
            ticker = pos["ticker"]

            # Rule 1: Take profit
            if self.rules.should_take_profit(pos):
                qty = pos["qty"]
                result = await self.alpaca.sell_market(ticker, qty)
                await self._log_trade(
                    ticker, "take_profit", "SELL", qty,
                    pnl_pct=pos["unrealized_pnl_pct"],
                    reason=f"Take profit at {pos['unrealized_pnl_pct']:.2f}%",
                )
                await self._track_position_close(ticker)

                logger.info(
                    "TAKE PROFIT: %s — sold all %d shares at %.2f%% gain",
                    ticker,
                    int(qty),
                    pos["unrealized_pnl_pct"],
                )

                await self.ws.broadcast({
                    "type": "trade_executed",
                    "action": "take_profit",
                    "ticker": ticker,
                    "qty_sold": qty,
                    "pnl_pct": pos["unrealized_pnl_pct"],
                    "timestamp": datetime.now().isoformat(),
                })
                continue

            # Rule 2: Loss management
            days_held = self._get_days_held(ticker)

            # Check for negative catalyst via LLM if position is in the red
            has_negative_catalyst = False
            if pos.get("unrealized_pnl_pct", 0) < 0:
                try:
                    from modules.news_scanner import NewsScanner
                    news = await NewsScanner(self.llm)._fetch_news(ticker)
                    if news:
                        override = await self.llm.analyze_sell_override(
                            ticker=ticker, news=news, position=pos
                        )
                        has_negative_catalyst = override.get(
                            "override_no_sell_rule", False
                        )
                        if has_negative_catalyst:
                            logger.warning(
                                "NEGATIVE CATALYST for %s: %s",
                                ticker,
                                override.get("negative_catalyst"),
                            )
                except Exception as e:
                    logger.error("Catalyst check failed for %s: %s", ticker, e)

            loss_action = self.rules.evaluate_loss_position(
                position=pos,
                days_held=days_held,
                has_negative_catalyst=has_negative_catalyst,
            )

            if loss_action["action"] == "exit_red_zone":
                # Position was in red for >15 days, now at +0.5% — sell
                qty = pos["qty"]
                result = await self.alpaca.sell_market(ticker, qty)
                await self._log_trade(
                    ticker, "exit_red_zone", "SELL", qty,
                    pnl_pct=pos.get("unrealized_pnl_pct"),
                    reason=f"Exited red zone after {days_held} days",
                )
                await self._track_position_close(ticker)

                logger.info(
                    "EXIT RED ZONE: %s — sold %d shares after %d days in red",
                    ticker,
                    int(qty),
                    days_held,
                )

                await self.ws.broadcast({
                    "type": "trade_executed",
                    "action": "exit_red_zone",
                    "ticker": ticker,
                    "qty_sold": qty,
                    "days_held": days_held,
                    "timestamp": datetime.now().isoformat(),
                })

            elif loss_action["action"] == "waiting_exit_red":
                logger.debug(
                    "Waiting to exit red for %s: %d days, %.2f%%",
                    ticker,
                    days_held,
                    pos["unrealized_pnl_pct"],
                )

    # ------------------------------------------------------------------
    # Execute pending signals (runs after market open)
    # ------------------------------------------------------------------
    async def execute_pending_signals(self) -> None:
        """Execute any pending BUY/SELL signals from pre-market analysis."""
        if not self._pending_signals:
            return

        for signal in self._pending_signals:
            try:
                if signal.get("signal") == "BUY":
                    await self.process_buy_signal(signal)
                elif signal.get("signal") == "SELL":
                    await self.process_sell_signal(signal)
            except Exception as e:
                logger.error(
                    "Failed to execute signal for %s: %s",
                    signal.get("ticker"),
                    e,
                )

        self._pending_signals.clear()

    async def process_buy_signal(self, signal: dict[str, Any]) -> None:
        """
        Process a BUY signal through the rules engine and execute if approved.
        """
        ticker = signal.get("ticker", "")

        # Check if we already hold this ticker
        existing = await self.alpaca.get_position(ticker)
        if existing:
            logger.info("Already holding %s — skipping buy signal", ticker)
            return

        # Get ticker profile for validation
        from database.models import get_session, TickerProfile
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(TickerProfile).where(TickerProfile.ticker == ticker)
            )
            profile = result.scalar_one_or_none()

        if not profile:
            logger.warning("No profile for %s — cannot validate entry", ticker)
            return

        profile_dict = {
            "ticker": profile.ticker,
            "threshold_extraordinary_pct": profile.threshold_extraordinary_pct,
        }

        # Validate entry through rules engine
        validation = self.rules.validate_entry(signal, profile_dict)

        if not validation.get("approved"):
            logger.info(
                "BUY REJECTED for %s: %s",
                ticker,
                validation.get("reason"),
            )
            return

        # Calculate position size
        portfolio = await self.alpaca.get_portfolio_summary()
        buying_power = portfolio.get("buying_power", 0)
        snapshot = await self.alpaca.get_snapshot(ticker)

        if not snapshot or not snapshot.get("latest_trade_price"):
            logger.warning("No price data for %s — cannot size position", ticker)
            return

        current_price = snapshot["latest_trade_price"]
        qty = self.rules.calculate_position_size(
            buying_power=buying_power,
            current_price=current_price,
            risk_level=signal.get("risk_level", "medium"),
        )

        if qty <= 0:
            logger.warning("Position size is 0 for %s — skipping", ticker)
            return

        # Execute buy
        result = await self.alpaca.buy_market(ticker, qty)

        if "error" not in result:
            await self._track_position_open(ticker, price=current_price, qty=qty)
            await self._log_trade(
                ticker, "buy", "BUY", qty, price=current_price,
                reason=f"Catalyst: {signal.get('catalysts', [])}",
            )
            logger.info(
                "BUY EXECUTED: %s x%d @ ~$%.2f (catalyst: %s)",
                ticker,
                qty,
                current_price,
                signal.get("catalysts", ["unknown"]),
            )

            await self.ws.broadcast({
                "type": "trade_executed",
                "action": "buy",
                "ticker": ticker,
                "qty": qty,
                "price": current_price,
                "catalysts": signal.get("catalysts", []),
                "confidence": signal.get("confidence", 0),
                "timestamp": datetime.now().isoformat(),
            })

    async def process_sell_signal(self, signal: dict[str, Any]) -> None:
        """Process a SELL signal — only sells if position exists."""
        ticker = signal.get("ticker", "")
        position = await self.alpaca.get_position(ticker)

        if not position:
            logger.debug("No position to sell for %s", ticker)
            return

        qty = position["qty"]
        result = await self.alpaca.sell_market(ticker, qty)

        if "error" not in result:
            await self._track_position_close(ticker)
            await self._log_trade(
                ticker, "sell", "SELL", qty,
                pnl_pct=position.get("unrealized_pnl_pct", 0),
                reason=signal.get("reasoning", "LLM signal"),
            )
            logger.info(
                "SELL EXECUTED: %s x%d (reason: %s)",
                ticker,
                int(qty),
                signal.get("reasoning", "LLM signal"),
            )

            await self.ws.broadcast({
                "type": "trade_executed",
                "action": "sell",
                "ticker": ticker,
                "qty": qty,
                "pnl_pct": position.get("unrealized_pnl_pct", 0),
                "timestamp": datetime.now().isoformat(),
            })

    # ------------------------------------------------------------------
    # Overnight evaluation (runs at 3:30pm)
    # ------------------------------------------------------------------
    async def evaluate_overnight_holds(
        self, signals: list[dict[str, Any]]
    ) -> None:
        """
        At 3:30pm, decide which positions to hold overnight.
        Rule: Hold overnight only if signal is positive with active catalyst.
        """
        positions = await self.alpaca.get_open_positions()
        signal_map = {s.get("ticker"): s for s in signals}

        for pos in positions:
            ticker = pos["ticker"]
            signal = signal_map.get(ticker, {})

            should_hold = self.rules.should_hold_overnight(signal)

            if not should_hold:
                # Close position before market close
                qty = pos["qty"]
                pnl_pct = pos.get("unrealized_pnl_pct", 0)

                # But don't sell in the red unless catalyst override
                if pnl_pct < 0:
                    logger.info(
                        "Would close %s overnight but it's in red (%.2f%%). Holding per rules.",
                        ticker,
                        pnl_pct,
                    )
                    continue

                result = await self.alpaca.sell_market(ticker, qty)
                await self._log_trade(
                    ticker, "close_eod", "SELL", qty,
                    pnl_pct=pnl_pct,
                    reason="No positive signal for overnight",
                )
                await self._track_position_close(ticker)
                logger.info(
                    "CLOSE BEFORE EOD: %s x%d (no positive signal for overnight hold)",
                    ticker,
                    int(qty),
                )

                await self.ws.broadcast({
                    "type": "trade_executed",
                    "action": "close_eod",
                    "ticker": ticker,
                    "qty": qty,
                    "reason": "No positive signal for overnight",
                    "timestamp": datetime.now().isoformat(),
                })
            else:
                logger.info(
                    "HOLDING OVERNIGHT: %s (signal: %s, confidence: %.2f)",
                    ticker,
                    signal.get("signal"),
                    signal.get("confidence", 0),
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_days_held(self, ticker: str) -> int:
        """Get the number of days a position has been held."""
        open_date = self._position_open_dates.get(ticker)
        if open_date:
            return (datetime.now() - open_date).days
        return 0

    def store_pending_signals(self, signals: list[dict[str, Any]]) -> None:
        """Store signals from pre-market for execution at market open."""
        self._pending_signals = [
            s for s in signals if s.get("signal") in ("BUY", "SELL")
        ]
        logger.info("Stored %d pending signals for market open", len(self._pending_signals))
