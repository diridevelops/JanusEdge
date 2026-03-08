"""NinjaTrader CSV parser."""

import csv
import io
import re
from datetime import datetime, timezone
from typing import Iterable, List, Tuple

from app.imports.parsers.base import (
    BaseParser,
    ParsedExecution,
    ParseError,
    ParseResult,
)


class NinjaTraderParser(BaseParser):
    """
    Parser for NinjaTrader execution CSV files.

    Supports both legacy semicolon-delimited exports with
    comma decimals and newer comma-delimited exports with
    dot decimals. Timestamps use DD/MM/YYYY HH:mm:ss.
    """

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
        first_line = content.splitlines()[0].strip() if content else ""
        if not first_line:
            return False

        return all(
            h in first_line
            for h in self.EXPECTED_HEADERS
        ) and any(
            delimiter in first_line
            for delimiter in (";", ",")
        )

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

        lines = [
            line.rstrip()
            for line in content.splitlines()
            if line.strip()
        ]
        if not lines:
            return ParseResult(
                platform="ninjatrader",
                executions=[],
                errors=[],
                warnings=["Empty file"],
                row_count=0,
            )

        delimiter = self._detect_delimiter(lines[0])
        headers, rows = self._parse_rows(lines, delimiter)

        column_mapping = {h: h for h in headers}
        row_count = len(rows)

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

        for row_num, fields in enumerate(rows, start=2):
            raw_row = delimiter.join(fields)

            if len(fields) < len(headers):
                errors.append(ParseError(
                    row_number=row_num,
                    field="",
                    message="Insufficient columns",
                    raw_value=raw_row,
                ))
                continue

            row = dict(zip(headers, fields[:len(headers)]))

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
                    raw_value=raw_row,
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

    def _detect_delimiter(self, header_line: str) -> str:
        """
        Determine the CSV delimiter from the header row.

        Parameters:
            header_line: First non-empty line of the CSV.

        Returns:
            The detected delimiter.
        """
        comma_count = header_line.count(",")
        semicolon_count = header_line.count(";")
        if semicolon_count > comma_count:
            return ";"
        return ","

    def _parse_rows(
        self, lines: List[str], delimiter: str
    ) -> Tuple[List[str], List[List[str]]]:
        """
        Parse CSV lines into a header and data rows.

        Parameters:
            lines: Non-empty CSV lines.
            delimiter: Detected CSV delimiter.

        Returns:
            Tuple of headers and row fields.
        """
        normalized_lines = [
            self._strip_trailing_delimiter(line, delimiter)
            for line in lines
        ]
        reader = csv.reader(
            io.StringIO("\n".join(normalized_lines)),
            delimiter=delimiter,
        )
        rows = list(reader)
        headers = [cell.strip() for cell in rows[0]]
        data_rows = [
            [cell.strip() for cell in row]
            for row in rows[1:]
            if self._row_has_values(row)
        ]
        return headers, data_rows

    def _strip_trailing_delimiter(
        self, line: str, delimiter: str
    ) -> str:
        """
        Remove a trailing delimiter added by some exports.

        Parameters:
            line: Raw CSV line.
            delimiter: Active CSV delimiter.

        Returns:
            Normalized line without the trailing delimiter.
        """
        stripped = line.strip()
        if stripped.endswith(delimiter):
            return stripped[:-1]
        return stripped

    def _row_has_values(self, row: Iterable[str]) -> bool:
        """
        Check whether a parsed CSV row has any non-empty cells.

        Parameters:
            row: Parsed CSV row values.

        Returns:
            True when the row contains data.
        """
        return any(cell.strip() for cell in row)

    def _parse_decimal(self, raw: str) -> float:
        """
        Parse a decimal value from either export format.

        Parameters:
            raw: String like '6925,50' or '6734.00'.

        Returns:
            Float value.
        """
        cleaned = raw.strip().replace(",", ".")
        return float(cleaned)

    def _parse_commission(self, raw: str) -> float:
        """
        Parse NinjaTrader commission format.

        Handles legacy values like '0,39 $' and newer
        compact values like '039 $'.

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
        if (
            "," not in cleaned
            and "." not in cleaned
            and cleaned.startswith("0")
            and len(cleaned) > 1
        ):
            cleaned = f"0.{cleaned[1:]}"
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
