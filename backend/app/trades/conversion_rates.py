"""Historical quote-currency conversion for manually entered trades."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from app.backtests.fx_conversion import (
    FXConversionUnavailable,
    build_conversion_spec,
    resolve_conversion_route_rate,
    resolve_quote_to_usd_rate,
)


logger = logging.getLogger(__name__)
_BAR_MILLISECONDS = 60_000
_MAX_LOOKBACK_DAYS = 7


class ManualTradeConversionRateService:
    """Resolve an editable manual-trade USD rate from completed minute bars."""

    def __init__(self, provider=None) -> None:
        # Import the provider lazily so trades without FX conversion do not
        # initialize the historical data adapter.
        self.provider = provider

    def quote_to_usd_rate(
        self,
        *,
        quote_currency: str,
        event_time: datetime,
        instruments: Mapping[str, Any],
        quote_currency_unit_scale: float | None = None,
    ) -> dict[str, Any]:
        """Return a historical conversion quote or a user-facing reason."""
        currency = str(quote_currency).strip().upper()
        if event_time.tzinfo is None or event_time.utcoffset() is None:
            return self._unavailable(
                currency, "The conversion lookup time must include a timezone."
            )

        event_time = event_time.astimezone(timezone.utc)
        event_time_ms = int(event_time.timestamp() * 1000)
        try:
            spec = build_conversion_spec(
                currency,
                instruments=instruments,
                quote_currency_unit_scale=quote_currency_unit_scale,
            )
        except (TypeError, ValueError) as exc:
            return self._unavailable(currency, str(exc))

        if spec is None or not spec.get("supported"):
            return self._unavailable(
                currency,
                (spec or {}).get("reason")
                or f"No conversion route from {currency} to USD is configured.",
                route=(spec or {}).get("route", []),
                quote_currency_unit_scale=(spec or {}).get(
                    "quote_currency_unit_scale"
                ),
            )

        route = spec.get("route") or []
        scale = float(spec.get("quote_currency_unit_scale", 1.0))
        if not route:
            return {
                "available": True,
                "quote_currency": currency,
                "quote_to_usd_rate": scale,
                "quote_currency_unit_scale": scale,
                "rate_time": None,
                "route": [],
                "reason": None,
            }

        observations: dict[str, list[dict[str, Any]]] = {
            str(leg["instrument"]).upper(): [] for leg in route
        }
        provider = self._get_provider()
        event_date = event_time.date()
        try:
            for day_offset in range(_MAX_LOOKBACK_DAYS + 1):
                utc_date = event_date - timedelta(days=day_offset)
                for leg in route:
                    instrument = str(leg["instrument"]).upper()
                    if self._leg_rate(observations[instrument], leg, event_time_ms):
                        continue
                    result = provider.fetch_conversion_day(instrument, utc_date)
                    candles = (
                        result.get("candles", [])
                        if isinstance(result, Mapping)
                        else []
                    )
                    observations[instrument].extend(
                        candle for candle in candles if isinstance(candle, dict)
                    )
                if all(
                    self._leg_rate(
                        observations[str(leg["instrument"]).upper()],
                        leg,
                        event_time_ms,
                    )
                    for leg in route
                ):
                    break
        except Exception as exc:  # Provider failures should permit manual entry.
            logger.warning(
                "Manual trade conversion lookup failed for %s: %s",
                currency,
                exc,
            )
            return self._unavailable(
                currency,
                "Historical conversion candles could not be retrieved; enter a rate manually.",
                route=route,
                quote_currency_unit_scale=scale,
            )

        leg_rates = []
        for leg in route:
            instrument = str(leg["instrument"]).upper()
            resolved = self._leg_rate(
                observations[instrument], leg, event_time_ms
            )
            if resolved is None:
                return self._unavailable(
                    currency,
                    "No completed historical conversion rate was found within the previous seven days; enter a rate manually.",
                    route=route,
                    quote_currency_unit_scale=scale,
                )
            leg_rates.append((leg, resolved))

        try:
            rate = resolve_conversion_route_rate(
                currency,
                event_time_ms,
                route,
                observations,
                quote_currency_unit_scale=scale,
            )
        except (FXConversionUnavailable, TypeError, ValueError) as exc:
            return self._unavailable(currency, str(exc), route=route)

        # A multi-leg route can use candles that closed at different times.
        # Report the oldest leg close as the conservative common as-of time.
        rate_time_ms = min(item[1][1] for item in leg_rates)
        return {
            "available": True,
            "quote_currency": currency,
            "quote_to_usd_rate": rate,
            "quote_currency_unit_scale": scale,
            "rate_time": datetime.fromtimestamp(
                rate_time_ms / 1000, timezone.utc
            ).isoformat(),
            "route": [
                {
                    **dict(leg),
                    "rate": resolved[0],
                    "rate_time": datetime.fromtimestamp(
                        resolved[1] / 1000, timezone.utc
                    ).isoformat(),
                }
                for leg, resolved in leg_rates
            ],
            "reason": None,
        }

    @staticmethod
    def _leg_rate(
        observations: list[dict[str, Any]],
        leg: Mapping[str, Any],
        event_time_ms: int,
    ) -> tuple[float, int] | None:
        """Resolve a route leg and its latest eligible candle close time."""
        try:
            rate = resolve_quote_to_usd_rate(
                str(leg.get("from_currency", "")),
                event_time_ms,
                observations,
                direction=str(leg.get("direction", "")),
            )
        except (FXConversionUnavailable, TypeError, ValueError):
            return None

        eligible_close_times = []
        for candle in observations:
            try:
                candle_time = int(candle["time_ms"])
                close = float(candle["close"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            close_time = candle_time + _BAR_MILLISECONDS
            if (
                close_time <= event_time_ms
                and math.isfinite(close)
                and close > 0
            ):
                eligible_close_times.append(close_time)
        if not eligible_close_times:
            return None
        return rate, max(eligible_close_times)

    def _get_provider(self):
        if self.provider is None:
            from app.backtests.dukascopy_provider import DukascopyProvider

            self.provider = DukascopyProvider()
        return self.provider

    @staticmethod
    def _unavailable(
        quote_currency: str,
        reason: str,
        *,
        route: list | None = None,
        quote_currency_unit_scale: float | None = None,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "quote_currency": quote_currency,
            "quote_to_usd_rate": None,
            "quote_currency_unit_scale": quote_currency_unit_scale,
            "rate_time": None,
            "route": route or [],
            "reason": reason,
        }
