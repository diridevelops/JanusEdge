"""HistData parsing and immutable manual dataset revision tests."""

from datetime import date, datetime, timezone
from io import BytesIO
import json

import pytest
from bson import ObjectId
from werkzeug.datastructures import FileStorage

from app.backtests.manual_import import (
    MANUAL_CANDLE_CACHE_VERSION,
    ManualCandleDatasetStore,
    parse_histdata_files,
)
from app.backtests.snapshot_store import SnapshotStore
from app.auth.backup_service import PortableBackupService
from app.utils.errors import ConflictError, ValidationError


def _file(contents: str, name: str = "EURUSD.csv") -> FileStorage:
    return FileStorage(
        stream=BytesIO(contents.encode("utf-8")),
        filename=name,
        content_type="text/csv",
    )


def _row(stamp: str, open_price: str, high: str, low: str, close: str, volume: str) -> str:
    return f"{stamp};{open_price};{high};{low};{close};{volume}"


def test_histdata_parser_uses_fixed_est_and_deduplicates_identical_rows():
    first = _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10")
    second = _row("20260601 000100", "1.15", "1.25", "1.1", "1.2", "12")

    grouped, source_dates = parse_histdata_files([
        _file(first + "\n" + second),
        _file(first, "duplicate.csv"),
    ])

    candles = grouped[date(2026, 6, 1)]
    assert source_dates == ["2026-06-01"]
    assert len(candles) == 2
    assert candles[0]["time_ms"] == int(
        datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc).timestamp() * 1000
    )
    assert candles[0]["open"] == 1.1
    assert candles[0]["volume"] == 10


def test_histdata_parser_rejects_conflicting_duplicate_rows():
    first = _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10")
    conflict = _row("20260601 000000", "1.1", "1.21", "1.0", "1.18", "11")

    with pytest.raises(ValidationError, match="conflicting duplicate timestamp"):
        parse_histdata_files([_file(first), _file(conflict, "second.csv")])


def test_conflicting_import_requires_confirmation_and_keeps_prior_revision(app):
    user_id = ObjectId()
    base_rows = "\n".join([
        _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"),
        _row("20260601 000100", "1.15", "1.25", "1.1", "1.2", "12"),
    ])
    incoming_rows = "\n".join([
        _row("20260601 000000", "1.1", "1.21", "1.0", "1.18", "11"),
        _row("20260601 000200", "1.2", "1.3", "1.15", "1.25", "8"),
    ])

    with app.app_context():
        store = ManualCandleDatasetStore()
        original = store.merge(
            user_id,
            "EUR-USD",
            [_file(base_rows)],
            expected_revision=None,
            confirm_overwrite=False,
        )
        original_id = str(original["_id"])
        identical_preview = store.preview(
            user_id,
            "EUR-USD",
            [_file(_row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"))],
        )
        assert identical_preview["requires_confirmation"] is True
        assert identical_preview["conflict_count"] == 0
        with pytest.raises(ConflictError):
            store.merge(
                user_id,
                "EUR-USD",
                [_file(_row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"))],
                expected_revision=original_id,
                confirm_overwrite=False,
            )
        preview = store.preview(user_id, "EUR-USD", [_file(incoming_rows)])
        assert preview["requires_confirmation"] is True
        assert preview["conflicting_dates"] == ["2026-06-01"]
        assert preview["overlap_dates"] == ["2026-06-01"]
        assert preview["candle_count"] == 3

        with pytest.raises(ConflictError):
            store.merge(
                user_id,
                "EUR-USD",
                [_file(incoming_rows)],
                expected_revision=original_id,
                confirm_overwrite=False,
            )

        assert str(store.get_active(user_id, "EUR-USD")["_id"]) == original_id
        original_ref = store.get_day_ref(original, date(2026, 6, 1))
        original_candles = store.snapshot_store.read_cached_candle_date(
            original_ref
        )["candles"]
        assert len(original_candles) == 2
        assert original_candles[0]["close"] == pytest.approx(1.15)

        merged = store.merge(
            user_id,
            "EUR-USD",
            [_file(incoming_rows)],
            expected_revision=original_id,
            confirm_overwrite=True,
        )
        assert str(merged["_id"]) != original_id
        merged_candles = store.snapshot_store.read_cached_candle_date(
            store.get_day_ref(merged, date(2026, 6, 1))
        )["candles"]
        assert len(merged_candles) == 3
        assert merged_candles[0]["close"] == pytest.approx(1.18)
        assert merged_candles[2]["close"] == pytest.approx(1.25)
        assert store.get_active(ObjectId(), "EUR-USD") is None

        ref = store.get_day_ref(merged, date(2026, 6, 1))
        portable = PortableBackupService._portable_snapshot({
            "_day_candle_indexes": [{"utc_date": "2026-06-01", "cache_ref": ref}]
        })
        portable_ref = portable["_day_candle_indexes"][0]["cache_ref"]
        assert portable_ref["source"] == "manual"
        assert portable_ref["data_sha256"] == ref["data_sha256"]
        assert "object_key" not in portable_ref
        bound, has_missing = PortableBackupService()._bind_snapshot_cache(
            portable, user_id
        )
        assert has_missing is False
        assert bound["_day_candle_indexes"][0]["cache_ref"]["object_key"] == ref["object_key"]


def test_manual_run_uses_cached_dataset_and_has_manual_name_suffix(app):
    from app.backtests.service import BacktestService
    from app.extensions import mongo

    user_id = ObjectId()
    contents = "\n".join([
        _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"),
        _row("20260601 000100", "1.15", "1.25", "1.1", "1.2", "12"),
    ])

    with app.app_context():
        service = BacktestService()
        imported = service.create_manual_run(
            user_id=str(user_id),
            instrument="EUR-USD",
            display_timezone="UTC",
            start_date="2026-06-01",
            end_date="2026-06-01",
            period_selection="manual",
            period_months=None,
            warmup_days=0,
            blind_mode=False,
            initial_balance_usd=10_000,
            risk_percent=1,
            execution_costs=None,
            files=[_file(contents)],
        )
        cached = service.create_manual_run(
            user_id=str(user_id),
            instrument="EUR-USD",
            display_timezone="UTC",
            start_date="2026-06-01",
            end_date="2026-06-01",
            period_selection="manual",
            period_months=None,
            warmup_days=0,
            blind_mode=False,
            initial_balance_usd=10_000,
            risk_percent=1,
            execution_costs=None,
        )
        first_run = mongo.db.backtest_runs.find_one({"_id": imported["id"]})
        second_run = mongo.db.backtest_runs.find_one({"_id": cached["id"]})
        job = mongo.db.backtest_preparation_jobs.find_one({"run_id": imported["id"]})

    assert imported["source"] == "manual"
    assert imported["account_label"].endswith("-manual (" + str(imported["id"]) + ")")
    assert cached["account_label"].endswith("-manual (" + str(cached["id"]) + ")")
    assert first_run["manual_dataset_revision"] == second_run["manual_dataset_revision"]
    assert job["source"] == "manual"
    assert job["manual_dataset_revision"] == first_run["manual_dataset_revision"]


def test_oversized_manual_blind_period_uses_all_imported_dates(app):
    from app.backtests.service import BacktestService

    contents = "\n".join([
        _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"),
        _row("20260603 000000", "1.15", "1.25", "1.1", "1.2", "12"),
    ])
    with app.app_context():
        created = BacktestService().create_manual_run(
            user_id=str(ObjectId()),
            instrument="EUR-USD",
            display_timezone="UTC",
            start_date=None,
            end_date=None,
            period_selection="random",
            period_months=12,
            warmup_days=0,
            blind_mode=True,
            initial_balance_usd=10_000,
            risk_percent=1,
            execution_costs=None,
            files=[_file(contents)],
        )

    assert created["requested_start_date"] == "2026-06-01"
    assert created["requested_end_date"] == "2026-06-03"
    assert created["period_selection"] == "random"
    assert "blind-manual" in created["account_label"]


def test_manual_worker_uses_imported_warmup_and_replay_without_downloading(app):
    from app.backtests.service import BacktestService
    from app.backtests.worker import BacktestWorker
    from app.extensions import mongo

    contents = "\n".join([
        _row("20260601 235900", "1.1", "1.2", "1.0", "1.15", "10"),
        _row("20260602 000000", "1.15", "1.25", "1.1", "1.2", "12"),
    ])

    class NoDownloadProvider:
        def fetch_day(self, instrument, utc_date):
            raise AssertionError("Manual replay must not fetch base candles.")

    with app.app_context():
        created = BacktestService().create_manual_run(
            user_id=str(ObjectId()),
            instrument="EUR-USD",
            display_timezone="UTC",
            start_date="2026-06-02",
            end_date="2026-06-02",
            period_selection="manual",
            period_months=None,
            warmup_days=1,
            blind_mode=False,
            initial_balance_usd=10_000,
            risk_percent=1,
            execution_costs=None,
            files=[_file(contents)],
        )
        assert BacktestWorker(provider=NoDownloadProvider()).process_one() is True
        run = mongo.db.backtest_runs.find_one({"_id": created["id"]})

    assert run["status"] == "ready"
    snapshot = run["snapshot"]
    assert snapshot["candle_count"] == 2
    assert snapshot["warmup_coverage"]["candle_count"] == 1
    assert snapshot["replay_period_candle_count"] == 1
    assert snapshot["first_time_ms"] == int(
        datetime(2026, 6, 2, 4, 59, tzinfo=timezone.utc).timestamp() * 1000
    )
    assert snapshot["last_time_ms"] == int(
        datetime(2026, 6, 2, 5, 0, tzinfo=timezone.utc).timestamp() * 1000
    )


def test_invalid_manual_run_does_not_change_cached_dataset(app):
    from app.backtests.service import BacktestService
    from app.backtests.manual_import import ManualCandleDatasetStore

    with app.app_context():
        service = BacktestService()
        with pytest.raises(ValidationError, match="contain imported candles"):
            service.create_manual_run(
                user_id=str(ObjectId()),
                instrument="EUR-USD",
                display_timezone="UTC",
                start_date="2026-06-02",
                end_date="2026-06-02",
                period_selection="manual",
                period_months=None,
                warmup_days=0,
                blind_mode=False,
                initial_balance_usd=10_000,
                risk_percent=1,
                execution_costs=None,
                files=[_file(_row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10"))],
            )
        assert ManualCandleDatasetStore().get_active(
            ObjectId(), "EUR-USD"
        ) is None


def test_manual_run_recovery_reuploads_the_pinned_candle_data(app):
    from app.backtests.service import BacktestService
    from app.extensions import mongo
    from app.storage import get_client, get_market_data_bucket

    user_id = ObjectId()
    source = _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10")
    with app.app_context():
        service = BacktestService()
        created = service.create_manual_run(
            user_id=str(user_id),
            instrument="EUR-USD",
            display_timezone="UTC",
            start_date="2026-06-01",
            end_date="2026-06-01",
            period_selection="manual",
            period_months=None,
            warmup_days=0,
            blind_mode=False,
            initial_balance_usd=10_000,
            risk_percent=1,
            execution_costs=None,
            files=[_file(source)],
        )
        run = mongo.db.backtest_runs.find_one({"_id": created["id"]})
        dataset_store = ManualCandleDatasetStore()
        revision = dataset_store.get_revision(
            user_id, "EUR-USD", run["manual_dataset_revision"]
        )
        snapshot_store = SnapshotStore()
        completed_dates = []
        for utc_day in (date(2026, 6, 1), date(2026, 6, 2)):
            ref = dataset_store.get_day_ref(revision, utc_day)
            if ref["object_key"] is None:
                object_key, checksum, size = snapshot_store.write_cached_candle_date(
                    user_id,
                    "EUR-USD",
                    utc_day,
                    [],
                    cache_version=MANUAL_CANDLE_CACHE_VERSION,
                )
                ref.update({"object_key": object_key, "sha256": checksum, "object_size": size})
            completed_dates.append({
                "utc_date": datetime.combine(utc_day, datetime.min.time(), timezone.utc),
                "outcome": ref["outcome"],
                "cache_ref": ref,
            })
        snapshot, coverage = snapshot_store.assemble_cache_snapshot(
            run=run,
            completed_dates=completed_dates,
            cache_version=MANUAL_CANDLE_CACHE_VERSION,
        )
        mongo.db.backtest_runs.update_one(
            {"_id": run["_id"]},
            {"$set": {"status": "ready", "snapshot": snapshot, "coverage": coverage}},
        )
        replay_ref = next(
            item["cache_ref"]
            for item in snapshot["_day_candle_indexes"]
            if item["utc_date"] == "2026-06-01"
        )
        get_client().remove_object(get_market_data_bucket(), replay_ref["object_key"])

        missing = service.get_cache_status(str(user_id), str(run["_id"]))
        assert missing["state"] == "missing"
        assert any(item["kind"] == "replay" for item in missing["missing_references"])

        recovered = service.restore_manual_run_cache(
            str(user_id), str(run["_id"]), [_file(source)]
        )

    assert recovered["state"] == "available"
    assert recovered["missing_references"] == []


def test_manual_import_routes_accept_settings_instrument_and_histdata_csv(client):
    registered = client.post(
        "/api/auth/register",
        json={"username": "manual-import-api", "password": "TestPass123!", "timezone": "UTC"},
    )
    assert registered.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"username": "manual-import-api", "password": "TestPass123!"},
    )
    headers = {"Authorization": f"Bearer {login.json['token']}"}
    instruments = client.get("/api/backtest/manual-instruments", headers=headers)
    assert instruments.status_code == 200
    assert any(item["instrument"] == "EUR-USD" for item in instruments.json["instruments"])

    contents = _row("20260601 000000", "1.1", "1.2", "1.0", "1.15", "10")
    preview = client.post(
        "/api/backtest/manual-import/preview",
        data={"instrument": "EUR-USD", "files": (_file(contents).stream, "EURUSD.csv")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200
    assert preview.json["available_dates"] == ["2026-06-01"]

    settings = {
        "instrument": "EUR-USD",
        "display_timezone": "UTC",
        "start_date": "2026-06-01",
        "end_date": "2026-06-01",
        "period_selection": "manual",
        "warmup_days": 0,
        "blind_mode": False,
        "initial_balance_usd": 10_000,
        "risk_percent": 1,
    }
    created = client.post(
        "/api/backtest/runs/manual",
        data={"settings": json.dumps(settings), "files": (_file(contents).stream, "EURUSD.csv")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert created.status_code == 202
    assert created.json["run"]["source"] == "manual"
    assert created.json["run"]["account_label"].endswith("-manual (" + created.json["run"]["id"] + ")")
