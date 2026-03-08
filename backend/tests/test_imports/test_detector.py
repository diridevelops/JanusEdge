"""Tests for platform detection."""

import os

from app.imports.parsers.detector import PlatformDetector
from app.imports.parsers.ninjatrader import (
    NinjaTraderParser,
)
from app.imports.parsers.quantower import (
    QuantowerParser,
)


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "trade_examples",
)


class TestPlatformDetector:
    """Tests for PlatformDetector."""

    def setup_method(self):
        self.detector = PlatformDetector()

    def test_detect_ninjatrader(self):
        path = os.path.join(
            EXAMPLES_DIR,
            "NinjaTrader",
            "NinjaTrader Grid example1.csv",
        )
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        parser = self.detector.detect(content)
        assert parser is not None
        assert isinstance(parser, NinjaTraderParser)

    def test_detect_new_ninjatrader_format(self):
        path = os.path.join(
            EXAMPLES_DIR,
            "NinjaTrader",
            "NinjaTrader Grid example3.csv",
        )
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        parser = self.detector.detect(content)
        assert parser is not None
        assert isinstance(parser, NinjaTraderParser)

    def test_detect_quantower(self):
        path = os.path.join(
            EXAMPLES_DIR,
            "Quantower",
            "Quantower example1.csv",
        )
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        parser = self.detector.detect(content)
        assert parser is not None
        assert isinstance(parser, QuantowerParser)

    def test_detect_unknown_returns_none(self):
        content = "col1,col2,col3\na,b,c\n"
        parser = self.detector.detect(content)
        assert parser is None
