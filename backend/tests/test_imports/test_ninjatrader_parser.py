"""Tests for NinjaTrader CSV parser."""

import os

from app.imports.parsers.ninjatrader import (
    NinjaTraderParser,
)


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "trade_examples",
)


class TestNinjaTraderParser:
    """Tests for NinjaTraderParser."""

    def setup_method(self):
        self.parser = NinjaTraderParser()

    def _load_csv(self, filename: str) -> str:
        path = os.path.join(
            EXAMPLES_DIR, "NinjaTrader", filename
        )
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()

    def test_detect_valid_file(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        assert self.parser.detect(content) is True

    def test_detect_new_grid_format(self):
        content = self._load_csv(
            "NinjaTrader Grid example3.csv"
        )
        assert self.parser.detect(content) is True

    def test_detect_invalid_file(self):
        content = "col1,col2\na,b\n"
        assert self.parser.detect(content) is False

    def test_parse_example1_returns_executions(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        assert result.platform == "ninjatrader"
        assert len(result.executions) > 0
        assert len(result.errors) == 0

    def test_parse_example1_execution_fields(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        ex = result.executions[0]

        assert ex.symbol == "MES"
        assert ex.raw_symbol == "MES 03-26"
        assert ex.side == "Buy"
        assert ex.quantity == 1
        assert ex.price == 6925.50
        assert ex.commission == 0.39
        assert ex.account == "FNFTCH"

    def test_parse_date_dd_mm_yyyy(self):
        """Verify DD/MM/YYYY parsing: 04/02/2026 is Feb 4th."""
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        # First execution: 04/02/2026 10:05:21 ET
        ts = result.executions[0].timestamp
        # Converted to UTC: Feb 4th 2026 15:05:21
        assert ts.startswith("2026-02-04T")
        assert "2026-04-02" not in ts

    def test_parse_example1_four_executions(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        assert len(result.executions) == 4

    def test_parse_example2_returns_executions(self):
        content = self._load_csv(
            "NinjaTrader Grid example2.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        assert result.platform == "ninjatrader"
        assert len(result.executions) > 0
        assert len(result.errors) == 0

    def test_parse_example3_returns_executions(self):
        """Parse the newer comma-delimited NinjaTrader export."""
        content = self._load_csv(
            "NinjaTrader Grid example3.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        assert result.platform == "ninjatrader"
        assert len(result.executions) == 8
        assert len(result.errors) == 0

    def test_parse_example3_execution_fields(self):
        """The new format keeps the same semantic fields."""
        content = self._load_csv(
            "NinjaTrader Grid example3.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        ex = result.executions[0]

        assert ex.symbol == "MES"
        assert ex.raw_symbol == "MES 03-26"
        assert ex.side == "Buy"
        assert ex.quantity == 1
        assert ex.price == 6734.00
        assert ex.commission == 0.39
        assert ex.account == "FNFTCH"

    def test_parse_decimal_comma_to_dot(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        # NinjaTrader uses comma decimal: 6925,50
        ex = result.executions[0]
        assert ex.price == 6925.50

    def test_parse_commission_format(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        # Commission format: "0,39 $"
        ex = result.executions[0]
        assert ex.commission == 0.39

    def test_parse_compact_commission_format(self):
        """A leading zero without a separator means a decimal fee."""
        content = self._load_csv(
            "NinjaTrader Grid example3.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        ex = result.executions[0]
        assert ex.commission == 0.39

    def test_parse_empty_content(self):
        result = self.parser.parse("", "America/New_York")
        assert len(result.executions) == 0

    def test_column_mapping_present(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(
            content, "America/New_York"
        )
        assert "Instrument" in result.column_mapping
        assert "Action" in result.column_mapping

    def test_parse_without_timezone(self):
        content = self._load_csv(
            "NinjaTrader Grid example1.csv"
        )
        result = self.parser.parse(content)
        assert len(result.executions) > 0
