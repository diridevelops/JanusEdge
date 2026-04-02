"""Tests for tick-data import preview routes."""

from io import BytesIO
from pathlib import Path
import time
from uuid import uuid4


EXAMPLES_DIR = (
    Path(__file__).resolve().parents[3]
    / "market_data_examples"
)


def _load_example_bytes(file_name: str) -> bytes:
    """Load a synthetic market-data example fixture."""

    return (EXAMPLES_DIR / file_name).read_bytes()


def _register_and_login(client):
    """Register a test user and return authorization headers."""

    username = f"tickpreview-{uuid4().hex}"

    client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    token = response.get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _update_market_data_mappings(
    client, headers, market_data_mappings
):
    """Persist market-data mappings for the authenticated test user."""

    response = client.put(
        "/api/auth/market-data-mappings",
        json={"market_data_mappings": market_data_mappings},
        headers=headers,
    )

    assert response.status_code == 200


def _poll_preview_batch(client, headers, batch_id):
    """Poll a preview batch until it reaches a terminal state."""

    completed_batch = None
    for _ in range(50):
        poll_response = client.get(
            f"/api/market-data/tick-imports/preview/{batch_id}",
            headers=headers,
        )
        assert poll_response.status_code == 200
        completed_batch = poll_response.get_json()
        if completed_batch["status"] in {"completed", "failed"}:
            break
        time.sleep(0.02)

    assert completed_batch is not None
    return completed_batch


def test_preview_tick_import_returns_daily_summary(client):
    """Preview creates a batch and returns parsed tick counts grouped by day."""

    headers = _register_and_login(client)
    payload = _load_example_bytes(
        "ES 06-26.Last.txt"
    )

    response = client.post(
        "/api/market-data/tick-imports/preview",
        data={"file": (BytesIO(payload), "ES 06-26.Last.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    batch = response.get_json()
    assert batch["batch_type"] == "preview"
    assert batch["file_name"] == "ES 06-26.Last.txt"
    assert batch["preview"] is None or isinstance(
        batch["preview"], dict
    )

    completed_batch = _poll_preview_batch(
        client,
        headers,
        batch["id"],
    )

    assert completed_batch["status"] == "completed"
    data = completed_batch["preview"]
    assert data is not None
    assert data["file_name"] == "ES 06-26.Last.txt"
    assert data["symbol_guess"] == "ES"
    assert data["total_lines"] == 3
    assert data["valid_ticks"] == 2
    assert data["skipped_lines"] == 1
    assert data["first_tick_at"] == "2026-03-19T13:18:58.624000+00:00"
    assert data["last_tick_at"] == "2026-03-20T09:00:00+00:00"
    assert data["trading_dates"] == [
        {
            "date": "2026-03-19",
            "tick_count": 1,
            "first_tick_at": "2026-03-19T13:18:58.624000+00:00",
            "last_tick_at": "2026-03-19T13:18:58.624000+00:00",
        },
        {
            "date": "2026-03-20",
            "tick_count": 1,
            "first_tick_at": "2026-03-20T09:00:00+00:00",
            "last_tick_at": "2026-03-20T09:00:00+00:00",
        },
    ]


def test_preview_tick_import_rejects_missing_file(client):
    """Preview requires a multipart file upload."""

    headers = _register_and_login(client)

    response = client.post(
        "/api/market-data/tick-imports/preview",
        data={},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert (
        response.get_json()["error"]["message"]
        == "No file provided."
    )


def test_preview_tick_import_rejects_files_without_valid_ticks(client):
    """Preview batch fails when no valid NinjaTrader rows are present."""

    headers = _register_and_login(client)

    response = client.post(
        "/api/market-data/tick-imports/preview",
        data={"file": (BytesIO(b"not a tick line\n"), "ES 06-26.Last.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    batch = response.get_json()
    completed_batch = _poll_preview_batch(
        client,
        headers,
        batch["id"],
    )
    assert completed_batch["status"] == "failed"
    assert (
        completed_batch["error_message"]
        == "No valid NinjaTrader tick rows were found in the file."
    )


def test_get_preview_batch_nonexistent_returns_404(client):
    """Unknown preview batch ids return 404."""

    headers = _register_and_login(client)

    response = client.get(
        "/api/market-data/tick-imports/preview/000000000000000000000000",
        headers=headers,
    )

    assert response.status_code == 404


def test_tick_import_creates_batch_and_reports_progress(client, app):
    """Import endpoint creates datasets and exposes batch progress."""

    headers = _register_and_login(client)
    payload = _load_example_bytes(
        "ES 12-25.25-12-01_25-12-14.Last.txt"
    )

    response = client.post(
        "/api/market-data/tick-imports",
        data={"file": (BytesIO(payload), "ES 06-26.Last.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    batch = response.get_json()
    assert batch["status"] in {"queued", "processing", "completed"}

    completed_batch = batch
    for _ in range(50):
        poll_response = client.get(
            f"/api/market-data/tick-imports/{batch['id']}",
            headers=headers,
        )
        assert poll_response.status_code == 200
        completed_batch = poll_response.get_json()
        if completed_batch["status"] == "completed":
            break
        time.sleep(0.02)

    assert completed_batch["status"] == "completed"
    assert completed_batch["progress"]["processed_percentage"] == 100.0
    assert completed_batch["stats"]["valid_ticks"] == 3
    assert completed_batch["stats"]["days_completed"] == 2
    assert completed_batch["stats"]["datasets_written"] == 10

    with app.app_context():
        from app.extensions import mongo

        stored_datasets = list(
            mongo.db.market_data_datasets.find(
                {"symbol": "ES 06-26"}
            )
        )

    assert len(stored_datasets) == 10


def test_tick_import_uses_explicit_market_data_mapping(
    client, app
):
    """Import resolves dataset symbols through explicit mappings only."""

    headers = _register_and_login(client)
    _update_market_data_mappings(
        client,
        headers,
        {"MES": "ES"},
    )
    payload = _load_example_bytes(
        "ES 12-25.25-12-01_25-12-14.Last.txt"
    )

    response = client.post(
        "/api/market-data/tick-imports",
        data={"file": (BytesIO(payload), "MES 06-26.Last.txt")},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert response.status_code == 202
    batch = response.get_json()

    completed_batch = batch
    for _ in range(50):
        poll_response = client.get(
            f"/api/market-data/tick-imports/{batch['id']}",
            headers=headers,
        )
        assert poll_response.status_code == 200
        completed_batch = poll_response.get_json()
        if completed_batch["status"] == "completed":
            break
        time.sleep(0.02)

    assert completed_batch["status"] == "completed"

    with app.app_context():
        from app.extensions import mongo

        mapped_datasets = list(
            mongo.db.market_data_datasets.find(
                {"symbol": "ES 06-26"}
            )
        )
        original_datasets = list(
            mongo.db.market_data_datasets.find(
                {"symbol": "MES 06-26"}
            )
        )

    assert len(mapped_datasets) == 10
    assert original_datasets == []
