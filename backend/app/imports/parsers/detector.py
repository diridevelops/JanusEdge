"""Platform auto-detection for CSV files."""

from typing import Optional

from app.imports.parsers.base import BaseParser
from app.imports.parsers.ninjatrader import (
    NinjaTraderParser,
)
from app.imports.parsers.quantower import QuantowerParser


class PlatformDetector:
    """
    Detect trading platform from CSV content.

    Tries each registered parser's detect() method.
    """

    def __init__(self):
        self.parsers = [
            NinjaTraderParser(),
            QuantowerParser(),
        ]

    def detect(self, content: str) -> Optional[BaseParser]:
        """
        Detect the platform and return parser.

        Parameters:
            content: Raw CSV file content.

        Returns:
            The matching parser instance, or None.
        """
        for parser in self.parsers:
            if parser.detect(content):
                return parser
        return None

    def get_supported_platforms(self):
        """Return list of supported platform names."""
        return ["ninjatrader", "quantower"]
