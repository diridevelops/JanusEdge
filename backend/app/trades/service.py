"""Trade service — business logic for trades."""

from datetime import datetime, timedelta

from bson import ObjectId

from app.models.trade import create_trade_doc
from app.repositories.account_repo import (
    AccountRepository,
)
from app.repositories.execution_repo import (
    ExecutionRepository,
)
from app.repositories.market_data_repo import (
    MarketDataRepository,
)
from app.repositories.tag_repo import TagRepository
from app.repositories.trade_repo import TradeRepository
from app.imports.reconstructor import get_point_value
from app.market_data.symbol_mapper import map_to_yahoo
from app.utils.datetime_utils import utc_now
from app.utils.errors import NotFoundError


def _parse_date_from(value: str) -> datetime:
    """Parse date_from as inclusive lower bound."""
    return datetime.fromisoformat(value)


def _parse_date_to(value: str) -> datetime:
    """Parse date_to as inclusive upper bound.

    For date-only values (YYYY-MM-DD), include the entire
    selected day by converting to the next day minus 1 microsecond.
    """
    dt = datetime.fromisoformat(value)
    if len(value) == 10:
        return dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


class TradeService:
    """Service for trade operations."""

    def __init__(self):
        self.trade_repo = TradeRepository()
        self.exec_repo = ExecutionRepository()
        self.account_repo = AccountRepository()
        self.tag_repo = TagRepository()
        self.market_data_repo = MarketDataRepository()

    def list_trades(
        self,
        user_id: str,
        account: str = None,
        symbol: str = None,
        side: str = None,
        tag: str = None,
        date_from: str = None,
        date_to: str = None,
        page: int = 1,
        per_page: int = 25,
        sort_by: str = "entry_time",
        sort_dir: str = "desc",
    ) -> dict:
        """
        List trades with filters and pagination.

        Returns:
            Dict with trades, total, and page info.
        """
        filters = {}
        if account:
            if ObjectId.is_valid(account):
                filters["trade_account_id"] = ObjectId(
                    account
                )
            else:
                acct = self.account_repo.find_one(
                    {
                        "user_id": ObjectId(user_id),
                        "account_name": account,
                    }
                )
                if acct:
                    filters["trade_account_id"] = acct[
                        "_id"
                    ]
        if symbol:
            filters["symbol"] = symbol.upper()
        if side:
            filters["side"] = side
        if tag:
            if ObjectId.is_valid(tag):
                filters["tag_ids"] = ObjectId(tag)
            else:
                tag_doc = self.tag_repo.find_by_name(
                    user_id, tag
                )
                if tag_doc:
                    filters["tag_ids"] = tag_doc[
                        "_id"
                    ]
        if date_from:
            dt_from = _parse_date_from(date_from)
            filters.setdefault("entry_time", {})
            filters["entry_time"]["$gte"] = dt_from
        if date_to:
            dt_to = _parse_date_to(date_to)
            filters.setdefault("entry_time", {})
            filters["entry_time"]["$lte"] = dt_to

        direction = -1 if sort_dir == "desc" else 1
        skip = (page - 1) * per_page

        trades = self.trade_repo.find_by_user(
            user_id=user_id,
            filters=filters,
            sort_by=sort_by,
            sort_dir=direction,
            skip=skip,
            limit=per_page,
        )
        total = self.trade_repo.count_by_user(
            user_id, filters
        )

        market_cache: dict[tuple[str, datetime.date], bool] = {}

        serialized_trades = []
        for trade in trades:
            serialized = self.trade_repo.serialize_doc(trade)

            trade_day = trade.get("entry_time")
            if isinstance(trade_day, datetime):
                day_key = trade_day.date()
            else:
                day_key = datetime.fromisoformat(
                    str(serialized.get("entry_time"))
                ).date()

            yahoo_symbol = map_to_yahoo(
                trade.get("symbol", ""),
                trade.get("raw_symbol"),
            )

            cache_key = (yahoo_symbol, day_key)
            if cache_key not in market_cache:
                market_cache[cache_key] = (
                    self.market_data_repo.has_cached_day(
                        symbol=yahoo_symbol,
                        interval="5m",
                        cache_date=day_key,
                    )
                )

            serialized["market_data_cached"] = (
                market_cache[cache_key]
            )
            serialized_trades.append(serialized)

        return {
            "trades": serialized_trades,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }

    def get_trade(self, user_id: str, trade_id: str) -> dict:
        """
        Get a single trade with its executions.

        Returns:
            Dict with trade and executions.

        Raises:
            NotFoundError: If trade not found.
        """
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")

        executions = self.exec_repo.find_by_trade(
            trade_id
        )
        return {
            "trade": self.trade_repo.serialize_doc(trade),
            "executions": [
                self.exec_repo.serialize_doc(e)
                for e in executions
            ],
        }

    def create_manual_trade(
        self, user_id: str, data: dict
    ) -> dict:
        """
        Create a manual trade entry.

        Parameters:
            user_id: User's ObjectId string.
            data: Validated trade data.

        Returns:
            Created trade document.
        """
        user_oid = ObjectId(user_id)

        # Find or create account
        account = self.account_repo.find_or_create(
            user_id=user_id,
            account_name=data.get("account", "Manual"),
            source_platform="manual",
        )

        # Compute P&L
        symbol = data["symbol"].upper()
        point_value = get_point_value(symbol)
        qty = data["total_quantity"]
        entry_price = data["entry_price"]
        exit_price = data["exit_price"]
        fee = data.get("fee", 0.0)

        if data["side"] == "Long":
            gross_pnl = (exit_price - entry_price) * qty * point_value
        else:
            gross_pnl = (entry_price - exit_price) * qty * point_value

        net_pnl = gross_pnl - fee

        entry_time = data["entry_time"]
        exit_time = data["exit_time"]
        if isinstance(entry_time, str):
            entry_time = datetime.fromisoformat(entry_time)
        if isinstance(exit_time, str):
            exit_time = datetime.fromisoformat(exit_time)

        holding_secs = int(
            (exit_time - entry_time).total_seconds()
        )

        trade_doc = create_trade_doc(
            user_id=user_oid,
            trade_account_id=account["_id"],
            import_batch_id=None,
            symbol=symbol,
            raw_symbol=data["symbol"],
            side=data["side"],
            total_quantity=qty,
            max_quantity=qty,
            avg_entry_price=entry_price,
            avg_exit_price=exit_price,
            gross_pnl=round(gross_pnl, 2),
            fee=fee,
            fee_source="manual_edit",
            net_pnl=round(net_pnl, 2),
            entry_time=entry_time,
            exit_time=exit_time,
            holding_time_seconds=holding_secs,
            execution_count=0,
            source="manual",
        )

        # Handle tags
        tag_names = data.get("tags", [])
        if tag_names:
            tag_ids = self._resolve_tags(
                user_id, tag_names
            )
            trade_doc["tag_ids"] = tag_ids

        # Handle notes
        notes = data.get("notes", "")
        if notes:
            trade_doc["post_trade_notes"] = notes

        trade_id = self.trade_repo.insert_one(trade_doc)
        trade = self.trade_repo.find_by_id(trade_id)
        return self.trade_repo.serialize_doc(trade)

    def update_trade(
        self, user_id: str, trade_id: str, data: dict
    ) -> dict:
        """
        Update trade fields (fees, notes, tags, etc.).

        Returns:
            Updated trade document.

        Raises:
            NotFoundError: If trade not found.
        """
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")

        updates = {}
        if "fee" in data:
            new_fee = data["fee"]
            updates["fee"] = new_fee
            updates["fee_source"] = data.get(
                "fee_source", "manual_edit"
            )
            updates["fee_last_edited"] = utc_now()
            updates["net_pnl"] = (
                trade["gross_pnl"] - new_fee
            )
            updates["manually_adjusted"] = True

        if "strategy" in data:
            updates["strategy"] = data["strategy"]
        if "pre_trade_notes" in data:
            updates["pre_trade_notes"] = (
                data["pre_trade_notes"]
            )
        if "post_trade_notes" in data:
            updates["post_trade_notes"] = (
                data["post_trade_notes"]
            )
        if "tag_ids" in data:
            updates["tag_ids"] = [
                ObjectId(tid) for tid in data["tag_ids"]
            ]

        if updates:
            updates["updated_at"] = utc_now()
            self.trade_repo.update_one(
                trade_id, {"$set": updates}
            )

        trade = self.trade_repo.find_by_id(trade_id)
        return self.trade_repo.serialize_doc(trade)

    def delete_trade(
        self, user_id: str, trade_id: str
    ) -> None:
        """
        Soft-delete a trade.

        Raises:
            NotFoundError: If trade not found.
        """
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")

        self.trade_repo.soft_delete(trade_id)

    def restore_trade(
        self, user_id: str, trade_id: str
    ) -> dict:
        """
        Restore a soft-deleted trade.

        Returns:
            Restored trade document.

        Raises:
            NotFoundError: If trade not found.
        """
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")

        self.trade_repo.restore(trade_id)
        trade = self.trade_repo.find_by_id(trade_id)
        return self.trade_repo.serialize_doc(trade)

    def search_trades(
        self, user_id: str, query: str
    ) -> list:
        """
        Full-text search on trades.

        Returns:
            List of matching trade documents.
        """
        trades = self.trade_repo.search_text(
            user_id, query
        )
        return [
            self.trade_repo.serialize_doc(t)
            for t in trades
        ]

    def _resolve_tags(
        self, user_id: str, tag_names: list
    ) -> list:
        """Resolve tag names to ObjectIds, creating if needed."""
        from app.models.tag import create_tag_doc

        tag_ids = []
        for name in tag_names:
            tag = self.tag_repo.find_by_name(
                user_id, name
            )
            if not tag:
                doc = create_tag_doc(
                    user_id=ObjectId(user_id),
                    name=name,
                )
                tag_id = self.tag_repo.insert_one(doc)
                tag_ids.append(ObjectId(tag_id))
            else:
                tag_ids.append(tag["_id"])
        return tag_ids
