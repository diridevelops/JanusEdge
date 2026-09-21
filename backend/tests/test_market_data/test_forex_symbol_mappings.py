"""Tests for nested forex symbol-mapping configuration."""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.market_data.symbol_mapper import (
    get_default_symbol_mappings,
    validate_symbol_mappings,
)


@pytest.fixture(autouse=True)
def clean_users(app):
    """Keep settings-route tests isolated from other test users."""

    with app.app_context():
        from app.extensions import mongo

        mongo.db.users.delete_many({})
        mongo.db.auth_refresh_sessions.delete_many({})
    yield


def _register_and_login(client) -> str:
    """Register a unique settings test user and return its access token."""

    username = f"forex-settings-{uuid4().hex}"
    register_response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "TestPass123!",
            "timezone": "America/New_York",
        },
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": "TestPass123!",
        },
    )
    assert login_response.status_code == 200
    return login_response.get_json()["token"]


def _auth(token: str) -> dict[str, str]:
    """Return an authorization header for a test token."""

    return {"Authorization": f"Bearer {token}"}


def _custom_forex_mapping() -> dict:
    """Return a complete mapping set with one non-default forex pair."""

    mappings = deepcopy(get_default_symbol_mappings())
    mappings.setdefault("forex", {})
    mappings["forex"]["GBP/EUR"] = {
        "base_currency": "GBP",
        "quote_currency": "EUR",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }
    return mappings


def test_default_symbol_mappings_include_main_forex_pairs():
    """Built-in settings contain the approved main pairs and BTC/USD."""

    mappings = get_default_symbol_mappings()

    assert mappings["MES"] == {
        "dollar_value_per_point": 5.0,
    }
    assert set(mappings["forex"]) == {
        "EUR/USD",
        "GBP/USD",
        "AUD/USD",
        "NZD/USD",
        "USD/JPY",
        "USD/CHF",
        "USD/CAD",
        "BTC/USD",
    }
    assert mappings["forex"]["EUR/USD"] == {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }
    assert mappings["forex"]["USD/JPY"] == {
        "base_currency": "USD",
        "quote_currency": "JPY",
        "pip_size": 0.01,
        "price_precision": 3,
        "contract_size": 100000,
    }
    assert mappings["forex"]["BTC/USD"] == {
        "base_currency": "BTC",
        "quote_currency": "USD",
        "pip_size": 1.0,
        "price_precision": 2,
        "contract_size": 1,
    }


def test_validate_symbol_mappings_keeps_futures_top_level_and_normalizes_forex():
    """Forex entries are nested while legacy futures remain top-level."""

    normalized = validate_symbol_mappings(
        {
            "mes": {"dollar_value_per_point": 5},
            "forex": {
                "gbp/eur": {
                    "base_currency": "gbp",
                    "quote_currency": "eur",
                    "pip_size": 0.0001,
                    "price_precision": 5,
                }
            },
        }
    )

    assert normalized["MES"] == {
        "dollar_value_per_point": 5.0,
    }
    assert normalized["forex"]["GBP/EUR"] == {
        "base_currency": "GBP",
        "quote_currency": "EUR",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }


def test_validate_symbol_mappings_defaults_custom_forex_contract_size():
    """A new forex pair defaults to 100,000 base-currency units."""

    normalized = validate_symbol_mappings(
        {
            "forex": {
                "GBP/EUR": {
                    "base_currency": "GBP",
                    "quote_currency": "EUR",
                    "pip_size": 0.0001,
                    "price_precision": 5,
                }
            }
        }
    )

    assert normalized["forex"]["GBP/EUR"]["contract_size"] == 100000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pip_size", 0),
        ("price_precision", -1),
        ("price_precision", 2.5),
        ("contract_size", 0),
        ("base_currency", ""),
    ],
)
def test_validate_symbol_mappings_rejects_invalid_forex_fields(
    field, value
):
    """Invalid forex metadata cannot enter the settings model."""

    entry = {
        "base_currency": "GBP",
        "quote_currency": "EUR",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }
    entry[field] = value

    with pytest.raises(ValueError):
        validate_symbol_mappings(
            {"forex": {"GBP/EUR": entry}}
        )


def test_validate_symbol_mappings_rejects_pair_currency_mismatches():
    """The pair key and base/quote fields must describe the same pair."""

    entry = {
        "base_currency": "EUR",
        "quote_currency": "USD",
        "pip_size": 0.0001,
        "price_precision": 5,
        "contract_size": 100000,
    }

    with pytest.raises(ValueError):
        validate_symbol_mappings(
            {"forex": {"GBP/EUR": entry}}
        )


@pytest.mark.parametrize(
    "pair_key",
    ["GBPEUR", "GBP-EUR", "GBP/", "/EUR", "GBP/EUR/USD"],
)
def test_validate_symbol_mappings_rejects_non_canonical_pairs(pair_key):
    """Forex keys must use canonical uppercase slash notation."""

    with pytest.raises(ValueError):
        validate_symbol_mappings(
            {
                "forex": {
                    pair_key: {
                        "base_currency": "GBP",
                        "quote_currency": "EUR",
                        "pip_size": 0.0001,
                        "price_precision": 5,
                        "contract_size": 100000,
                    }
                }
            }
        )


def test_update_symbol_mappings_persists_custom_forex_mapping(
    client,
):
    """The settings API persists nested forex mappings unchanged."""

    token = _register_and_login(client)
    mappings = _custom_forex_mapping()

    response = client.put(
        "/api/auth/symbol-mappings",
        headers=_auth(token),
        json={"symbol_mappings": mappings},
    )

    assert response.status_code == 200
    assert response.get_json()["symbol_mappings"] == mappings

    profile_response = client.get(
        "/api/auth/me",
        headers=_auth(token),
    )
    assert profile_response.status_code == 200
    assert profile_response.get_json()["symbol_mappings"] == mappings


def test_update_symbol_mappings_rejects_forex_currency_mismatch(client):
    """The settings endpoint rejects a pair with inconsistent currencies."""

    token = _register_and_login(client)
    mappings = _custom_forex_mapping()
    mappings["forex"]["GBP/EUR"]["quote_currency"] = "USD"

    response = client.put(
        "/api/auth/symbol-mappings",
        headers=_auth(token),
        json={"symbol_mappings": mappings},
    )

    assert response.status_code == 400
