"""Quantower CSV parser."""

import csv
import io
import re
from datetime import datetime, timezone, timedelta

from app.imports.parsers.base import (
    BaseParser,
    ParsedExecution,
    ParseError,
    ParseResult,
)


class QuantowerParser(BaseParser):
    """
    Parser for Quantower execution CSV files.

    Format: comma delimited, comma decimals in quoted
    fields, DD/MM/YYYY HH:mm:ss with timezone offsets.
    """

    DELIMITER = ","
    EXPECTED_HEADERS = [
        "Account", "Date/Time", "Symbol", "Side",
        "Quantity", "Price",
    ]

    def detect(self, content: str) -> bool:
        """
        Detect Quantower CSV by header pattern.

        Parameters:
            content: Raw CSV file content.

        Returns:
            True if headers match Quantower format.
        """
        first_line = content.split("\n")[0].strip()
        return (
            "Date/Time" in first_line
            and "Symbol" in first_line
            and "Side" in first_line
            and ";" not in first_line
        )

    def parse(
        self, content: str, user_timezone: str = None
    ) -> ParseResult:
        """
        Parse a Quantower CSV file.

        Parameters:
            content: Raw CSV file content.
            user_timezone: Not used — Quantower has offset.

        Returns:
            ParseResult with executions and errors.
        """
        executions = []
        errors = []
        warnings = []

        reader = csv.DictReader(
            io.StringIO(content), delimiter=","
        )
        headers = reader.fieldnames or []
        column_mapping = {h: h for h in headers}

        row_count = 0
        for row_num, row in enumerate(reader, start=2):
            row_count += 1
            try:
                execution = self._parse_row(row, row_num)
                executions.append(execution)
            except Exception as e:
                errors.append(ParseError(
                    row_number=row_num,
                    field="",
                    message=str(e),
                    raw_value=str(row),
                ))

        return ParseResult(
            platform="quantower",
            executions=executions,
            errors=errors,
            warnings=warnings,
            row_count=row_count,
            column_mapping=column_mapping,
        )

    def _parse_row(
        self, row: dict, row_num: int
    ) -> ParsedExecution:
        """
        Parse a single Quantower CSV row.

        Parameters:
            row: Dict of column name to value.
            row_num: Row number for error reporting.

        Returns:
            ParsedExecution instance.
        """
        raw_symbol = row.get("Symbol", "").strip()
        symbol = self._normalize_symbol(raw_symbol)

        side = row.get("Side", "").strip()
        if side not in ("Buy", "Sell"):
            raise ValueError(f"Invalid side: {side}")

        quantity_raw = row.get("Quantity", "0").strip()
        quantity = abs(int(
            self._parse_decimal(quantity_raw)
        ))

        price = self._parse_decimal(
            row.get("Price", "0")
        )

        timestamp_str = row.get("Date/Time", "").strip()
        timestamp = self._parse_timestamp(timestamp_str)

        account = row.get("Account", "").strip()
        order_type = row.get("Order type", "").strip()
        trade_id = row.get("Trade ID", "").strip()
        order_id = row.get("Order ID", "").strip()
        connection = row.get(
            "Connection name", ""
        ).strip()

        fee = self._parse_decimal(
            row.get("Fee", "0")
        )
        gross_pnl = self._parse_decimal(
            row.get("Gross P/L", "0")
        )

        return ParsedExecution(
            symbol=symbol,
            raw_symbol=raw_symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=timestamp.isoformat(),
            platform_execution_id=trade_id,
            platform_order_id=order_id,
            order_type=order_type,
            entry_exit="",
            commission=abs(fee),
            account=account,
            connection=connection,
            raw_data={
                k: v for k, v in row.items() if v
            },
        )

    def _parse_decimal(self, raw: str) -> float:
        """
        Parse Quantower decimal format.

        Handles quoted fields with comma decimals.

        Parameters:
            raw: String like '"5634,5"' or '5634.5'.

        Returns:
            Float value.
        """
        cleaned = raw.strip().strip('"')
        if not cleaned or cleaned == "":
            return 0.0
        cleaned = cleaned.replace(",", ".")
        return float(cleaned)

    def _parse_timestamp(self, raw: str) -> datetime:
        """
        Parse Quantower timestamp with timezone offset.

        Format: DD/MM/YYYY HH:mm:ss ±HH:mm

        Parameters:
            raw: Timestamp string with offset.

        Returns:
            UTC datetime.
        """
        raw = raw.strip()

        # Match: DD/MM/YYYY HH:mm:ss ±HH:mm
        match = re.match(
            r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})'
            r'\s+([+-]\d{2}:\d{2})',
            raw,
        )

        if match:
            dt_str = match.group(1)
            offset_str = match.group(2)

            dt = datetime.strptime(
                dt_str, "%d/%m/%Y %H:%M:%S"
            )

            # Parse offset (e.g., -05:00)
            sign = 1 if offset_str[0] == '+' else -1
            parts = offset_str[1:].split(":")
            offset_hours = int(parts[0])
            offset_mins = int(parts[1])
            offset = timedelta(
                hours=sign * offset_hours,
                minutes=sign * offset_mins,
            )

            tz = timezone(offset)
            dt = dt.replace(tzinfo=tz)
            return dt.astimezone(timezone.utc)

        # Fallback: no timezone offset
        dt = datetime.strptime(
            raw, "%d/%m/%Y %H:%M:%S"
        )
        return dt.replace(tzinfo=timezone.utc)
