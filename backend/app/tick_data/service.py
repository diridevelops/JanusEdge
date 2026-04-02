"""Services for importing and reading NinjaTrader tick data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from io import TextIOWrapper
import os
from pathlib import Path
import tempfile
import threading
from typing import BinaryIO
from typing import Mapping

import pandas as pd
from bson import ObjectId
from flask import current_app

from app.market_data.symbol_mapper import (
    resolve_market_data_symbol,
    resolve_market_data_symbols,
)
from app.models.market_data import create_market_data_doc
from app.models.market_data_import_batch import (
    create_market_data_import_batch_doc,
)
from app.repositories.market_data_import_batch_repo import (
    MarketDataImportBatchRepository,
)
from app.repositories.market_data_repo import MarketDataRepository
from app.tick_data.candles import (
    SUPPORTED_CANDLE_TIMEFRAMES,
    build_candles_from_ticks,
)
from app.tick_data.ninjatrader import (
    NinjaTraderTick,
    parse_ninjatrader_tick_line,
)
from app.tick_data.parquet_store import MarketDataParquetStore
from app.utils.errors import NotFoundError
from app.utils.errors import ValidationError


_PROGRESS_UPDATE_LINE_INTERVAL = 5000


@dataclass(frozen=True, slots=True)
class TickImportPreviewSummary:
    """Structured preview details for an uploaded tick-data file."""

    file_name: str
    symbol_guess: str | None
    total_lines: int
    valid_ticks: int
    skipped_lines: int
    first_tick_at: str | None
    last_tick_at: str | None
    trading_dates: list[dict]

    def to_dict(self) -> dict:
        """Serialize the preview for API responses."""

        return {
            "file_name": self.file_name,
            "symbol_guess": self.symbol_guess,
            "total_lines": self.total_lines,
            "valid_ticks": self.valid_ticks,
            "skipped_lines": self.skipped_lines,
            "first_tick_at": self.first_tick_at,
            "last_tick_at": self.last_tick_at,
            "trading_dates": self.trading_dates,
        }


class TickDataService:
    """Application service for tick-data ingestion primitives."""

    def __init__(self) -> None:
        self.dataset_repo = MarketDataRepository()
        self.import_batch_repo = (
            MarketDataImportBatchRepository()
        )
        self.parquet_store = MarketDataParquetStore()

    def preview_ninjatrader_upload(
        self,
        *,
        file_name: str,
        file_stream: BinaryIO,
    ) -> TickImportPreviewSummary:
        """Parse a text upload and return a daily summary preview."""

        if not file_name:
            raise ValidationError("File name is required.")

        day_summary: dict[date, dict] = {}
        first_tick: NinjaTraderTick | None = None
        last_tick: NinjaTraderTick | None = None
        total_lines = 0
        valid_ticks = 0
        skipped_lines = 0

        for line in self._iter_decoded_lines(file_stream):
            total_lines += 1
            if not line.strip():
                skipped_lines += 1
                continue

            try:
                tick = parse_ninjatrader_tick_line(line)
            except ValueError:
                skipped_lines += 1
                continue

            valid_ticks += 1
            if first_tick is None:
                first_tick = tick
            last_tick = tick

            trading_date = tick.timestamp.date()
            summary = day_summary.setdefault(
                trading_date,
                {
                    "date": trading_date.isoformat(),
                    "tick_count": 0,
                    "first_tick_at": tick.timestamp.isoformat(),
                    "last_tick_at": tick.timestamp.isoformat(),
                },
            )
            summary["tick_count"] += 1
            summary["last_tick_at"] = tick.timestamp.isoformat()

        if valid_ticks == 0:
            if total_lines == 0:
                raise ValidationError("File is empty.")
            raise ValidationError(
                "No valid NinjaTrader tick rows were found in the file."
            )

        trading_dates = [
            day_summary[current_date]
            for current_date in sorted(day_summary)
        ]

        return TickImportPreviewSummary(
            file_name=file_name,
            symbol_guess=self._guess_symbol(file_name),
            total_lines=total_lines,
            valid_ticks=valid_ticks,
            skipped_lines=skipped_lines,
            first_tick_at=(
                first_tick.timestamp.isoformat()
                if first_tick is not None
                else None
            ),
            last_tick_at=(
                last_tick.timestamp.isoformat()
                if last_tick is not None
                else None
            ),
            trading_dates=trading_dates,
        )

    def start_ninjatrader_import(
        self,
        *,
        user_id: str,
        file_name: str,
        file_stream: BinaryIO,
        symbol: str | None = None,
        raw_symbol: str | None = None,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> dict:
        """Persist an upload to a temp file and start background import."""

        if not file_name:
            raise ValidationError("File name is required.")

        temp_path, file_hash, file_size = self._store_upload(
            file_stream
        )
        if file_size == 0:
            os.unlink(temp_path)
            raise ValidationError("File is empty.")

        guessed_raw_symbol = raw_symbol or self._guess_raw_symbol(
            file_name
        )
        base_symbol = symbol or self._guess_symbol(file_name)
        dataset_symbol = resolve_market_data_symbol(
            base_symbol or guessed_raw_symbol or "",
            guessed_raw_symbol,
            market_data_mappings,
        )
        if not dataset_symbol:
            os.unlink(temp_path)
            raise ValidationError(
                "Unable to determine the market-data symbol."
            )

        batch_doc = create_market_data_import_batch_doc(
            user_id=ObjectId(user_id),
            file_name=file_name,
            file_hash=file_hash,
            file_size_bytes=file_size,
            symbol=dataset_symbol,
            raw_symbol=guessed_raw_symbol,
        )
        batch_id = self.import_batch_repo.insert_one(batch_doc)

        app = current_app._get_current_object()
        worker = threading.Thread(
            target=self._run_import_batch,
            kwargs={
                "app": app,
                "batch_id": batch_id,
                "temp_path": temp_path,
                "symbol": dataset_symbol,
                "raw_symbol": guessed_raw_symbol,
                "file_name": file_name,
                "file_size": file_size,
            },
            daemon=True,
        )
        worker.start()
        return self.get_import_batch(
            user_id=user_id,
            batch_id=batch_id,
        )

    def start_ninjatrader_preview(
        self,
        *,
        user_id: str,
        file_name: str,
        file_stream: BinaryIO,
    ) -> dict:
        """Persist an upload and start a background preview batch."""

        if not file_name:
            raise ValidationError("File name is required.")

        temp_path, file_hash, file_size = self._store_upload(
            file_stream
        )
        if file_size == 0:
            os.unlink(temp_path)
            raise ValidationError("File is empty.")

        guessed_raw_symbol = self._guess_raw_symbol(file_name)
        guessed_symbol = self._guess_symbol(file_name)
        batch_doc = create_market_data_import_batch_doc(
            user_id=ObjectId(user_id),
            file_name=file_name,
            file_hash=file_hash,
            file_size_bytes=file_size,
            symbol=guessed_symbol or guessed_raw_symbol or "",
            raw_symbol=guessed_raw_symbol,
            batch_type="preview",
        )
        batch_id = self.import_batch_repo.insert_one(batch_doc)

        app = current_app._get_current_object()
        worker = threading.Thread(
            target=self._run_preview_batch,
            kwargs={
                "app": app,
                "batch_id": batch_id,
                "temp_path": temp_path,
                "file_name": file_name,
                "file_size": file_size,
            },
            daemon=True,
        )
        worker.start()
        return self.get_preview_batch(
            user_id=user_id,
            batch_id=batch_id,
        )

    def get_import_batch(
        self,
        *,
        user_id: str,
        batch_id: str,
    ) -> dict:
        """Return one import batch for the authenticated user."""

        batch = self.import_batch_repo.find_by_user_and_id(
            user_id=user_id,
            batch_id=batch_id,
            batch_type="import",
        )
        if batch is None:
            raise NotFoundError("Tick-data import batch not found.")
        return self.import_batch_repo.serialize_doc(batch)

    def get_preview_batch(
        self,
        *,
        user_id: str,
        batch_id: str,
    ) -> dict:
        """Return one preview batch for the authenticated user."""

        batch = self.import_batch_repo.find_by_user_and_id(
            user_id=user_id,
            batch_id=batch_id,
            batch_type="preview",
        )
        if batch is None:
            raise NotFoundError("Tick-data preview batch not found.")
        return self.import_batch_repo.serialize_doc(batch)

    def get_ohlc(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        interval: str,
        start_dt: datetime,
        end_dt: datetime,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> list[dict]:
        """Read candle bars from stored Parquet datasets."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        start_date = start_dt.date()
        end_date = end_dt.date()

        if interval == "1d":
            return self._read_daily_bars(
                symbols=dataset_symbols,
                start_dt=start_dt,
                end_dt=end_dt,
            )

        documents = self.dataset_repo.find_cached(
            dataset_symbols,
            interval,
            start_date,
            end_date,
        )
        bars: list[dict] = []
        for document in documents:
            frame = self.parquet_store.read_dataframe(
                document["object_key"]
            )
            if frame.empty:
                continue
            bars.extend(
                self._frame_to_ohlc_records(frame)
            )

        return self._filter_bars_by_range(
            bars,
            start_dt=start_dt,
            end_dt=end_dt,
        )

    def has_ohlc_for_day(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        interval: str,
        trading_day: date,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> bool:
        """Return True when market data is available for a day."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        if interval == "1d":
            return (
                self.dataset_repo.find_dataset(
                    dataset_symbols,
                    "ticks",
                    trading_day,
                    None,
                )
                is not None
            )

        return self.dataset_repo.has_cached_day(
            dataset_symbols,
            interval,
            trading_day,
        )

    def refresh_ohlc(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        start_date: date,
        end_date: date,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> None:
        """Regenerate stored candle datasets from raw tick datasets."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        dataset_symbol = dataset_symbols[0]
        current_day = start_date
        while current_day <= end_date:
            tick_document = self.dataset_repo.find_dataset(
                dataset_symbols,
                "ticks",
                current_day,
                None,
            )
            if tick_document is not None:
                ticks_frame = self.parquet_store.read_dataframe(
                    tick_document["object_key"]
                )
                self._write_candle_datasets(
                    symbol=dataset_symbol,
                    raw_symbol=tick_document.get("raw_symbol"),
                    trading_day=current_day,
                    ticks_frame=ticks_frame,
                    source_file_name=tick_document.get(
                        "source_file_name", ""
                    ),
                    import_batch_id=tick_document.get(
                        "import_batch_id"
                    ),
                )
            current_day += timedelta(days=1)

    def has_ticks_for_day(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        trading_day: date,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> bool:
        """Return True when raw tick data is available for a day."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        return (
            self.dataset_repo.find_dataset(
                dataset_symbols,
                "ticks",
                trading_day,
                None,
            )
            is not None
        )

    def read_bars_for_day(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        interval: str,
        trading_day: date,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> list[dict]:
        """Read all bars for one UTC trading day."""

        start_dt = datetime.combine(
            trading_day,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        end_dt = start_dt + timedelta(days=1) - timedelta(seconds=1)
        return self.get_ohlc(
            symbol=symbol,
            raw_symbol=raw_symbol,
            interval=interval,
            start_dt=start_dt,
            end_dt=end_dt,
            market_data_mappings=market_data_mappings,
        )

    def read_ticks_for_day(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        trading_day: date,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> list[dict]:
        """Read all raw ticks for one UTC trading day."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        tick_document = self.dataset_repo.find_dataset(
            dataset_symbols,
            "ticks",
            trading_day,
            None,
        )
        if tick_document is None:
            return []

        frame = self.parquet_store.read_dataframe(
            tick_document["object_key"]
        )
        return self._frame_to_tick_records(frame)

    def read_tick_prices_for_range(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        start_dt: datetime,
        end_dt: datetime,
        market_data_mappings: Mapping[str, str] | None = None,
    ) -> tuple[list[tuple[datetime, float]], bool]:
        """Read only timestamp and last_price ticks for a UTC time range."""

        dataset_symbols = resolve_market_data_symbols(
            symbol,
            raw_symbol,
            market_data_mappings,
        )
        current_day = start_dt.date()
        last_day = end_dt.date()
        records: list[tuple[datetime, float]] = []

        while current_day <= last_day:
            tick_document = self.dataset_repo.find_dataset(
                dataset_symbols,
                "ticks",
                current_day,
                None,
            )
            if tick_document is None:
                return [], True

            frame = self.parquet_store.read_dataframe(
                tick_document["object_key"]
            )
            day_records = self._frame_to_tick_price_records(
                frame,
                start_dt=start_dt,
                end_dt=end_dt,
            )
            records.extend(day_records)
            current_day += timedelta(days=1)

        return records, False

    def _iter_decoded_lines(
        self,
        file_stream: BinaryIO,
    ):
        """Yield UTF-8 decoded lines from an uploaded file stream."""

        text_stream = TextIOWrapper(
            file_stream,
            encoding="utf-8-sig",
            newline=None,
        )
        try:
            for line in text_stream:
                yield line
        except UnicodeDecodeError as exc:
            raise ValidationError(
                "Tick data file must be valid UTF-8 text."
            ) from exc
        except OSError as exc:
            raise ValidationError(
                "Failed to read uploaded file."
            ) from exc
        finally:
            try:
                text_stream.detach()
            except Exception:
                pass

    def _store_upload(
        self,
        file_stream: BinaryIO,
    ) -> tuple[str, str, int]:
        """Persist an uploaded file to a temporary path and hash it."""

        hasher = hashlib.sha256()
        total_bytes = 0
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".txt",
        ) as temp_file:
            while True:
                chunk = file_stream.read(1024 * 1024)
                if not chunk:
                    break
                temp_file.write(chunk)
                hasher.update(chunk)
                total_bytes += len(chunk)

        return temp_file.name, hasher.hexdigest(), total_bytes

    def _run_import_batch(
        self,
        *,
        app,
        batch_id: str,
        temp_path: str,
        symbol: str,
        raw_symbol: str | None,
        file_name: str,
        file_size: int,
    ) -> None:
        """Process a temp upload into daily raw tick and candle datasets."""

        processed_lines = 0
        valid_ticks = 0
        skipped_lines = 0
        processed_bytes = 0
        days_completed = 0
        datasets_written = 0
        current_day: date | None = None
        current_rows: list[dict] = []
        decode_encoding = "utf-8-sig"

        with app.app_context():
            self.import_batch_repo.mark_processing(batch_id)
            try:
                with open(temp_path, "rb") as file_handle:
                    for raw_line in file_handle:
                        processed_bytes = file_handle.tell()
                        processed_lines += 1
                        try:
                            line = raw_line.decode(
                                decode_encoding
                            )
                        except UnicodeDecodeError as exc:
                            raise ValidationError(
                                "Tick data file must be valid UTF-8 text."
                            ) from exc
                        decode_encoding = "utf-8"

                        if not line.strip():
                            skipped_lines += 1
                            self._maybe_update_progress(
                                batch_id=batch_id,
                                processed_lines=processed_lines,
                                valid_ticks=valid_ticks,
                                skipped_lines=skipped_lines,
                                processed_bytes=processed_bytes,
                                total_bytes=file_size,
                                days_completed=days_completed,
                                datasets_written=datasets_written,
                            )
                            continue

                        try:
                            tick = parse_ninjatrader_tick_line(line)
                        except ValueError:
                            skipped_lines += 1
                            self._maybe_update_progress(
                                batch_id=batch_id,
                                processed_lines=processed_lines,
                                valid_ticks=valid_ticks,
                                skipped_lines=skipped_lines,
                                processed_bytes=processed_bytes,
                                total_bytes=file_size,
                                days_completed=days_completed,
                                datasets_written=datasets_written,
                            )
                            continue

                        tick_day = tick.timestamp.date()
                        if current_day is None:
                            current_day = tick_day
                        elif tick_day < current_day:
                            raise ValidationError(
                                "Tick data must be sorted by timestamp."
                            )
                        elif tick_day != current_day:
                            datasets_written += (
                                self._flush_daily_partition(
                                    symbol=symbol,
                                    raw_symbol=raw_symbol,
                                    trading_day=current_day,
                                    rows=current_rows,
                                    source_file_name=file_name,
                                    import_batch_id=batch_id,
                                )
                            )
                            days_completed += 1
                            current_day = tick_day
                            current_rows = []

                        current_rows.append(
                            self._tick_to_row(tick)
                        )
                        valid_ticks += 1
                        self._maybe_update_progress(
                            batch_id=batch_id,
                            processed_lines=processed_lines,
                            valid_ticks=valid_ticks,
                            skipped_lines=skipped_lines,
                            processed_bytes=processed_bytes,
                            total_bytes=file_size,
                            days_completed=days_completed,
                            datasets_written=datasets_written,
                        )

                if current_day is not None and current_rows:
                    datasets_written += self._flush_daily_partition(
                        symbol=symbol,
                        raw_symbol=raw_symbol,
                        trading_day=current_day,
                        rows=current_rows,
                        source_file_name=file_name,
                        import_batch_id=batch_id,
                    )
                    days_completed += 1

                if valid_ticks == 0:
                    raise ValidationError(
                        "No valid NinjaTrader tick rows were found in the file."
                    )

                self.import_batch_repo.mark_completed(
                    batch_id,
                    total_bytes=file_size,
                    processed_lines=processed_lines,
                    valid_ticks=valid_ticks,
                    skipped_lines=skipped_lines,
                    days_completed=days_completed,
                    datasets_written=datasets_written,
                )
            except Exception as exc:
                self.import_batch_repo.mark_failed(
                    batch_id,
                    error_message=str(exc),
                    processed_bytes=processed_bytes,
                    total_bytes=file_size,
                    processed_lines=processed_lines,
                    valid_ticks=valid_ticks,
                    skipped_lines=skipped_lines,
                    days_completed=days_completed,
                    datasets_written=datasets_written,
                )
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    def _run_preview_batch(
        self,
        *,
        app,
        batch_id: str,
        temp_path: str,
        file_name: str,
        file_size: int,
    ) -> None:
        """Process a temp upload into a preview summary batch."""

        processed_lines = 0
        valid_ticks = 0
        skipped_lines = 0
        processed_bytes = 0
        day_summary: dict[date, dict] = {}
        first_tick: NinjaTraderTick | None = None
        last_tick: NinjaTraderTick | None = None
        decode_encoding = "utf-8-sig"

        with app.app_context():
            self.import_batch_repo.mark_processing(batch_id)
            try:
                with open(temp_path, "rb") as file_handle:
                    for raw_line in file_handle:
                        processed_bytes = file_handle.tell()
                        processed_lines += 1
                        try:
                            line = raw_line.decode(
                                decode_encoding
                            )
                        except UnicodeDecodeError as exc:
                            raise ValidationError(
                                "Tick data file must be valid UTF-8 text."
                            ) from exc
                        decode_encoding = "utf-8"

                        if not line.strip():
                            skipped_lines += 1
                            self._maybe_update_progress(
                                batch_id=batch_id,
                                processed_lines=processed_lines,
                                valid_ticks=valid_ticks,
                                skipped_lines=skipped_lines,
                                processed_bytes=processed_bytes,
                                total_bytes=file_size,
                                days_completed=len(day_summary),
                                datasets_written=0,
                            )
                            continue

                        try:
                            tick = parse_ninjatrader_tick_line(line)
                        except ValueError:
                            skipped_lines += 1
                            self._maybe_update_progress(
                                batch_id=batch_id,
                                processed_lines=processed_lines,
                                valid_ticks=valid_ticks,
                                skipped_lines=skipped_lines,
                                processed_bytes=processed_bytes,
                                total_bytes=file_size,
                                days_completed=len(day_summary),
                                datasets_written=0,
                            )
                            continue

                        valid_ticks += 1
                        if first_tick is None:
                            first_tick = tick
                        last_tick = tick

                        trading_date = tick.timestamp.date()
                        summary = day_summary.setdefault(
                            trading_date,
                            {
                                "date": trading_date.isoformat(),
                                "tick_count": 0,
                                "first_tick_at": tick.timestamp.isoformat(),
                                "last_tick_at": tick.timestamp.isoformat(),
                            },
                        )
                        summary["tick_count"] += 1
                        summary["last_tick_at"] = (
                            tick.timestamp.isoformat()
                        )
                        self._maybe_update_progress(
                            batch_id=batch_id,
                            processed_lines=processed_lines,
                            valid_ticks=valid_ticks,
                            skipped_lines=skipped_lines,
                            processed_bytes=processed_bytes,
                            total_bytes=file_size,
                            days_completed=len(day_summary),
                            datasets_written=0,
                        )

                if processed_lines == 0:
                    raise ValidationError("File is empty.")

                if valid_ticks == 0:
                    raise ValidationError(
                        "No valid NinjaTrader tick rows were found in the file."
                    )

                trading_dates = [
                    day_summary[current_date]
                    for current_date in sorted(day_summary)
                ]
                preview = TickImportPreviewSummary(
                    file_name=file_name,
                    symbol_guess=self._guess_symbol(file_name),
                    total_lines=processed_lines,
                    valid_ticks=valid_ticks,
                    skipped_lines=skipped_lines,
                    first_tick_at=(
                        first_tick.timestamp.isoformat()
                        if first_tick is not None
                        else None
                    ),
                    last_tick_at=(
                        last_tick.timestamp.isoformat()
                        if last_tick is not None
                        else None
                    ),
                    trading_dates=trading_dates,
                )
                self.import_batch_repo.mark_preview_completed(
                    batch_id,
                    preview=preview.to_dict(),
                    total_bytes=file_size,
                    processed_lines=processed_lines,
                    valid_ticks=valid_ticks,
                    skipped_lines=skipped_lines,
                    days_completed=len(trading_dates),
                )
            except Exception as exc:
                self.import_batch_repo.mark_failed(
                    batch_id,
                    error_message=str(exc),
                    processed_bytes=processed_bytes,
                    total_bytes=file_size,
                    processed_lines=processed_lines,
                    valid_ticks=valid_ticks,
                    skipped_lines=skipped_lines,
                    days_completed=len(day_summary),
                    datasets_written=0,
                )
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    def _maybe_update_progress(
        self,
        *,
        batch_id: str,
        processed_lines: int,
        valid_ticks: int,
        skipped_lines: int,
        processed_bytes: int,
        total_bytes: int,
        days_completed: int,
        datasets_written: int,
    ) -> None:
        """Write periodic progress updates for large imports."""

        if processed_lines % _PROGRESS_UPDATE_LINE_INTERVAL != 0:
            return

        self.import_batch_repo.update_progress(
            batch_id,
            processed_bytes=processed_bytes,
            total_bytes=total_bytes,
            processed_lines=processed_lines,
            valid_ticks=valid_ticks,
            skipped_lines=skipped_lines,
            days_completed=days_completed,
            datasets_written=datasets_written,
        )

    def _flush_daily_partition(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        trading_day: date,
        rows: list[dict],
        source_file_name: str,
        import_batch_id: str,
    ) -> int:
        """Write one day's ticks and derived candles to MinIO."""

        ticks_frame = pd.DataFrame(rows)
        ticks_frame["timestamp"] = pd.to_datetime(
            ticks_frame["timestamp"],
            utc=True,
        )

        datasets_written = 1
        tick_object_key = self._build_object_key(
            symbol=symbol,
            dataset_type="ticks",
            timeframe=None,
            trading_day=trading_day,
        )
        tick_size = self.parquet_store.write_dataframe(
            tick_object_key,
            ticks_frame,
        )
        tick_document = create_market_data_doc(
            symbol=symbol,
            raw_symbol=raw_symbol,
            dataset_type="ticks",
            timeframe=None,
            date=trading_day,
            object_key=tick_object_key,
            row_count=len(ticks_frame.index),
            byte_size=tick_size,
            source_file_name=source_file_name,
            import_batch_id=import_batch_id,
        )
        self.dataset_repo.upsert_document(tick_document)

        datasets_written += self._write_candle_datasets(
            symbol=symbol,
            raw_symbol=raw_symbol,
            trading_day=trading_day,
            ticks_frame=ticks_frame,
            source_file_name=source_file_name,
            import_batch_id=import_batch_id,
        )
        return datasets_written

    def _write_candle_datasets(
        self,
        *,
        symbol: str,
        raw_symbol: str | None,
        trading_day: date,
        ticks_frame: pd.DataFrame,
        source_file_name: str,
        import_batch_id: str | None,
    ) -> int:
        """Write all supported candle timeframes for one day."""

        datasets_written = 0
        for timeframe in SUPPORTED_CANDLE_TIMEFRAMES:
            candle_frame = build_candles_from_ticks(
                ticks_frame,
                timeframe,
            )
            object_key = self._build_object_key(
                symbol=symbol,
                dataset_type="candles",
                timeframe=timeframe,
                trading_day=trading_day,
            )
            byte_size = self.parquet_store.write_dataframe(
                object_key,
                candle_frame,
            )
            document = create_market_data_doc(
                symbol=symbol,
                raw_symbol=raw_symbol,
                dataset_type="candles",
                timeframe=timeframe,
                date=trading_day,
                object_key=object_key,
                row_count=len(candle_frame.index),
                byte_size=byte_size,
                source_file_name=source_file_name,
                import_batch_id=import_batch_id,
            )
            self.dataset_repo.upsert_document(document)
            datasets_written += 1
        return datasets_written

    def _read_daily_bars(
        self,
        *,
        symbols: list[str],
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict]:
        """Build daily OHLC bars from stored raw tick partitions."""

        current_day = start_dt.date()
        bars: list[dict] = []
        while current_day <= end_dt.date():
            tick_document = self.dataset_repo.find_dataset(
                symbols,
                "ticks",
                current_day,
                None,
            )
            if tick_document is not None:
                ticks_frame = self.parquet_store.read_dataframe(
                    tick_document["object_key"]
                )
                daily_frame = build_candles_from_ticks(
                    ticks_frame,
                    "1d",
                )
                bars.extend(
                    self._frame_to_ohlc_records(daily_frame)
                )
            current_day += timedelta(days=1)

        return self._filter_bars_by_range(
            bars,
            start_dt=start_dt,
            end_dt=end_dt,
        )

    def _frame_to_ohlc_records(
        self,
        frame: pd.DataFrame,
    ) -> list[dict]:
        """Convert a candle DataFrame into API response records."""

        if frame.empty:
            return []

        records: list[dict] = []
        for row in frame.to_dict(orient="records"):
            records.append(
                {
                    "time": int(row["time"]),
                    "open": round(float(row["open"]), 6),
                    "high": round(float(row["high"]), 6),
                    "low": round(float(row["low"]), 6),
                    "close": round(float(row["close"]), 6),
                    "volume": int(row.get("volume", 0)),
                }
            )
        records.sort(key=lambda item: item["time"])
        return records

    def _frame_to_tick_records(
        self,
        frame: pd.DataFrame,
    ) -> list[dict]:
        """Convert a tick DataFrame into replayable records."""

        if frame.empty:
            return []

        normalized = frame.copy()
        normalized["timestamp"] = pd.to_datetime(
            normalized["timestamp"],
            utc=True,
        )
        normalized = normalized.sort_values("timestamp")

        records: list[dict] = []
        for row in normalized.to_dict(orient="records"):
            records.append(
                {
                    "timestamp": row["timestamp"].to_pydatetime(),
                    "last_price": round(
                        float(row["last_price"]), 6
                    ),
                    "bid_price": round(
                        float(row["bid_price"]), 6
                    ),
                    "ask_price": round(
                        float(row["ask_price"]), 6
                    ),
                    "size": int(row.get("size", 0)),
                }
            )
        return records

    def _frame_to_tick_price_records(
        self,
        frame: pd.DataFrame,
        *,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[tuple[datetime, float]]:
        """Convert a tick DataFrame into sorted timestamp/last-price pairs."""

        if frame.empty:
            return []

        normalized = frame.loc[:, ["timestamp", "last_price"]].copy()
        normalized["timestamp"] = pd.to_datetime(
            normalized["timestamp"],
            utc=True,
        )
        normalized = normalized[
            (normalized["timestamp"] >= start_dt)
            & (normalized["timestamp"] <= end_dt)
        ]
        if normalized.empty:
            return []

        normalized = normalized.sort_values("timestamp")
        records: list[tuple[datetime, float]] = []
        for timestamp, last_price in normalized.itertuples(
            index=False,
            name=None,
        ):
            records.append(
                (
                    timestamp.to_pydatetime(),
                    round(float(last_price), 6),
                )
            )
        return records

    def _filter_bars_by_range(
        self,
        bars: list[dict],
        *,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[dict]:
        """Return only bars that fall inside the requested time range."""

        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())
        return [
            bar
            for bar in sorted(bars, key=lambda item: item["time"])
            if start_ts <= bar["time"] <= end_ts
        ]

    def _build_object_key(
        self,
        *,
        symbol: str,
        dataset_type: str,
        timeframe: str | None,
        trading_day: date,
    ) -> str:
        """Build a stable object key for a stored dataset partition."""

        safe_symbol = symbol.replace("/", "_").replace("\\", "_")
        base_key = (
            f"{safe_symbol}/{dataset_type}/"
            f"{trading_day.year:04d}/{trading_day.month:02d}/"
            f"{trading_day.day:02d}.parquet"
        )
        if dataset_type == "ticks":
            return base_key
        return (
            f"{safe_symbol}/{dataset_type}/{timeframe}/"
            f"{trading_day.year:04d}/{trading_day.month:02d}/"
            f"{trading_day.day:02d}.parquet"
        )

    @staticmethod
    def _tick_to_row(tick: NinjaTraderTick) -> dict:
        """Convert a parsed tick into a row dict for DataFrames."""

        return {
            "timestamp": tick.timestamp,
            "last_price": tick.last_price,
            "bid_price": tick.bid_price,
            "ask_price": tick.ask_price,
            "size": tick.size,
        }

    def _guess_symbol(self, file_name: str) -> str | None:
        """Infer a symbol hint from common NinjaTrader export names."""

        stem = Path(file_name).stem
        if not stem:
            return None

        before_dot = stem.split(".", 1)[0].strip()
        if not before_dot:
            return None

        return before_dot.split()[0].upper()

    def _guess_raw_symbol(
        self,
        file_name: str,
    ) -> str | None:
        """Infer a raw symbol hint from a NinjaTrader export filename."""

        stem = Path(file_name).stem
        if not stem:
            return None

        return stem.split(".", 1)[0].strip() or None
