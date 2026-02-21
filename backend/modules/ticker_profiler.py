"""
Ticker Profiler — Calculates and stores the "extraordinary gap" threshold
for each ticker based on historical data.

When a ticker is added to the watchlist, this module:
1. Fetches 4 months of daily bar data
2. Calculates gap-up statistics (days that opened higher than previous close)
3. Computes threshold = (avg_gap_up + max_gap_up + p75_gap_up) / 3
4. Stores the profile in the database
5. Recalculates every 30 days; alerts if threshold changes >30%
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import numpy as np

from config import settings

logger = logging.getLogger("trading_bot.profiler")


class TickerProfiler:
    """
    Manages ticker profiles — historical volatility analysis and
    extraordinary gap thresholds.
    """

    def __init__(self, alpaca_client: Any) -> None:
        self.alpaca = alpaca_client

    async def create_profile(self, ticker: str, session: Any) -> dict[str, Any]:
        """
        Create a new ticker profile by analyzing historical data.
        Called when a user adds a ticker to the watchlist.
        """
        logger.info("Creating profile for %s...", ticker)

        # Fetch historical bars
        bars = await self.alpaca.get_historical_bars(
            ticker=ticker,
            months_back=settings.ticker_profile_months,
        )

        if not bars or len(bars) < 10:
            logger.error("Not enough data for %s — only %d bars", ticker, len(bars))
            return {"error": f"Not enough historical data for {ticker}"}

        # Calculate gap-up statistics
        profile = self._calculate_gap_stats(ticker, bars)

        # Save to database
        from database.models import TickerProfile

        db_profile = TickerProfile(
            ticker=ticker,
            analysis_date=datetime.now(),
            analysis_period_months=settings.ticker_profile_months,
            days_analyzed=profile["days_analyzed"],
            days_gap_up=profile["days_gap_up"],
            gap_up_frequency_pct=profile["gap_up_frequency_pct"],
            gap_up_avg_pct=profile["gap_up_avg_pct"],
            gap_up_max_pct=profile["gap_up_max_pct"],
            gap_up_p75_pct=profile["gap_up_p75_pct"],
            threshold_extraordinary_pct=profile["threshold_extraordinary_pct"],
            next_recalc_date=datetime.now() + timedelta(days=settings.ticker_profile_recalc_days),
        )

        # Use merge to upsert
        await session.merge(db_profile)
        await session.commit()

        logger.info(
            "Profile created for %s: threshold=%.2f%%",
            ticker,
            profile["threshold_extraordinary_pct"],
        )

        return profile

    async def get_all_profiles(self, session: Any) -> list[dict[str, Any]]:
        """Get all stored ticker profiles."""
        from database.models import TickerProfile
        from sqlalchemy import select

        result = await session.execute(select(TickerProfile))
        profiles = result.scalars().all()

        return [
            {
                "ticker": p.ticker,
                "analysis_date": p.analysis_date.isoformat() if p.analysis_date else None,
                "days_analyzed": p.days_analyzed,
                "days_gap_up": p.days_gap_up,
                "gap_up_frequency_pct": p.gap_up_frequency_pct,
                "gap_up_avg_pct": p.gap_up_avg_pct,
                "gap_up_max_pct": p.gap_up_max_pct,
                "gap_up_p75_pct": p.gap_up_p75_pct,
                "threshold_extraordinary_pct": p.threshold_extraordinary_pct,
                "next_recalc_date": p.next_recalc_date.isoformat() if p.next_recalc_date else None,
            }
            for p in profiles
        ]

    async def get_profile(self, ticker: str, session: Any) -> Optional[dict[str, Any]]:
        """Get a single ticker profile."""
        from database.models import TickerProfile
        from sqlalchemy import select

        result = await session.execute(
            select(TickerProfile).where(TickerProfile.ticker == ticker)
        )
        p = result.scalar_one_or_none()

        if p is None:
            return None

        return {
            "ticker": p.ticker,
            "analysis_date": p.analysis_date.isoformat() if p.analysis_date else None,
            "days_analyzed": p.days_analyzed,
            "days_gap_up": p.days_gap_up,
            "gap_up_frequency_pct": p.gap_up_frequency_pct,
            "gap_up_avg_pct": p.gap_up_avg_pct,
            "gap_up_max_pct": p.gap_up_max_pct,
            "gap_up_p75_pct": p.gap_up_p75_pct,
            "threshold_extraordinary_pct": p.threshold_extraordinary_pct,
            "next_recalc_date": p.next_recalc_date.isoformat() if p.next_recalc_date else None,
        }

    async def delete_profile(self, ticker: str, session: Any) -> None:
        """Delete a ticker profile from the watchlist."""
        from database.models import TickerProfile
        from sqlalchemy import delete

        await session.execute(
            delete(TickerProfile).where(TickerProfile.ticker == ticker)
        )
        await session.commit()
        logger.info("Profile deleted for %s", ticker)

    async def recalculate_expired_profiles(self, session: Any) -> list[str]:
        """
        Recalculate profiles that are due for update (every 30 days).
        Returns list of updated tickers.
        If threshold changes >30%, logs alert.
        """
        from database.models import TickerProfile
        from sqlalchemy import select

        result = await session.execute(
            select(TickerProfile).where(TickerProfile.next_recalc_date <= datetime.now())
        )
        expired = result.scalars().all()
        updated_tickers = []

        for old_profile in expired:
            ticker = old_profile.ticker
            old_threshold = old_profile.threshold_extraordinary_pct

            logger.info("Recalculating profile for %s (expired)", ticker)

            bars = await self.alpaca.get_historical_bars(
                ticker=ticker,
                months_back=settings.ticker_profile_months,
            )

            if not bars or len(bars) < 10:
                logger.warning("Not enough data for recalc of %s, skipping", ticker)
                continue

            new_stats = self._calculate_gap_stats(ticker, bars)
            new_threshold = new_stats["threshold_extraordinary_pct"]

            # Check for significant change
            if old_threshold > 0:
                change_pct = abs(new_threshold - old_threshold) / old_threshold * 100
                if change_pct > settings.threshold_change_alert_pct:
                    logger.warning(
                        "⚠️ ALERT: %s threshold changed %.1f%% (%.2f → %.2f). Review manually!",
                        ticker,
                        change_pct,
                        old_threshold,
                        new_threshold,
                    )

            # Update profile
            old_profile.analysis_date = datetime.now()
            old_profile.days_analyzed = new_stats["days_analyzed"]
            old_profile.days_gap_up = new_stats["days_gap_up"]
            old_profile.gap_up_frequency_pct = new_stats["gap_up_frequency_pct"]
            old_profile.gap_up_avg_pct = new_stats["gap_up_avg_pct"]
            old_profile.gap_up_max_pct = new_stats["gap_up_max_pct"]
            old_profile.gap_up_p75_pct = new_stats["gap_up_p75_pct"]
            old_profile.threshold_extraordinary_pct = new_threshold
            old_profile.next_recalc_date = datetime.now() + timedelta(
                days=settings.ticker_profile_recalc_days
            )

            updated_tickers.append(ticker)

        if updated_tickers:
            await session.commit()

        return updated_tickers

    # ------------------------------------------------------------------
    # Calculation: gap-up statistics
    # ------------------------------------------------------------------
    def _calculate_gap_stats(
        self, ticker: str, bars: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Calculate gap-up statistics from daily bars.

        Gap up = today's open > yesterday's close.
        """
        gap_ups: list[float] = []

        for i in range(1, len(bars)):
            prev_close = bars[i - 1]["close"]
            today_open = bars[i]["open"]

            if prev_close > 0:
                gap_pct = ((today_open - prev_close) / prev_close) * 100
                if gap_pct > 0:
                    gap_ups.append(gap_pct)

        total_days = len(bars) - 1  # exclude first day (no previous close)
        days_gap_up = len(gap_ups)

        if days_gap_up == 0:
            # No gap ups in the period
            return {
                "ticker": ticker,
                "days_analyzed": total_days,
                "days_gap_up": 0,
                "gap_up_frequency_pct": 0.0,
                "gap_up_avg_pct": 0.0,
                "gap_up_max_pct": 0.0,
                "gap_up_p75_pct": 0.0,
                "threshold_extraordinary_pct": 0.0,
            }

        gap_arr = np.array(gap_ups)

        avg_gap = float(np.mean(gap_arr))
        max_gap = float(np.max(gap_arr))
        p75_gap = float(np.percentile(gap_arr, 75))

        # threshold = (avg + max + p75) / 3
        threshold = (avg_gap + max_gap + p75_gap) / 3

        profile = {
            "ticker": ticker,
            "days_analyzed": total_days,
            "days_gap_up": days_gap_up,
            "gap_up_frequency_pct": round((days_gap_up / total_days) * 100, 1),
            "gap_up_avg_pct": round(avg_gap, 4),
            "gap_up_max_pct": round(max_gap, 4),
            "gap_up_p75_pct": round(p75_gap, 4),
            "threshold_extraordinary_pct": round(threshold, 4),
        }

        logger.info(
            "%s profile: %d/%d gap-up days (%.1f%%), avg=%.2f%%, max=%.2f%%, "
            "p75=%.2f%%, threshold=%.2f%%",
            ticker,
            days_gap_up,
            total_days,
            profile["gap_up_frequency_pct"],
            avg_gap,
            max_gap,
            p75_gap,
            threshold,
        )

        return profile
