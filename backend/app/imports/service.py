"""Import service — orchestrates CSV parsing and import."""

from datetime import datetime
from typing import List

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.imports.parsers.base import (
    ParsedExecution,
    ParseResult,
)
from app.imports.parsers.detector import PlatformDetector
from app.imports.reconstructor import (
    ReconstructedTrade,
    reconstruct_trades,
)
from app.models.execution import create_execution_doc
from app.models.import_batch import (
    create_import_batch_doc,
)
from app.models.trade import create_trade_doc
from app.models.audit_log import create_audit_log_doc
from app.repositories.account_repo import (
    AccountRepository,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.execution_repo import (
    ExecutionRepository,
)
from app.repositories.import_batch_repo import (
    ImportBatchRepository,
)
from app.repositories.trade_repo import TradeRepository
from app.utils.errors import (
    DuplicateImportError,
    ValidationError,
)
from app.utils.hash_utils import compute_file_hash


class ImportService:
    """Service for CSV import orchestration."""

    def __init__(self):
        self.detector = PlatformDetector()
        self.batch_repo = ImportBatchRepository()
        self.exec_repo = ExecutionRepository()
        self.trade_repo = TradeRepository()
        self.account_repo = AccountRepository()
        self.audit_repo = AuditRepository()

    def upload_and_parse(
        self,
        file_content: bytes,
        file_name: str,
        user_id: str,
        user_timezone: str = None,
    ) -> dict:
        """
        Upload, detect platform, and parse CSV.

        Parameters:
            file_content: Raw file bytes.
            file_name: Original file name.
            user_id: User's ObjectId string.
            user_timezone: User's trading timezone.

        Returns:
            Dict with platform, executions, errors,
            and file_hash.

        Raises:
            ValidationError: If platform unrecognized.
            DuplicateImportError: If already imported.
        """
        file_hash = compute_file_hash(file_content)

        # Check for duplicates
        existing = self.batch_repo.find_by_file_hash(
            user_id, file_hash
        )
        if existing:
            raise DuplicateImportError(
                "This file has already been imported."
            )

        content = file_content.decode("utf-8-sig")
        parser = self.detector.detect(content)
        if not parser:
            raise ValidationError(
                "Unrecognized CSV format. "
                "Supported: NinjaTrader, Quantower."
            )

        result = parser.parse(content, user_timezone)

        return {
            "platform": result.platform,
            "executions": [
                self._serialize_execution(e)
                for e in result.executions
            ],
            "errors": [
                {
                    "row_number": e.row_number,
                    "field": e.field,
                    "message": e.message,
                    "raw_value": e.raw_value,
                }
                for e in result.errors
            ],
            "warnings": result.warnings,
            "row_count": result.row_count,
            "file_hash": file_hash,
            "file_name": file_name,
            "file_size": len(file_content),
            "column_mapping": result.column_mapping,
        }

    def reconstruct(
        self,
        executions_data: list,
        method: str = "FIFO",
    ) -> list:
        """
        Reconstruct trades from parsed executions.

        Parameters:
            executions_data: List of execution dicts
                from the upload step.
            method: Reconstruction method.

        Returns:
            List of reconstructed trade dicts.
        """
        executions = [
            self._deserialize_execution(e)
            for e in executions_data
        ]
        trades = reconstruct_trades(executions, method)

        return [
            self._serialize_trade(t, i)
            for i, t in enumerate(trades)
        ]

    def finalize(
        self,
        user_id: str,
        file_hash: str,
        file_name: str,
        file_size: int,
        platform: str,
        trades_data: list,
        all_executions: list,
        fees: dict,
        reconstruction_method: str = "FIFO",
        user_timezone: str = None,
        column_mapping: dict = None,
    ) -> dict:
        """
        Finalize import: persist executions, trades, batch.

        Parameters:
            user_id: User's ObjectId string.
            file_hash: SHA-256 of file.
            file_name: Original file name.
            file_size: File size in bytes.
            platform: Detected platform.
            trades_data: Reconstructed trades data.
            all_executions: All parsed executions.
            fees: Dict mapping trade index to fee.
            reconstruction_method: Method used.
            user_timezone: User's timezone.
            column_mapping: Detected column mapping.

        Returns:
            Import summary dict.
        """
        user_oid = ObjectId(user_id)

        # Check duplicate again
        existing = self.batch_repo.find_by_file_hash(
            user_id, file_hash
        )
        if existing:
            raise DuplicateImportError(
                "This file has already been imported."
            )

        # Re-parse and reconstruct
        executions = [
            self._deserialize_execution(e)
            for e in all_executions
        ]
        reconstructed = reconstruct_trades(
            executions, reconstruction_method
        )

        # Create import batch first
        batch_doc = create_import_batch_doc(
            user_id=user_oid,
            file_name=file_name,
            file_hash=file_hash,
            file_size_bytes=file_size,
            platform=platform,
            column_mapping=column_mapping,
            reconstruction_method=reconstruction_method,
        )
        try:
            batch_id = self.batch_repo.insert_one(batch_doc)
        except DuplicateKeyError as exc:
            raise DuplicateImportError(
                "This file has already been imported."
            ) from exc
        batch_oid = ObjectId(batch_id)

        # Process each reconstructed trade
        total_trades = 0
        total_execs = 0

        for i, trade in enumerate(reconstructed):
            fee = fees.get(str(i), 0.0)

            # Find/create trade account
            account = self.account_repo.find_or_create(
                user_id=user_id,
                account_name=trade.account,
                source_platform=platform,
            )
            account_oid = account["_id"]

            # Insert executions
            exec_docs = []
            exec_ids = []
            for ex in trade.executions:
                timestamp = datetime.fromisoformat(
                    ex.timestamp
                )
                doc = create_execution_doc(
                    user_id=user_oid,
                    trade_account_id=account_oid,
                    import_batch_id=batch_oid,
                    symbol=ex.symbol,
                    raw_symbol=ex.raw_symbol,
                    side=ex.side,
                    quantity=ex.quantity,
                    price=ex.price,
                    timestamp=timestamp,
                    platform_execution_id=(
                        ex.platform_execution_id or None
                    ),
                    platform_order_id=(
                        ex.platform_order_id or None
                    ),
                    order_type=ex.order_type or None,
                    entry_exit=ex.entry_exit or None,
                    commission=ex.commission,
                    raw_data=ex.raw_data,
                )
                exec_docs.append(doc)

            try:
                inserted_exec_ids = (
                    self.exec_repo.insert_many(exec_docs)
                )
            except DuplicateKeyError as exc:
                raise ValidationError(
                    "Duplicate execution IDs detected in imported data."
                ) from exc
            total_execs += len(inserted_exec_ids)

            # Determine fee source
            csv_total_commission = sum(
                ex.commission for ex in trade.executions
            )
            if fee > 0:
                fee_source = "import_entry"
            elif csv_total_commission > 0:
                fee = csv_total_commission
                fee_source = "csv"
            else:
                fee_source = "import_entry"

            net_pnl = trade.gross_pnl - fee

            # Insert trade
            entry_time = datetime.fromisoformat(
                trade.entry_time
            )
            exit_time = datetime.fromisoformat(
                trade.exit_time
            )

            trade_doc = create_trade_doc(
                user_id=user_oid,
                trade_account_id=account_oid,
                import_batch_id=batch_oid,
                symbol=trade.symbol,
                raw_symbol=trade.raw_symbol,
                side=trade.side,
                total_quantity=trade.total_quantity,
                max_quantity=trade.max_quantity,
                avg_entry_price=trade.avg_entry_price,
                avg_exit_price=trade.avg_exit_price,
                gross_pnl=trade.gross_pnl,
                fee=fee,
                fee_source=fee_source,
                net_pnl=net_pnl,
                entry_time=entry_time,
                exit_time=exit_time,
                holding_time_seconds=(
                    trade.holding_time_seconds
                ),
                execution_count=trade.execution_count,
                source="imported",
            )
            trade_id = self.trade_repo.insert_one(
                trade_doc
            )

            # Update executions with trade_id
            self.exec_repo.update_trade_ids(
                inserted_exec_ids, trade_id
            )

            total_trades += 1

        # Update batch stats
        self.batch_repo.update_one(
            batch_id,
            {
                "$set": {
                    "stats": {
                        "total_rows": len(all_executions),
                        "imported_rows": total_execs,
                        "skipped_rows": 0,
                        "error_rows": 0,
                        "trades_reconstructed": (
                            total_trades
                        ),
                    }
                }
            },
        )

        # Audit log
        audit_doc = create_audit_log_doc(
            user_id=user_oid,
            action="import",
            entity_type="import_batch",
            entity_id=batch_oid,
            new_values={
                "file_name": file_name,
                "platform": platform,
                "trades": total_trades,
                "executions": total_execs,
            },
            metadata={
                "file_name": file_name,
                "file_hash": file_hash,
            },
        )
        self.audit_repo.insert_one(audit_doc)

        return {
            "import_batch_id": batch_id,
            "file_name": file_name,
            "platform": platform,
            "trades_imported": total_trades,
            "executions_imported": total_execs,
        }

    def _serialize_execution(
        self, ex: ParsedExecution
    ) -> dict:
        """Convert ParsedExecution to dict."""
        return {
            "symbol": ex.symbol,
            "raw_symbol": ex.raw_symbol,
            "side": ex.side,
            "quantity": ex.quantity,
            "price": ex.price,
            "timestamp": ex.timestamp,
            "platform_execution_id": (
                ex.platform_execution_id
            ),
            "platform_order_id": ex.platform_order_id,
            "order_type": ex.order_type,
            "entry_exit": ex.entry_exit,
            "commission": ex.commission,
            "account": ex.account,
            "connection": ex.connection,
            "raw_data": ex.raw_data,
        }

    def _deserialize_execution(
        self, data: dict
    ) -> ParsedExecution:
        """Convert dict back to ParsedExecution."""
        return ParsedExecution(
            symbol=data.get("symbol", ""),
            raw_symbol=data.get("raw_symbol", ""),
            side=data.get("side", ""),
            quantity=data.get("quantity", 0),
            price=data.get("price", 0.0),
            timestamp=data.get("timestamp", ""),
            platform_execution_id=data.get(
                "platform_execution_id", ""
            ),
            platform_order_id=data.get(
                "platform_order_id", ""
            ),
            order_type=data.get("order_type", ""),
            entry_exit=data.get("entry_exit", ""),
            commission=data.get("commission", 0.0),
            account=data.get("account", ""),
            connection=data.get("connection", ""),
            raw_data=data.get("raw_data", {}),
        )

    def _serialize_trade(
        self, trade: ReconstructedTrade, index: int
    ) -> dict:
        """Convert ReconstructedTrade to dict."""
        return {
            "index": index,
            "symbol": trade.symbol,
            "raw_symbol": trade.raw_symbol,
            "side": trade.side,
            "total_quantity": trade.total_quantity,
            "max_quantity": trade.max_quantity,
            "avg_entry_price": trade.avg_entry_price,
            "avg_exit_price": trade.avg_exit_price,
            "gross_pnl": trade.gross_pnl,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "holding_time_seconds": (
                trade.holding_time_seconds
            ),
            "execution_count": trade.execution_count,
            "fee": trade.fee,
            "account": trade.account,
        }
