"""User model definition."""

from app.market_data.symbol_mapper import (
    get_default_market_data_mappings,
    get_default_symbol_mappings,
)
from app.utils.datetime_utils import utc_now

DEFAULT_STARTING_EQUITY = 10000.0
DEFAULT_RISK_BREAKEVEN_R_THRESHOLD = 0.05


def create_user_doc(
    username: str,
    password_hash: str,
    timezone: str = "America/New_York",
    display_timezone: str | None = None,
    starting_equity: float = DEFAULT_STARTING_EQUITY,
    risk_breakeven_enabled: bool = False,
    risk_breakeven_r_threshold: float = DEFAULT_RISK_BREAKEVEN_R_THRESHOLD,
    symbol_mappings: dict | None = None,
    market_data_mappings: dict | None = None,
) -> dict:
    """
    Create a user document for MongoDB insertion.

    Parameters:
        username: Unique username.
        password_hash: Bcrypt-hashed password.
        timezone: User's trading timezone.
        display_timezone: Timezone for UI display
            (defaults to trading timezone).
        starting_equity: Initial account equity for
            Monte Carlo simulations (default 10 000).
        risk_breakeven_r_threshold: Absolute fee-inclusive R
            threshold for optional breakeven classification.
        symbol_mappings: User-configurable point-value mappings
            keyed by base symbol.
        market_data_mappings: User-configurable market-data
            prefix mappings keyed by source symbol.

    Returns:
        Dict ready for MongoDB insert.
    """
    now = utc_now()
    return {
        "username": username,
        "password_hash": password_hash,
        "timezone": timezone,
        "display_timezone": display_timezone or timezone,
        "starting_equity": starting_equity,
        "risk_breakeven_enabled": risk_breakeven_enabled,
        "risk_breakeven_r_threshold": risk_breakeven_r_threshold,
        "symbol_mappings": (
            symbol_mappings
            or get_default_symbol_mappings()
        ),
        "market_data_mappings": (
            market_data_mappings
            or get_default_market_data_mappings()
        ),
        "created_at": now,
        "updated_at": now,
    }
