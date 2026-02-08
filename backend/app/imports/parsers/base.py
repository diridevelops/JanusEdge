"""Abstract base parser for CSV files."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ParsedExecution:
    """A single parsed execution from a CSV row."""

    symbol: str
    raw_symbol: str
    side: str  # 'Buy' or 'Sell'
    quantity: int
    price: float
    timestamp: str  # ISO format string
    platform_execution_id: str = ""
    platform_order_id: str = ""
    order_type: str = ""
    entry_exit: str = ""  # 'Entry' or 'Exit'
    commission: float = 0.0
    account: str = ""
    connection: str = ""
    raw_data: dict = field(default_factory=dict)


@dataclass
class ParseError:
    """A row-level parse error."""

    row_number: int
    field: str
    message: str
    raw_value: str = ""


@dataclass
class ParseResult:
    """Result of parsing a CSV file."""

    platform: str
    executions: List[ParsedExecution]
    errors: List[ParseError]
    warnings: List[str]
    row_count: int
    column_mapping: dict = field(default_factory=dict)


class BaseParser(ABC):
    """
    Abstract base parser for trading platform CSVs.

    Subclasses must implement detect() and parse().
    """

    @abstractmethod
    def detect(self, content: str) -> bool:
        """
        Check if this parser can handle the content.

        Parameters:
            content: Raw CSV file content.

        Returns:
            True if this parser should handle the file.
        """
        pass

    @abstractmethod
    def parse(
        self, content: str, user_timezone: str = None
    ) -> ParseResult:
        """
        Parse CSV content into executions.

        Parameters:
            content: Raw CSV file content.
            user_timezone: User's trading timezone.

        Returns:
            ParseResult with executions and errors.
        """
        pass

    def _normalize_symbol(self, raw: str) -> str:
        """
        Extract base symbol from platform-specific format.

        Parameters:
            raw: Raw symbol like 'MES 03-26' or 'MESM25'.

        Returns:
            Normalized symbol like 'MES'.
        """
        import re
        raw = raw.strip()
        # NinjaTrader: "MES 03-26" -> "MES"
        match = re.match(r'^([A-Z]+)\s+\d{2}-\d{2}$', raw)
        if match:
            return match.group(1)
        # Quantower: "MESM25" -> "MES"
        match = re.match(
            r'^([A-Z]+)[FGHJKMNQUVXZ]\d{2}$', raw
        )
        if match:
            return match.group(1)
        # Fallback: return as-is
        return raw
