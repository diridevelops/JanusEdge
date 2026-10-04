"""Regressions for the versioned Dukascopy instrument sizing table."""

from app.market_data.symbol_mapper import get_default_instrument_mappings


def test_mexican_stock_order_limits_match_instrument_specific_schedule():
    """Mexican stocks use the published share minima and increments."""
    mappings = get_default_instrument_mappings()

    assert (mappings["ALFAA.MX-MXN"]["min_lots"], mappings["ALFAA.MX-MXN"]["lot_increment"]) == (2000, 2000)
    assert (mappings["AMXL.MX-MXN"]["min_lots"], mappings["AMXL.MX-MXN"]["lot_increment"]) == (1000, 1000)
    assert (mappings["ARCA.MX-MXN"]["min_lots"], mappings["ARCA.MX-MXN"]["lot_increment"]) == (100, 100)
    assert (mappings["ASURB.MX-MXN"]["min_lots"], mappings["ASURB.MX-MXN"]["lot_increment"]) == (50, 50)
    assert mappings["WALMEX.MX-MXN"]["spec_source"] == "dukascopy_mexico_stock_order_limits"


def test_other_stock_rule_represents_one_share_per_lot():
    """The published general stock schedule maps one lot to one share."""
    mapping = get_default_instrument_mappings()["AAPL.US-USD"]

    assert mapping["contract_size"] == 1
    assert mapping["min_lots"] == 1
    assert mapping["lot_increment"] == 1
    assert mapping["spec_source"] == "dukascopy_other_stock_order_limits"


def test_mexican_stock_schedule_is_used_by_the_generator():
    """Future catalog refreshes preserve the explicit Mexico exceptions."""
    from pathlib import Path
    import runpy

    generator = Path(__file__).resolve().parents[2] / "scripts" / "generate_dukascopy_instrument_specs.py"
    schedule = runpy.run_path(str(generator))["MEXICO_STOCK_ORDER_LIMITS"]

    assert schedule["ALFAA.MX"] == (2000, 2000)
    assert schedule["WALMEX.MX"] == (500, 500)
