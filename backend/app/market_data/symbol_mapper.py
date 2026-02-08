"""Symbol mapper — platform symbols to yfinance tickers."""

import re

# Platform symbol → yfinance ticker mapping
SYMBOL_MAP = {
    # NinjaTrader: "SYMBOL MM-YY"
    r"^MES\s+\d{2}-\d{2}$": "MES=F",
    r"^ES\s+\d{2}-\d{2}$": "ES=F",
    r"^MNQ\s+\d{2}-\d{2}$": "MNQ=F",
    r"^NQ\s+\d{2}-\d{2}$": "NQ=F",
    r"^MYM\s+\d{2}-\d{2}$": "MYM=F",
    r"^YM\s+\d{2}-\d{2}$": "YM=F",
    r"^MCL\s+\d{2}-\d{2}$": "MCL=F",
    r"^CL\s+\d{2}-\d{2}$": "CL=F",
    r"^GC\s+\d{2}-\d{2}$": "GC=F",
    r"^MGC\s+\d{2}-\d{2}$": "MGC=F",
    # Quantower: "SYMBOLMONYY" (e.g., MESM25)
    r"^MES[FGHJKMNQUVXZ]\d{2}$": "MES=F",
    r"^ES[FGHJKMNQUVXZ]\d{2}$": "ES=F",
    r"^MNQ[FGHJKMNQUVXZ]\d{2}$": "MNQ=F",
    r"^NQ[FGHJKMNQUVXZ]\d{2}$": "NQ=F",
    r"^MYM[FGHJKMNQUVXZ]\d{2}$": "MYM=F",
    r"^YM[FGHJKMNQUVXZ]\d{2}$": "YM=F",
    r"^MCL[FGHJKMNQUVXZ]\d{2}$": "MCL=F",
    r"^CL[FGHJKMNQUVXZ]\d{2}$": "CL=F",
    r"^GC[FGHJKMNQUVXZ]\d{2}$": "GC=F",
    r"^MGC[FGHJKMNQUVXZ]\d{2}$": "MGC=F",
}

# Normalized symbol → yfinance ticker (fallback)
BASE_SYMBOL_MAP = {
    "MES": "MES=F",
    "ES": "ES=F",
    "MNQ": "MNQ=F",
    "NQ": "NQ=F",
    "MYM": "MYM=F",
    "YM": "YM=F",
    "MCL": "MCL=F",
    "CL": "CL=F",
    "GC": "GC=F",
    "MGC": "MGC=F",
}


def map_to_yahoo(
    symbol: str, raw_symbol: str = None
) -> str:
    """
    Map a platform symbol to a yfinance ticker.

    Parameters:
        symbol: Normalized symbol (e.g. 'MES').
        raw_symbol: Original platform symbol.

    Returns:
        yfinance ticker string (e.g. 'MES=F').

    Raises:
        ValueError: If symbol cannot be mapped.
    """
    # Try raw symbol first (more specific)
    if raw_symbol:
        raw_clean = raw_symbol.strip()
        for pattern, ticker in SYMBOL_MAP.items():
            if re.match(pattern, raw_clean):
                return ticker

    # Try base symbol map
    clean = symbol.strip().upper()
    if clean in BASE_SYMBOL_MAP:
        return BASE_SYMBOL_MAP[clean]

    # Fallback: append =F for futures
    return f"{clean}=F"
