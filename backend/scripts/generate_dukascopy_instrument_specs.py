"""Generate the versioned Dukascopy instrument catalog and verified sizing rows.

The upstream catalog supplies instrument identities, price scale, point size,
and asset groups. Contract multipliers and order limits come from the official
Dukascopy sources listed in the generated JSON. Missing values stay missing;
this script never fills them with a generic lot rule.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
import json
import math
from pathlib import Path
import urllib.request


CATALOG_URL = "https://jetta.dukascopy.com/v1/instruments"
OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "market_data"
    / "data"
    / "dukascopy_instrument_specs_v1.json"
)

SIZING_SOURCES = {
    "forex": "https://www.dukascopy.com/wiki/en/development/strategy-api/orders-and-positions/order-amounts/",
    "cfd_order_limits": "https://www.dukascopy.com/swiss/english/forex/forex-trading-accounts/link/?mob=1",
    "cfd_contract_sizes": "https://www.dukascopy.com/swiss/english/cfd/range-of-markets/",
    "crypto_order_limits": "https://www.dukascopy.com/swiss/english/crypto/range-of-markets/?from=hp",
    "additional_commodity_order_limits": "https://www.dukascopy.com/japan/cfd-services/commodity-cfd-general-info/",
}

FX_GROUPS = {"FX_CROSSES", "FX_MAJORS", "FX_RSRV"}
CRYPTO_ORDER_LIMITS = {
    "BTC": (0.01, 0.01),
    "ETH": (1, 0.1),
    "LTC": (10, 1),
    "BCH": (1, 1),
    "XLM": (2500, 1),
    "DSH": (1, 1),
    "TRX": (2500, 1),
    "ADA": (115, 1),
    "UNI": (5, 1),
    "LNK": (4, 1),
    "AVE": (0.1, 0.1),
    "CMP": (0.1, 0.1),
    "YFI": (0.01, 0.01),
    "BAT": (100, 1),
}
INDEX_ORDER_LIMITS = {
    "CHI.IDX": (0.1, 0.1),
    "DEU.IDX": (0.1, 0.1),
    "DOLLAR.IDX": (100, 100),
    "HKG.IDX": (0.1, 0.1),
    "ITA.IDX": (0.1, 0.1),
    "NLD.IDX": (20, 20),
    "SGD.IDX": (10, 10),
    "USA30.IDX": (0.1, 0.1),
    "VOL.IDX": (10, 1),
}
MEXICO_STOCK_ORDER_LIMITS = {
    "ALFAA.MX": (2000, 2000),
    "ALSEA.MX": (500, 500),
    "AMXL.MX": (1000, 1000),
    "ARCA.MX": (100, 100),
    "ASURB.MX": (50, 50),
    "BBAJIOO.MX": (500, 500),
    "BOLSAA.MX": (500, 500),
    "CEMEXCPO.MX": (2000, 2000),
    "ELEKTRA.MX": (25, 25),
    "FEMSAUBD.MX": (100, 100),
    "GAPB.MX": (100, 100),
    "GCARSOA1.MX": (500, 500),
    "GCC.MX": (250, 250),
    "GFNORTEO.MX": (100, 100),
    "GMEXICOB.MX": (500, 500),
    "GRUMAB.MX": (100, 100),
    "KIMBERA.MX": (500, 500),
    "KOFUBL.MX": (250, 250),
    "LABB.MX": (1000, 1000),
    "LIVEPOLC1.MX": (250, 250),
    "MEGACPO.MX": (500, 500),
    "OMAB.MX": (100, 100),
    "ORBIA.MX": (500, 500),
    "PEOLES.MX": (100, 100),
    "PINFRA.MX": (100, 100),
    "Q.MX": (250, 250),
    "RA.MX": (250, 250),
    "TLEVISACPO.MX": (1000, 1000),
    "VESTA.MX": (500, 500),
    "VOLARA.MX": (1000, 1000),
    "WALMEX.MX": (500, 500),
}
COMMODITY_CONTRACT_SIZES = {
    "BRENT.CMD": 100,
    "LIGHT.CMD": 100,
    "GAS.CMD": 100,
    "COPPER.CMD": 100,
    "DIESEL.CMD": 4,
    "COFFEE.CMD": 1,
    "COCOA.CMD": 1,
    "SUGAR.CMD": 1,
    "COTTON.CMD": 1,
    "OJUICE.CMD": 1,
    "SOYBEAN.CMD": 1,
    "XPT.CMD": 1,
    "XPD.CMD": 1,
}
COMMODITY_ORDER_LIMITS = {
    "BRENT.CMD": (1, 1),
    "LIGHT.CMD": (1, 1),
    "GAS.CMD": (10, 1),
    "COPPER.CMD": (20, 1),
    "DIESEL.CMD": (1, 1),
    "COFFEE.CMD": (500, 10),
    "COCOA.CMD": (1, 1),
    "SUGAR.CMD": (10, 10),
    "COTTON.CMD": (600, 100),
    "OJUICE.CMD": (300, 20),
    "SOYBEAN.CMD": (400, 400),
    "XPT.CMD": (1, 1),
    "XPD.CMD": (1, 0.1),
}


def _load_catalog() -> dict:
    request = urllib.request.Request(
        CATALOG_URL,
        headers={"User-Agent": "JanusEdge instrument-spec snapshot"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(
        payload.get("instruments"), list
    ):
        raise ValueError("Dukascopy returned an invalid instrument catalog.")
    return payload


def _row(source: dict, groups: dict[int, str]) -> dict:
    name = str(source.get("name", "")).strip().upper()
    instrument = str(source.get("code", "")).strip().upper()
    parts = name.split("/")
    base, quote = parts if len(parts) == 2 else ("", "")
    group = groups.get(source.get("groupId"))
    platform_group = source.get("platformGroupId")
    catalog_price_scale = source.get("priceScale")
    pip_size = source.get("pipValue")
    tick_size = (
        10 ** (-catalog_price_scale)
        if isinstance(catalog_price_scale, int) and not isinstance(catalog_price_scale, bool)
        else None
    )
    price_precision = (
        max(0, -Decimal(str(tick_size)).normalize().as_tuple().exponent)
        if tick_size is not None
        else None
    )
    contract_size = min_lots = lot_increment = None
    spec_source = None
    reason = None

    if group in FX_GROUPS:
        # Standard FX lot is 100,000 base units. JForex documents a 1,000-unit
        # minimum and 1-unit increment, represented in lots by these factors.
        contract_size, min_lots, lot_increment = 100_000, 0.01, 0.00001
        spec_source = "jforex_currency_order_amounts"
    elif group == "FX_METALS" and quote == "USD" and base in {"XAU", "XAG"}:
        contract_size = 1  # one ounce per simulator lot
        min_lots, lot_increment = (1, 1) if base == "XAU" else (50, 10)
        spec_source = "dukascopy_bank_metal_order_limits"
    elif group == "FX_METALS":
        reason = (
            "JForex order limits for this metal cross are not published in "
            "the verified sizing sources."
        )
    elif group == "VCCY" and quote == "USD" and base in CRYPTO_ORDER_LIMITS:
        contract_size = 1  # one underlying coin per simulator lot
        min_lots, lot_increment = CRYPTO_ORDER_LIMITS[base]
        spec_source = "dukascopy_crypto_order_limits"
    elif group == "VCCY":
        reason = (
            "A verified JForex order-size rule for this crypto quote pair is "
            "not published in the sizing source."
        )
    elif group and group.startswith("IDX_"):
        contract_size = 1  # one index CFD contract per simulator lot
        min_lots, lot_increment = INDEX_ORDER_LIMITS.get(base, (1, 1))
        spec_source = (
            "dukascopy_instrument_order_limits"
            if base in INDEX_ORDER_LIMITS
            else "dukascopy_other_index_order_limits"
        )
    elif group == "BND_CFD":
        contract_size, min_lots, lot_increment = 1, 10, 1
        spec_source = "dukascopy_bond_order_limits"
    elif group in {"CMD_ENERGY", "CMD_AGRICULTURAL", "CMD_METALS"}:
        contract_size = COMMODITY_CONTRACT_SIZES.get(base)
        limits = COMMODITY_ORDER_LIMITS.get(base)
        if contract_size is not None and limits is not None:
            min_lots, lot_increment = limits
            spec_source = "dukascopy_commodity_contract_and_order_limits"
        else:
            reason = (
                "A verified JForex contract multiplier or order-size rule is "
                "not published for this commodity."
            )
    elif platform_group in {"STK_CASH", "STOCKS", "ETF"} or group in {
        "STCK_CFD",
        "ETF_CFD",
    }:
        contract_size = 1
        limits = MEXICO_STOCK_ORDER_LIMITS.get(base, (1, 1))
        min_lots, lot_increment = limits
        spec_source = (
            "dukascopy_mexico_stock_order_limits"
            if base in MEXICO_STOCK_ORDER_LIMITS
            else "dukascopy_other_stock_order_limits"
        )
    else:
        reason = (
            "No verified JForex contract and order-size specification is "
            "available for this instrument category."
        )

    if (
        isinstance(price_precision, bool)
        or not isinstance(price_precision, int)
        or not 0 <= price_precision <= 15
    ):
        reason = reason or (
            "Dukascopy catalog does not publish a valid price tick scale for "
            "this instrument."
        )
        price_precision = None
        tick_size = None
    try:
        pip_size = float(pip_size)
        if not math.isfinite(pip_size) or pip_size <= 0:
            pip_size = None
    except (TypeError, ValueError, OverflowError):
        pip_size = None
    if pip_size is None:
        reason = reason or (
            "Dukascopy catalog does not publish a valid point size for this "
            "instrument."
        )

    supported = reason is None and all(
        value is not None
        for value in (tick_size, pip_size, contract_size, min_lots, lot_increment)
    )
    if not supported and reason is None:
        reason = "The verified JForex metadata for this instrument is incomplete."
    return {
        "instrument": instrument,
        "name": name,
        "base_currency": base,
        "quote_currency": quote,
        "quote_currency_unit_scale": {"USX": 0.01, "GBX": 0.01}.get(quote, 1),
        "pip_size": pip_size,
        "tick_size": tick_size,
        "price_precision": price_precision,
        "contract_size": contract_size,
        "min_lots": min_lots,
        "lot_increment": lot_increment,
        "supported_for_simulation": supported,
        "reason": reason,
        "spec_source": spec_source,
        "catalog_group": group,
        "platform_group": platform_group,
    }


def main() -> None:
    catalog = _load_catalog()
    groups = {row["id"]: row["code"] for row in catalog.get("groups", [])}
    instruments = sorted(
        (_row(source, groups) for source in catalog["instruments"]),
        key=lambda row: row["instrument"],
    )
    names = [row["instrument"] for row in instruments]
    if len(names) != len(set(names)):
        raise ValueError("Dukascopy catalog contains duplicate instrument codes.")
    document = {
        "spec_version": f"dukascopy-catalog-{date.today().isoformat()}-v1",
        "catalog_source": CATALOG_URL,
        "catalog_retrieved_at_utc": date.today().isoformat(),
        "sizing_sources": SIZING_SOURCES,
        "instruments": instruments,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(document, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    supported_count = sum(row["supported_for_simulation"] for row in instruments)
    print(
        f"Wrote {len(instruments)} symbols ({supported_count} sized, "
        f"{len(instruments) - supported_count} requiring metadata) to {OUTPUT_PATH}."
    )
    print("Unsupported categories:", Counter(
        row["reason"] for row in instruments if not row["supported_for_simulation"]
    ))


if __name__ == "__main__":
    main()
