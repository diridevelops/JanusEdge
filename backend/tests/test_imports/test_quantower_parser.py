"""Tests for Quantower CSV parser."""

import os

from app.imports.parsers.quantower import (
    QuantowerParser,
)


EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "trade_examples",
)


class TestQuantowerParser:
    """Tests for QuantowerParser."""

    def setup_method(self):
        self.parser = QuantowerParser()

    def _load_csv(self, filename: str) -> str:
        path = os.path.join(
            EXAMPLES_DIR, "Quantower", filename
        )
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()

    def test_detect_valid_file(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        assert self.parser.detect(content) is True

    def test_detect_invalid_file(self):
        content = (
            "Instrument;Action;Quantity\n"
            "MES;Buy;1\n"
        )
        assert self.parser.detect(content) is False

    def test_parse_example1_returns_executions(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        assert result.platform == "quantower"
        assert len(result.executions) > 0
        assert len(result.errors) == 0

    def test_parse_example1_execution_fields(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        # Find a Buy execution
        buys = [
            e for e in result.executions
            if e.side == "Buy"
        ]
        assert len(buys) > 0

        ex = buys[0]
        assert ex.symbol == "MES"
        assert ex.raw_symbol == "MESM25"
        assert ex.side == "Buy"
        assert ex.quantity > 0
        assert ex.price > 0
        assert ex.account == "111222"

    def test_parse_example2_returns_executions(self):
        content = self._load_csv(
            "Quantower example2.csv"
        )
        result = self.parser.parse(content)
        assert result.platform == "quantower"
        assert len(result.executions) > 0
        assert len(result.errors) == 0

    def test_parse_example3_returns_executions(self):
        content = self._load_csv(
            "Quantower example3.csv"
        )
        result = self.parser.parse(content)
        assert result.platform == "quantower"
        assert len(result.executions) > 0

    def test_parse_quoted_decimal(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        ex = result.executions[0]
        # Quantower prices like "5634,5" → 5634.5
        assert isinstance(ex.price, float)
        assert ex.price > 1000

    def test_parse_negative_quantity_is_sell(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        sells = [
            e for e in result.executions
            if e.side == "Sell"
        ]
        for s in sells:
            assert s.quantity > 0  # Should be abs()

    def test_parse_timezone_offset(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        ex = result.executions[0]
        # Timestamps should be converted to UTC
        assert "+00:00" in ex.timestamp or "Z" in ex.timestamp

    def test_column_mapping_present(self):
        content = self._load_csv(
            "Quantower example1.csv"
        )
        result = self.parser.parse(content)
        assert "Account" in result.column_mapping
        assert "Symbol" in result.column_mapping
