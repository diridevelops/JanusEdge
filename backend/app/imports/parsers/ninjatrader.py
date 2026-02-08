"""NinjaTrader CSV parser."""

import csv
import io
import re
from datetime import datetime, timezone

from app.imports.parsers.base import (
    BaseParser,
    ParsedExecution,
    ParseError,
    ParseResult,
)


class NinjaTraderParser(BaseParser):
    """
    Parser for NinjaTrader execution CSV files.

    Format: semicolon delimited, comma decimal separator,
    DD/MM/YYYY HH:mm:ss timestamps (no timezone).
    """

    DELIMITER = ";"
    EXPECTED_HEADERS = [
        "Instrument", "Action", "Quantity", "Price",
        "Time", "ID", "E/X",
    ]

    def detect(self, content: str) -> bool:
        """
        Detect NinjaTrader CSV by header pattern.

        Parameters:
            content: Raw CSV file content.

        Returns:
            True if headers match NinjaTrader format.
        """
        first_line = content.split("\n")[0].strip()
        return all(
            h in first_line
            for h in self.EXPECTED_HEADERS
        ) and ";" in first_line

    def parse(
        self, content: str, user_timezone: str = None
    ) -> ParseResult:
        """
        Parse a NinjaTrader CSV file.

        Parameters:
            content: Raw CSV file content.
            user_timezone: User's trading timezone for
                timestamp interpretation.

        Returns:
            ParseResult with executions and errors.
        """
        executions = []
        errors = []
        warnings = []

        lines = content.strip().split("\n")
        if not lines:
            return ParseResult(
                platform="ninjatrader",
                executions=[],
                errors=[],
                warnings=["Empty file"],
                row_count=0,
            )

        # Parse header
        header_line = lines[0].strip().rstrip(";")
        headers = [
            h.strip() for h in header_line.split(";")
        ]

        column_mapping = {h: h for h in headers}
        row_count = len(lines) - 1

        # Get timezone info for conversions
        tz_info = None
        if user_timezone:
            try:
                import pytz
                tz_info = pytz.timezone(user_timezone)
            except Exception:
                warnings.append(
                    f"Invalid timezone: {user_timezone}"
                )

        for row_num, line in enumerate(
            lines[1:], start=2
        ):
            line = line.strip()
            if not line or line == ";":
                continue

            # Strip trailing semicolons
            line = line.rstrip(";")
            fields = line.split(";")

            if len(fields) < len(headers):
                errors.append(ParseError(
                    row_number=row_num,
                    field="",
                    message="Insufficient columns",
                    raw_value=line,
                ))
                continue

            row = dict(zip(headers, fields))

            try:
                execution = self._parse_row(
                    row, row_num, tz_info
                )
                executions.append(execution)
            except Exception as e:
                errors.append(ParseError(
                    row_number=row_num,
                    field="",
                    message=str(e),
                    raw_value=line,
                ))

        return ParseResult(
            platform="ninjatrader",
            executions=executions,
            errors=errors,
            warnings=warnings,
            row_count=row_count,
            column_mapping=column_mapping,
        )

    def _parse_row(
        self, row: dict, row_num: int, tz_info
    ) -> ParsedExecution:
        """
        Parse a single NinjaTrader CSV row.

        Parameters:
            row: Dict of column name to value.
            row_num: Row number for error reporting.
            tz_info: pytz timezone for timestamp.

        Returns:
            ParsedExecution instance.
        """
        raw_symbol = row.get("Instrument", "").strip()
        symbol = self._normalize_symbol(raw_symbol)

        side = row.get("Action", "").strip()
        if side not in ("Buy", "Sell"):
            raise ValueError(
                f"Invalid action: {side}"
            )

        quantity = int(
            row.get("Quantity", "0").strip()
            .replace(",", ".")
        )

        price = self._parse_decimal(
            row.get("Price", "0")
        )

        timestamp_str = row.get("Time", "").strip()
        timestamp = self._parse_timestamp(
            timestamp_str, tz_info
        )

        execution_id = row.get("ID", "").strip()
        entry_exit = row.get("E/X", "").strip()
        order_id = row.get("Order ID", "").strip()
        commission = self._parse_commission(
            row.get("Commission", "0")
        )
        account = row.get("Account", "").strip()
        connection = row.get("Connection", "").strip()

        return ParsedExecution(
            symbol=symbol,
            raw_symbol=raw_symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=timestamp.isoformat(),
            platform_execution_id=execution_id,
            platform_order_id=order_id,
            order_type="",
            entry_exit=entry_exit,
            commission=commission,
            account=account,
            connection=connection,
            raw_data=dict(row),
        )

    def _parse_decimal(self, raw: str) -> float:
        """
        Parse European-format decimal (comma separator).

        Parameters:
            raw: String like '6925,50'.

        Returns:
            Float value.
        """
        cleaned = raw.strip().replace(",", ".")
        return float(cleaned)

    def _parse_commission(self, raw: str) -> float:
        """
        Parse NinjaTrader commission format.

        Handles format like '0,39 $'.

        Parameters:
            raw: Raw commission string.

        Returns:
            Float commission value.
        """
        cleaned = raw.strip()
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[^\d,.\-]', '', cleaned)
        if not cleaned:
            return 0.0
        cleaned = cleaned.replace(",", ".")
        return float(cleaned)

    def _parse_timestamp(
        self, raw: str, tz_info
    ) -> datetime:
        """
        Parse NinjaTrader timestamp.

        Format: DD/MM/YYYY HH:mm:ss (no timezone).
        Timestamps are interpreted in the user's timezone,
        then converted to UTC.

        Parameters:
            raw: Timestamp string.
            tz_info: pytz timezone object.

        Returns:
            UTC datetime.
        """
        dt = datetime.strptime(
            raw.strip(), "%d/%m/%Y %H:%M:%S"
        )

        if tz_info:
            dt = tz_info.localize(dt)
            dt = dt.astimezone(timezone.utc)
        else:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
