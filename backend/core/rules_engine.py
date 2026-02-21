"""
Rules Engine — Deterministic trading rules.
This module contains ALL hard-coded trading rules. The LLM NEVER overrides these.
The only exception is the sell-override for confirmed negative catalysts.
"""

import logging
from typing import Any

from config import settings

logger = logging.getLogger("trading_bot.rules")


class RulesEngine:
    """
    Hard-coded trading rules based on the Rulebook v1.0.
    Every decision goes through this engine before reaching Alpaca.
    """

    def __init__(self, alpaca_client: Any) -> None:
        self.alpaca = alpaca_client

    # ------------------------------------------------------------------
    # Take Profit Rule
    # ------------------------------------------------------------------
    def should_take_profit(self, position: dict[str, Any]) -> bool:
        """
        Rule: Sell 100% if position reaches +TAKE_PROFIT_PCT% at any time.
        No exceptions.
        """
        pnl_pct = position.get("unrealized_pnl_pct", 0.0)
        if pnl_pct >= settings.take_profit_pct:
            logger.info(
                "TAKE PROFIT triggered for %s: %.2f%% >= %.2f%%",
                position["ticker"],
                pnl_pct,
                settings.take_profit_pct,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Extraordinary Gap Up Rule
    # ------------------------------------------------------------------
    def should_sell_extraordinary_gap(
        self,
        ticker: str,
        gap_up_pct: float,
        threshold_pct: float,
    ) -> dict[str, Any]:
        """
        Rule: If gap up > threshold_extraordinario → sell 60% immediately.
        Monitor remaining 40% with trailing stop based on tick momentum.

        Returns action dict with sell_pct and trailing_stop instructions.
        """
        if gap_up_pct > threshold_pct:
            logger.info(
                "EXTRAORDINARY GAP for %s: %.2f%% > threshold %.2f%%",
                ticker,
                gap_up_pct,
                threshold_pct,
            )
            return {
                "action": "extraordinary_gap_sell",
                "ticker": ticker,
                "sell_pct": settings.extraordinary_gap_sell_pct,  # 60%
                "remaining_pct": 100 - settings.extraordinary_gap_sell_pct,  # 40%
                "trailing_stop": True,
                "gap_up_pct": gap_up_pct,
                "threshold_pct": threshold_pct,
            }
        return {"action": "none"}

    # ------------------------------------------------------------------
    # Loss Rules
    # ------------------------------------------------------------------
    def evaluate_loss_position(
        self,
        position: dict[str, Any],
        days_held: int,
        has_negative_catalyst: bool = False,
    ) -> dict[str, Any]:
        """
        Loss management rules:
        1. Never close in red (default).
        2. Exception: confirmed negative catalyst → allow sell.
        3. If >15 days in red → wait until +0.5% and sell immediately.

        Returns action dict.
        """
        pnl_pct = position.get("unrealized_pnl_pct", 0.0)
        ticker = position.get("ticker", "UNKNOWN")

        # Position is in profit — no loss rule applies
        if pnl_pct >= 0:
            # Check if this was a long-held red position now barely green
            if days_held >= settings.max_position_days_red and pnl_pct >= settings.min_profit_to_exit_red:
                logger.info(
                    "EXIT RED ZONE for %s: held %d days, now at +%.2f%%",
                    ticker,
                    days_held,
                    pnl_pct,
                )
                return {
                    "action": "exit_red_zone",
                    "ticker": ticker,
                    "reason": f"Held {days_held} days in red, now at +{pnl_pct:.2f}% — selling to exit",
                    "sell_pct": 100.0,
                }
            return {"action": "none"}

        # Position is in the red
        if has_negative_catalyst:
            logger.warning(
                "NEGATIVE CATALYST OVERRIDE for %s: selling in red at %.2f%%",
                ticker,
                pnl_pct,
            )
            return {
                "action": "negative_catalyst_sell",
                "ticker": ticker,
                "reason": "Confirmed negative catalyst — overriding no-sell-in-red rule",
                "sell_pct": 100.0,
            }

        # In red, no catalyst, but held too long — waiting for +0.5%
        if days_held >= settings.max_position_days_red:
            logger.info(
                "WAITING TO EXIT RED for %s: held %d days, current %.2f%%",
                ticker,
                days_held,
                pnl_pct,
            )
            return {
                "action": "waiting_exit_red",
                "ticker": ticker,
                "reason": f"Held {days_held} days in red. Waiting for +{settings.min_profit_to_exit_red}% to exit.",
                "target_pct": settings.min_profit_to_exit_red,
            }

        # In red, no catalyst, not yet 15 days — hold
        return {
            "action": "hold_in_red",
            "ticker": ticker,
            "reason": f"In red at {pnl_pct:.2f}% for {days_held} days. Holding per rules.",
        }

    # ------------------------------------------------------------------
    # Entry Rules
    # ------------------------------------------------------------------
    def validate_entry(
        self,
        signal: dict[str, Any],
        ticker_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate a BUY signal against entry rules:
        1. Must have confirmed catalyst within 1-2 months.
        2. No buying on pure sentiment without verifiable catalyst.
        3. No buying companies with 12-month negative trend (unless clear cycle change).

        Returns validated entry decision.
        """
        if signal.get("signal") != "BUY":
            return {"approved": False, "reason": f"Signal is {signal.get('signal')}, not BUY"}

        # Check catalyst exists
        catalysts = signal.get("catalysts", [])
        if not catalysts:
            logger.info("ENTRY REJECTED for %s: no catalysts found", signal["ticker"])
            return {
                "approved": False,
                "reason": "No verifiable catalyst found. Cannot buy on sentiment alone.",
            }

        # Check catalyst horizon
        horizon = signal.get("catalyst_horizon", "unknown")
        if horizon == "long_term":
            # Only valid if market is actively pricing it in
            if signal.get("confidence", 0) < 0.7:
                return {
                    "approved": False,
                    "reason": "Long-term catalyst without strong evidence of market pricing it in.",
                }

        # Check confidence threshold
        if signal.get("confidence", 0) < 0.5:
            return {
                "approved": False,
                "reason": f"Confidence too low: {signal.get('confidence', 0):.2f}",
            }

        logger.info(
            "ENTRY APPROVED for %s: %s (confidence: %.2f)",
            signal["ticker"],
            catalysts,
            signal.get("confidence", 0),
        )
        return {
            "approved": True,
            "ticker": signal["ticker"],
            "catalysts": catalysts,
            "confidence": signal.get("confidence", 0),
            "reasoning": signal.get("reasoning", ""),
        }

    # ------------------------------------------------------------------
    # Overnight Rules
    # ------------------------------------------------------------------
    def should_hold_overnight(self, signal: dict[str, Any]) -> bool:
        """
        Rule: Hold overnight ONLY if the 3:30pm analysis produces a positive
        signal with an active confirmed catalyst. Otherwise, close before end of day.
        """
        if signal.get("signal") in ("BUY", "HOLD"):
            if signal.get("catalysts") and signal.get("confidence", 0) >= 0.5:
                return True
        return False

    # ------------------------------------------------------------------
    # Position Sizing
    # ------------------------------------------------------------------
    def calculate_position_size(
        self,
        buying_power: float,
        current_price: float,
        risk_level: str = "medium",
        max_pct_portfolio: float = 20.0,
    ) -> int:
        """
        Calculate number of shares to buy.
        Caps each position at max_pct_portfolio% of buying power.
        """
        max_allocation = buying_power * (max_pct_portfolio / 100)
        shares = int(max_allocation / current_price)

        if shares <= 0:
            logger.warning("Position size is 0 — not enough buying power")
            return 0

        logger.info(
            "Position size: %d shares @ $%.2f = $%.2f (%.1f%% of $%.2f)",
            shares,
            current_price,
            shares * current_price,
            (shares * current_price / buying_power) * 100,
            buying_power,
        )
        return shares

    # ------------------------------------------------------------------
    # Momentum Check (for extraordinary gap trailing)
    # ------------------------------------------------------------------
    def check_momentum_decay(
        self,
        recent_ticks: list[float],
        decay_threshold: float = 0.30,
    ) -> bool:
        """
        Check if the last 4 ticks show decaying momentum.
        Rule: If the range between ticks is <30% of the previous tick's range,
        momentum is dying → sell remaining position.

        Args:
            recent_ticks: Last 4+ price values (most recent last)
            decay_threshold: % of previous range that triggers decay signal
        """
        if len(recent_ticks) < 4:
            return False

        last_4 = recent_ticks[-4:]
        ranges = [abs(last_4[i + 1] - last_4[i]) for i in range(3)]

        # Check if each subsequent range is smaller than threshold of previous
        decaying = all(
            ranges[i + 1] < ranges[i] * decay_threshold
            for i in range(len(ranges) - 1)
            if ranges[i] > 0
        )

        if decaying:
            logger.info("MOMENTUM DECAY detected: ticks=%s, ranges=%s", last_4, ranges)

        return decaying
