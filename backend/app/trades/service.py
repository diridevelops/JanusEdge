"""Trade service — business logic for trades."""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from bson import ObjectId

from app.market_data.service import MarketDataService
from app.storage import get_bucket, get_client
from app.whatif.cache import clear_simulation_cache
from app.models.trade import create_trade_doc
from app.repositories.account_repo import (
    AccountRepository,
)
from app.repositories.execution_repo import (
    ExecutionRepository,
)
from app.repositories.media_repo import MediaRepository
from app.repositories.tag_repo import TagRepository
from app.repositories.trade_repo import TradeRepository
from app.repositories.user_repo import UserRepository
from app.market_data.symbol_mapper import (
    get_effective_market_data_mappings,
    get_effective_symbol_mappings,
    get_point_value,
)
from app.utils.datetime_utils import to_utc, utc_now
from app.utils.errors import NotFoundError, ValidationError
from app.utils.trade_metrics import (
    calculate_initial_risk_no_fees,
)


logger = logging.getLogger(__name__)


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
        self.market_data_service = MarketDataService()
        self.media_repo = MediaRepository()
        self.user_repo = UserRepository()

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

        if sort_by == "r_multiple":
            query = {
                "user_id": ObjectId(user_id),
                "status": {"$ne": "deleted"},
            }
            query.update(filters)
            trades = list(
                self.trade_repo.collection.aggregate(
                    [
                        {"$match": query},
                        {
                            "$addFields": {
                                "r_multiple_defined": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                "$initial_risk",
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                },
                                "r_multiple_sort": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                "$initial_risk",
                                                0,
                                            ]
                                        },
                                        {
                                            "$divide": [
                                                "$net_pnl",
                                                "$initial_risk",
                                            ]
                                        },
                                        0,
                                    ]
                                },
                            }
                        },
                        {
                            "$sort": {
                                "r_multiple_defined": -1,
                                "r_multiple_sort": direction,
                                "entry_time": -1,
                            }
                        },
                        {"$skip": skip},
                        {"$limit": per_page},
                    ]
                )
            )
        else:
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
        market_data_mappings = self._get_market_data_mappings(
            user_id
        )
        market_cache: dict[tuple[str, str | None, datetime.date], bool] = {}

        serialized_trades = []
        for trade in trades:
            trade.pop("r_multiple_sort", None)
            trade.pop("r_multiple_defined", None)
            serialized = self.trade_repo.serialize_doc(trade)

            trade_day = trade.get("entry_time")
            if isinstance(trade_day, datetime):
                day_key = trade_day.date()
            else:
                day_key = datetime.fromisoformat(
                    str(serialized.get("entry_time"))
                ).date()

            cache_key = (
                trade.get("symbol", ""),
                trade.get("raw_symbol"),
                day_key,
            )
            if cache_key not in market_cache:
                market_cache[cache_key] = (
                    self.market_data_service.tick_data_service.has_ohlc_for_day(
                        symbol=trade.get("symbol", ""),
                        raw_symbol=trade.get("raw_symbol"),
                        interval="5m",
                        trading_day=day_key,
                        market_data_mappings=market_data_mappings,
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
        if trade.get("status") == "deleted":
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
        symbol_mappings = self._get_symbol_mappings(user_id)
        try:
            point_value = get_point_value(
                symbol,
                str(data.get("symbol", symbol)),
                symbol_mappings,
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        qty = data["total_quantity"]
        entry_price = data["entry_price"]
        exit_price = data["exit_price"]
        fee = data.get("fee", 0.0)

        if data["side"] == "Long":
            gross_pnl = (exit_price - entry_price) * qty * point_value
        else:
            gross_pnl = (entry_price - exit_price) * qty * point_value

        net_pnl = gross_pnl - fee
        requested_initial_risk = float(
            data.get("initial_risk", 0.0)
        )
        if net_pnl < 0 and requested_initial_risk <= 0:
            initial_risk = calculate_initial_risk_no_fees(
                gross_pnl
            )
        else:
            initial_risk = requested_initial_risk

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
            initial_risk=round(initial_risk, 2),
            entry_time=entry_time,
            exit_time=exit_time,
            holding_time_seconds=holding_secs,
            execution_count=0,
            source="manual",
        )

        # Auto-populate target_price for winners
        if net_pnl > 0:
            trade_doc["target_price"] = exit_price

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
        clear_simulation_cache()
        return self.trade_repo.serialize_doc(trade)

    def _get_symbol_mappings(self, user_id: str) -> dict:
        """Return the effective symbol mappings for a user."""
        user = self.user_repo.find_by_id(user_id)
        return get_effective_symbol_mappings(
            user.get("symbol_mappings") if user else None
        )

    def _get_market_data_mappings(self, user_id: str) -> dict:
        """Return the effective market-data mappings for a user."""
        user = self.user_repo.find_by_id(user_id)
        return get_effective_market_data_mappings(
            user.get("market_data_mappings") if user else None
        )

    @staticmethod
    def _get_trade_day(entry_time) -> date:
        """Return the UTC trading day for the trade entry."""
        if isinstance(entry_time, datetime):
            return entry_time.date()
        return datetime.fromisoformat(str(entry_time)).date()

    @staticmethod
    def _get_entry_datetime(entry_time) -> datetime:
        """Return the trade entry as a timezone-aware UTC datetime."""
        if isinstance(entry_time, datetime):
            return to_utc(entry_time)
        return to_utc(datetime.fromisoformat(str(entry_time)))

    @staticmethod
    def _infer_tick_size_from_bars(
        bars: list[dict],
    ) -> Decimal:
        """Infer the minimum observed positive price increment from OHLC bars."""
        prices: list[Decimal] = []
        for bar in bars:
            for field_name in ("open", "high", "low", "close"):
                price_value = bar.get(field_name)
                if price_value is None:
                    continue
                try:
                    prices.append(Decimal(str(price_value)))
                except InvalidOperation:
                    continue

        unique_prices = sorted(set(prices))
        if len(unique_prices) < 2:
            return Decimal("0.01")

        positive_increments = [
            current - previous
            for previous, current in zip(
                unique_prices,
                unique_prices[1:],
            )
            if current > previous
        ]
        if not positive_increments:
            return Decimal("0.01")

        return min(positive_increments).normalize()

    @staticmethod
    def _round_price_to_tick(
        price: Decimal, tick_size: Decimal
    ) -> float:
        """Round a price to the detected tick precision."""
        normalized_tick = tick_size.normalize()
        decimal_places = max(
            0,
            -normalized_tick.as_tuple().exponent,
        )
        rounded = price.quantize(normalized_tick)
        return round(float(rounded), decimal_places)

    def _detect_wish_stop_from_bars(
        self,
        *,
        bars: list[dict],
        side: str,
        entry_price: float,
        tick_size: Decimal,
        entry_ts: int,
    ) -> float:
        """Detect wishful stop from the first completed adverse excursion."""
        entry_decimal = Decimal(str(entry_price))
        adverse_started = False
        adverse_extreme: Decimal | None = None

        for bar in bars:
            bar_time = int(bar["time"])
            is_entry_bar = (
                bar_time <= entry_ts < bar_time + 60
            )

            if side == "Long":
                if not adverse_started:
                    bar_low = bar.get("low")
                    if bar_low is None:
                        continue
                    low_price = Decimal(str(bar_low))
                    if low_price < entry_decimal:
                        adverse_started = True
                        adverse_extreme = low_price
                        bar_high = bar.get("high")
                        if (
                            not is_entry_bar
                            and bar_high is not None
                            and Decimal(str(bar_high))
                            >= entry_decimal
                        ):
                            return self._round_price_to_tick(
                                adverse_extreme - tick_size,
                                tick_size,
                            )
                    continue

                bar_low = bar.get("low")
                if bar_low is not None:
                    low_price = Decimal(str(bar_low))
                    if (
                        adverse_extreme is None
                        or low_price < adverse_extreme
                    ):
                        adverse_extreme = low_price

                bar_high = bar.get("high")
                if (
                            bar_high is not None
                            and Decimal(str(bar_high))
                            >= entry_decimal
                        ):
                            return self._round_price_to_tick(
                                adverse_extreme - tick_size,
                                tick_size,
                            )
            elif side == "Short":
                if not adverse_started:
                    bar_high = bar.get("high")
                    if bar_high is None:
                        continue
                    high_price = Decimal(str(bar_high))
                    if high_price > entry_decimal:
                        adverse_started = True
                        adverse_extreme = high_price
                        bar_low = bar.get("low")
                        if (
                            not is_entry_bar
                            and bar_low is not None
                            and Decimal(str(bar_low))
                            <= entry_decimal
                        ):
                            return self._round_price_to_tick(
                                adverse_extreme + tick_size,
                                tick_size,
                            )
                    continue

                bar_high = bar.get("high")
                if bar_high is not None:
                    high_price = Decimal(str(bar_high))
                    if (
                        adverse_extreme is None
                        or high_price > adverse_extreme
                    ):
                        adverse_extreme = high_price

                bar_low = bar.get("low")
                if (
                            bar_low is not None
                            and Decimal(str(bar_low))
                            <= entry_decimal
                        ):
                            return self._round_price_to_tick(
                                adverse_extreme + tick_size,
                                tick_size,
                            )
            else:
                raise ValidationError(
                    "Wishful stop detection only supports Long and Short trades."
                )

        if adverse_started:
            raise ValidationError(
                "Price moved to the adverse side after entry but did not recover back to the entry price on that trade day."
            )

        raise ValidationError(
            "No adverse excursion was found after the trade entry."
        )

    def detect_wish_stop(
        self, user_id: str, trade_id: str
    ) -> dict:
        """Detect a suggested wishful stop from stored 1-minute OHLC bars."""
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")
        if trade.get("status") == "deleted":
            raise NotFoundError("Trade not found.")
        if trade.get("net_pnl", 0) >= 0:
            raise ValidationError(
                "Wishful stop detection is only available for losing trades."
            )

        entry_time = trade.get("entry_time")
        entry_price = trade.get("avg_entry_price")
        symbol = trade.get("symbol", "")
        raw_symbol = trade.get("raw_symbol")

        if entry_time is None or entry_price is None:
            raise ValidationError(
                "Trade entry data is required to detect a wishful stop."
            )

        trade_day = self._get_trade_day(entry_time)
        market_data_mappings = self._get_market_data_mappings(
            user_id
        )
        bars = (
            self.market_data_service.tick_data_service.read_bars_for_day(
                symbol=symbol,
                raw_symbol=raw_symbol,
                interval="1m",
                trading_day=trade_day,
                market_data_mappings=market_data_mappings,
            )
        )
        if not bars:
            raise ValidationError(
                "No OHLC data is available for this trade day."
            )

        entry_dt = self._get_entry_datetime(entry_time)
        entry_ts = int(entry_dt.timestamp())
        trade_bars = [
            bar
            for bar in bars
            if int(bar["time"]) + 60 > entry_ts
        ]
        if not trade_bars:
            raise ValidationError(
                "No OHLC bars are available at or after the trade entry time."
            )

        tick_size = self._infer_tick_size_from_bars(bars)
        wish_stop_price = self._detect_wish_stop_from_bars(
            bars=trade_bars,
            side=trade.get("side", ""),
            entry_price=entry_price,
            tick_size=tick_size,
            entry_ts=entry_ts,
        )

        return {"wish_stop_price": wish_stop_price}

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
        if trade.get("status") == "deleted":
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

        if "initial_risk" in data:
            updates["initial_risk"] = data[
                "initial_risk"
            ]
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

        if "wish_stop_price" in data:
            updates["wish_stop_price"] = data[
                "wish_stop_price"
            ]
        if "target_price" in data:
            updates["target_price"] = data[
                "target_price"
            ]

        # Auto-manage wicked-out tag based on wish_stop_price
        if "wish_stop_price" in data:
            current_tag_ids = updates.get(
                "tag_ids",
                list(trade.get("tag_ids", [])),
            )
            wo_tag = self.tag_repo.find_by_name(
                user_id, "wicked-out"
            )
            if data["wish_stop_price"] is not None:
                # Add wicked-out tag if not present
                if not wo_tag:
                    from app.models.tag import (
                        create_tag_doc,
                    )

                    doc = create_tag_doc(
                        user_id=ObjectId(user_id),
                        name="wicked-out",
                        category="custom",
                        color="#ef4444",
                    )
                    wo_id = self.tag_repo.insert_one(doc)
                    wo_oid = ObjectId(wo_id)
                else:
                    wo_oid = wo_tag["_id"]
                if wo_oid not in current_tag_ids:
                    current_tag_ids.append(wo_oid)
                    updates["tag_ids"] = current_tag_ids
            else:
                # Remove wicked-out tag if present
                if wo_tag and wo_tag["_id"] in current_tag_ids:
                    current_tag_ids.remove(wo_tag["_id"])
                    updates["tag_ids"] = current_tag_ids

        if updates:
            updates["updated_at"] = utc_now()
            self.trade_repo.update_one(
                trade_id, {"$set": updates}
            )

        trade = self.trade_repo.find_by_id(trade_id)
        clear_simulation_cache()
        return self.trade_repo.serialize_doc(trade)

    def delete_trade(
        self, user_id: str, trade_id: str
    ) -> None:
        """
        Permanently delete a trade and related data.

        Raises:
            NotFoundError: If trade not found.
        """
        trade = self.trade_repo.find_by_id(trade_id)
        if not trade:
            raise NotFoundError("Trade not found.")
        if str(trade["user_id"]) != user_id:
            raise NotFoundError("Trade not found.")

        self._delete_trade_media(user_id, trade_id)
        self.exec_repo.delete_many(
            {"trade_id": ObjectId(trade_id)}
        )

        import_batch_id = trade.get("import_batch_id")
        self.trade_repo.delete_one(trade_id)

        if import_batch_id is not None:
            self._cleanup_empty_import_batch(
                str(import_batch_id)
            )

        clear_simulation_cache()

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
        clear_simulation_cache()
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

    def list_symbols(self, user_id: str) -> list:
        """Return distinct symbols for a user's closed trades."""
        return self.trade_repo.distinct_symbols(user_id)

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

    def _delete_trade_media(
        self, user_id: str, trade_id: str
    ) -> None:
        """Delete all media objects and records for a trade."""
        media_docs = self.media_repo.find_by_trade(
            user_id, trade_id
        )
        if not media_docs:
            return

        try:
            client = get_client()
            bucket = get_bucket()
        except RuntimeError:
            client = None
            bucket = None

        if client and bucket:
            for media_doc in media_docs:
                try:
                    client.remove_object(
                        bucket, media_doc["object_key"]
                    )
                except Exception:
                    logger.warning(
                        "Failed to remove object %s",
                        media_doc["object_key"],
                        exc_info=True,
                    )

        self.media_repo.delete_for_trade(user_id, trade_id)

    def _cleanup_empty_import_batch(
        self, import_batch_id: str
    ) -> None:
        """Delete import-batch metadata when its trades are gone."""
        if self.trade_repo.count(
            {
                "import_batch_id": ObjectId(import_batch_id),
                "status": {"$ne": "deleted"},
            }
        ) > 0:
            return

        self.trade_repo.delete_many(
            {"import_batch_id": ObjectId(import_batch_id)}
        )
        self.exec_repo.delete_many(
            {"import_batch_id": ObjectId(import_batch_id)}
        )

        from app.repositories.import_batch_repo import (
            ImportBatchRepository,
        )

        ImportBatchRepository().delete_one(import_batch_id)
