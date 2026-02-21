"""
LLM Analyst — Gemini-powered market analysis engine.
Produces BUY / SELL / HOLD signals with written reasoning.
The LLM NEVER executes orders — it only produces signals.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from google import genai

from config import settings

logger = logging.getLogger("trading_bot.llm")

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
RETRY_BASE_DELAY = 5  # seconds

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a professional swing trading analyst. Your job is to analyze market data, news, catalysts, and sentiment to produce clear trading signals.

CRITICAL RULES:
1. You ONLY produce signals: BUY, SELL, or HOLD. You NEVER execute trades.
2. You must cite specific sources/catalysts for every signal.
3. A BUY signal requires a CONFIRMED catalyst within the next 1-2 months.
4. Do NOT recommend buying if the price rise is purely sentiment-driven without a verifiable catalyst.
5. Do NOT recommend companies with a sustained negative trend over the last 12 months unless there is a very clear cycle-change catalyst.
6. Long-term catalysts (>2 months) are only valid if there is evidence the market is actively pricing them in NOW.
7. When analyzing sentiment, distinguish between genuine momentum and hype.
8. Be conservative — when in doubt, signal HOLD.

OUTPUT FORMAT (JSON only, no markdown):
{
    "ticker": "SYMBOL",
    "signal": "BUY" | "SELL" | "HOLD",
    "confidence": 0.0 to 1.0,
    "reasoning": "2-3 sentence explanation",
    "catalysts": ["catalyst 1", "catalyst 2"],
    "catalyst_type": "positive" | "negative" | "neutral",
    "catalyst_horizon": "short_term" | "medium_term" | "long_term",
    "sentiment_score": -1.0 to 1.0,
    "risk_level": "low" | "medium" | "high",
    "suggested_action": "brief action description"
}"""

SELL_ANALYSIS_PROMPT = """You are analyzing whether to SELL a position that is currently in the RED (negative P&L).

The trading system has a rule: NEVER close in red UNLESS a new confirmed negative catalyst has appeared.
Your job is to determine if a genuine new negative catalyst exists that justifies overriding this rule.

A valid negative catalyst must be:
- NEW (not already priced in)
- CONFIRMED (from a credible source, not rumor)
- MATERIAL (significant enough to fundamentally change the stock's trajectory)

Examples of valid catalysts: SEC investigation, major fraud revelation, CEO resignation under scandal, significant earnings miss with guidance cut, major product recall.
Examples of INVALID catalysts: general market fear, sector rotation, analyst downgrade without new information, short-seller reports without evidence.

OUTPUT FORMAT (JSON only):
{
    "ticker": "SYMBOL",
    "override_no_sell_rule": true | false,
    "negative_catalyst": "description or null",
    "catalyst_source": "source or null",
    "confidence": 0.0 to 1.0,
    "reasoning": "explanation"
}"""


class LLMAnalyst:
    """
    Gemini-powered analysis engine.
    Receives market context and produces structured trading signals.
    """

    def __init__(self) -> None:
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = "gemini-2.5-flash"
        logger.info("LLM Analyst initialized (model: %s)", self.model)

    async def _call_gemini(
        self,
        contents: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Call Gemini with automatic retry on rate-limit (429) errors."""
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                        response_mime_type="application/json",
                        thinking_config=genai.types.ThinkingConfig(
                            thinking_budget=0,
                        ),
                    ),
                )
                return response.text
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini rate-limited (attempt %d/%d), retrying in %ds…",
                        attempt, MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        raise last_error  # type: ignore[misc]

    async def analyze_ticker(
        self,
        ticker: str,
        news: list[dict[str, Any]],
        price_data: dict[str, Any],
        position: Optional[dict[str, Any]] = None,
        extra_context: str = "",
    ) -> dict[str, Any]:
        """
        Analyze a ticker and produce a BUY/SELL/HOLD signal.
        """
        user_message = self._build_analysis_prompt(
            ticker, news, price_data, position, extra_context
        )

        try:
            content = await self._call_gemini(
                contents=f"{SYSTEM_PROMPT}\n\n{user_message}",
                max_tokens=1024,
                temperature=0.3,
            )

            signal = self._parse_signal(content, ticker)
            logger.info(
                "Signal for %s: %s (confidence: %.2f)",
                ticker,
                signal.get("signal", "UNKNOWN"),
                signal.get("confidence", 0),
            )
            return signal

        except Exception as e:
            logger.error("LLM analysis failed for %s: %s", ticker, e)
            return {
                "ticker": ticker,
                "signal": "HOLD",
                "confidence": 0.0,
                "reasoning": f"Analysis failed: {str(e)}",
                "catalysts": [],
                "error": True,
            }

    async def analyze_sell_override(
        self,
        ticker: str,
        news: list[dict[str, Any]],
        position: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Analyze whether a position in the red should be sold
        due to a new confirmed negative catalyst (override rule).
        """
        user_message = (
            f"Ticker: {ticker}\n"
            f"Position: {json.dumps(position, default=str)}\n"
            f"Recent news:\n"
        )
        for article in news[:10]:
            user_message += (
                f"- [{article.get('source', 'unknown')}] "
                f"{article.get('headline', 'No headline')}: "
                f"{article.get('summary', 'No summary')}\n"
            )

        try:
            content = await self._call_gemini(
                contents=f"{SELL_ANALYSIS_PROMPT}\n\n{user_message}",
                max_tokens=512,
                temperature=0.2,
            )

            result = json.loads(self._clean_json(content))
            result["ticker"] = ticker
            result["analyzed_at"] = datetime.now().isoformat()
            logger.info(
                "Sell override analysis for %s: override=%s",
                ticker,
                result.get("override_no_sell_rule", False),
            )
            return result

        except Exception as e:
            logger.error("Sell override analysis failed for %s: %s", ticker, e)
            return {
                "ticker": ticker,
                "override_no_sell_rule": False,
                "reasoning": f"Analysis failed: {str(e)}",
                "error": True,
            }

    async def summarize_market_sentiment(
        self, news: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Produce a general market sentiment summary from a batch of news."""
        headlines = "\n".join(
            f"- {a.get('headline', '')}" for a in news[:30]
        )
        user_message = (
            f"You are a concise financial analyst. Return only valid JSON.\n\n"
            f"Summarize overall market sentiment based on these headlines. "
            f"Return JSON with: overall_sentiment (-1 to 1), key_themes (list), "
            f"sectors_bullish (list), sectors_bearish (list), summary (2 sentences).\n\n"
            f"{headlines}"
        )

        try:
            content = await self._call_gemini(
                contents=user_message,
                max_tokens=512,
                temperature=0.2,
            )
            return json.loads(self._clean_json(content))
        except Exception as e:
            logger.error("Market sentiment analysis failed: %s", e)
            return {"overall_sentiment": 0, "summary": "Analysis unavailable"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clean_json(self, raw: str) -> str:
        """Extract valid JSON from LLM output, stripping fences/text."""
        import re

        cleaned = raw.strip()

        # Remove markdown fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3]
            cleaned = cleaned.strip()

        # If it already parses, return as-is
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            pass

        # Try to extract the first JSON object from the text
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            candidate = match.group(0)
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        return cleaned

    def _build_analysis_prompt(
        self,
        ticker: str,
        news: list[dict[str, Any]],
        price_data: dict[str, Any],
        position: Optional[dict[str, Any]],
        extra_context: str,
    ) -> str:
        """Build the user prompt for ticker analysis."""
        parts = [
            f"Analyze {ticker} for a swing trading signal.",
            f"\n--- PRICE DATA ---\n{json.dumps(price_data, indent=2, default=str)}",
        ]

        if position:
            parts.append(
                f"\n--- CURRENT POSITION ---\n{json.dumps(position, indent=2, default=str)}"
            )
        else:
            parts.append("\nNo current position in this ticker.")

        parts.append("\n--- RECENT NEWS ---")
        if news:
            for article in news[:10]:
                parts.append(
                    f"- [{article.get('source', 'unknown')}] "
                    f"{article.get('headline', 'No headline')}\n"
                    f"  {article.get('summary', 'No summary')}"
                )
        else:
            parts.append("No recent news found.")

        if extra_context:
            parts.append(f"\n--- ADDITIONAL CONTEXT ---\n{extra_context}")

        parts.append(
            f"\nCurrent datetime: {datetime.now().isoformat()}"
        )

        return "\n".join(parts)

    def _parse_signal(self, raw_response: str, ticker: str) -> dict[str, Any]:
        """Parse the LLM response into a structured signal dict."""
        try:
            cleaned = self._clean_json(raw_response)
            signal = json.loads(cleaned)
            signal["ticker"] = ticker
            signal["analyzed_at"] = datetime.now().isoformat()
            signal["raw_response"] = raw_response

            # Validate signal value
            if signal.get("signal") not in ("BUY", "SELL", "HOLD"):
                signal["signal"] = "HOLD"
                signal["confidence"] = 0.0

            return signal

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON for %s", ticker)
            return {
                "ticker": ticker,
                "signal": "HOLD",
                "confidence": 0.0,
                "reasoning": raw_response[:500],
                "catalysts": [],
                "analyzed_at": datetime.now().isoformat(),
                "parse_error": True,
            }
