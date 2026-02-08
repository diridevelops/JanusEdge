"""Market data cache model definition."""

from app.utils.datetime_utils import utc_now


def create_market_data_doc(
    symbol: str,
    interval: str,
    date,
    ohlc: list,
    bar_count: int,
) -> dict:
    """
    Create a market data cache document.

    Parameters:
        symbol: yfinance ticker (e.g. 'MES=F').
        interval: Time interval ('1m', '5m', etc.).
        date: Trading day as a date object.
        ohlc: List of OHLC dicts.
        bar_count: Number of candles.

    Returns:
        Dict ready for MongoDB insert.
    """
    return {
        "symbol": symbol,
        "interval": interval,
        "date": date,
        "ohlc": ohlc,
        "bar_count": bar_count,
        "fetched_at": utc_now(),
        "source": "yfinance",
    }
