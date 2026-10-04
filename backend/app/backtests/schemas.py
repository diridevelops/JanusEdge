"""Persistence and API schema helpers for Backtest resources."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import math
from typing import Any

from bson import ObjectId

from app.utils.datetime_utils import utc_now


RUN_STATUSES = frozenset({"selecting_period", "preparing", "ready", "complete", "deleting"})
PRICE_MODE = "combined_midpoint"
SOURCE_SIDE = "COMB"
VOLUME_SEMANTICS = "two_sided_quote_liquidity"
DEFAULT_CANDLEKIT_VERSION = "0.1.0"
DRAWING_SCHEMA_VERSION = 1
# A generous v1 limit for a chart drawing export that remains well below
# MongoDB's 16 MiB document limit, leaving room for BSON metadata and indexes.
MAX_DRAWING_STATE_BYTES = 1_048_576
CHART_WORKSPACE_SCHEMA_VERSION = 1
CHART_WORKSPACE_LAYOUT_ENGINE = "flexlayout-react"
BACKTEST_CHART_PANEL_TYPE = "backtest-chart"
DEFAULT_INITIAL_BALANCE_USD = 10_000.0
DEFAULT_RISK_PERCENT = 1.0
DEFAULT_SIMULATION_EXECUTION_COSTS = {
    "total_spread_pips": 0.0,
    "slippage_pips": 0.0,
    "commission_usd_per_lot_per_side": 0.0,
}


def create_backtest_run_doc(
    *,
    run_id: ObjectId,
    user_id: ObjectId,
    account_id: ObjectId,
    preparation_job_id: ObjectId,
    instrument: str,
    start_date: date,
    end_date: date,
    display_timezone: str,
    start_utc_ms: int,
    end_utc_ms: int,
    context_start_utc_ms: int,
    warmup_days: int = 0,
    blind_mode: bool = False,
    initial_balance_usd: float = DEFAULT_INITIAL_BALANCE_USD,
    risk_percent: float = DEFAULT_RISK_PERCENT,
    execution_costs: dict[str, float] | None = None,
    instrument_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a preparing run document with stable source semantics."""
    now = utc_now()
    return {
        "_id": run_id,
        "user_id": user_id,
        "instrument": instrument,
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "display_timezone": display_timezone,
        "start_utc_ms": start_utc_ms,
        "end_utc_ms": end_utc_ms,
        "context_start_utc_ms": context_start_utc_ms,
        "warmup_days": warmup_days,
        "source": "dukascopy",
        "source_interval_minutes": 1,
        "source_side": SOURCE_SIDE,
        "price_mode": PRICE_MODE,
        "volume_semantics": VOLUME_SEMANTICS,
        "period_selection": "manual",
        "period_months": None,
        "blind_mode": blind_mode,
        "normalized_reference_price": None,
        "initial_balance_usd": initial_balance_usd,
        "current_balance_usd": initial_balance_usd,
        "risk_percent": risk_percent,
        "execution_costs": dict(
            execution_costs or DEFAULT_SIMULATION_EXECUTION_COSTS
        ),
        "instrument_metadata": instrument_metadata,
        "status": "preparing",
        "progress": {"stage": "downloading", "percent": None},
        "account_id": account_id,
        "preparation_job_id": preparation_job_id,
        "snapshot": None,
        "coverage": None,
        "warmup_coverage": None,
        "replay_cursor": None,
        "created_at": now,
        "updated_at": now,
    }


def create_selecting_period_run_doc(
    *,
    run_id: ObjectId,
    user_id: ObjectId,
    preparation_job_id: ObjectId,
    instrument: str,
    display_timezone: str,
    period_months: int,
    selection_as_of_date: date,
    warmup_days: int = 0,
    blind_mode: bool = False,
    initial_balance_usd: float = DEFAULT_INITIAL_BALANCE_USD,
    risk_percent: float = DEFAULT_RISK_PERCENT,
    execution_costs: dict[str, float] | None = None,
    instrument_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a run that has no selected dates or account yet."""
    now = utc_now()
    return {
        "_id": run_id,
        "user_id": user_id,
        "instrument": instrument,
        "requested_start_date": None,
        "requested_end_date": None,
        "display_timezone": display_timezone,
        "start_utc_ms": None,
        "end_utc_ms": None,
        "context_start_utc_ms": None,
        "source": "dukascopy",
        "source_interval_minutes": 1,
        "source_side": SOURCE_SIDE,
        "price_mode": PRICE_MODE,
        "volume_semantics": VOLUME_SEMANTICS,
        "period_selection": "random",
        "period_months": period_months,
        "warmup_days": warmup_days,
        "blind_mode": blind_mode,
        "normalized_reference_price": None,
        "initial_balance_usd": initial_balance_usd,
        "current_balance_usd": initial_balance_usd,
        "risk_percent": risk_percent,
        "execution_costs": dict(
            execution_costs or DEFAULT_SIMULATION_EXECUTION_COSTS
        ),
        "instrument_metadata": instrument_metadata,
        "selection_as_of_date": selection_as_of_date.isoformat(),
        "status": "selecting_period",
        "progress": {"stage": "selecting_period", "percent": None},
        "account_id": None,
        "preparation_job_id": preparation_job_id,
        "snapshot": None,
        "coverage": None,
        "warmup_coverage": None,
        "replay_cursor": None,
        "created_at": now,
        "updated_at": now,
    }


def create_preparation_job_doc(
    *,
    job_id: ObjectId,
    user_id: ObjectId,
    run_id: ObjectId,
    instrument: str,
    requested_start_date: date,
    requested_end_date: date,
    context_start_utc_date: date,
    end_utc_date: date,
    staging_prefix: str,
) -> dict[str, Any]:
    """Build the durable queued preparation job for a run."""
    now = utc_now()
    return {
        "_id": job_id,
        "user_id": user_id,
        "run_id": run_id,
        "instrument": instrument,
        "requested_start_date": requested_start_date.isoformat(),
        "requested_end_date": requested_end_date.isoformat(),
        "state": "queued",
        "lease_owner": None,
        "lease_expires_at": None,
        "attempt_count": 0,
        "completed_utc_dates": [],
        "context_start_utc_date": datetime.combine(
            context_start_utc_date, time.min, tzinfo=timezone.utc
        ),
        "next_utc_date": datetime.combine(
            context_start_utc_date, time.min, tzinfo=timezone.utc
        ),
        "end_utc_date": datetime.combine(
            end_utc_date, time.min, tzinfo=timezone.utc
        ),
        "staging_prefix": staging_prefix,
        "created_at": now,
        "updated_at": now,
    }


def create_random_selection_job_doc(
    *,
    job_id: ObjectId,
    user_id: ObjectId,
    run_id: ObjectId,
    instrument: str,
    period_months: int,
    as_of_date: date,
    minimum_start_date: date,
    maximum_start_date: date,
    staging_prefix: str,
    blind_mode: bool = False,
) -> dict[str, Any]:
    """Build a durable selection job with a fixed cutoff and recovery state."""
    now = utc_now()
    return {
        "_id": job_id,
        "user_id": user_id,
        "run_id": run_id,
        "instrument": instrument,
        "requested_start_date": None,
        "requested_end_date": None,
        "state": "queued",
        "lease_owner": None,
        "lease_expires_at": None,
        "attempt_count": 0,
        "completed_utc_dates": [],
        "context_start_utc_date": None,
        "next_utc_date": None,
        "end_utc_date": None,
        "staging_prefix": staging_prefix,
        "blind_mode": blind_mode,
        "selection": {
            "status": "searching",
            "as_of_date": as_of_date.isoformat(),
            "period_months": period_months,
            "minimum_start_date": minimum_start_date.isoformat(),
            "maximum_start_date": maximum_start_date.isoformat(),
            "years_remaining": list(
                range(minimum_start_date.year, maximum_start_date.year + 1)
            ),
            "current_year": None,
            "tried_dates": [],
            "pending_date": None,
            "selected_start_date": None,
            "selected_end_date": None,
            "account_id": None,
        },
        "created_at": now,
        "updated_at": now,
    }


def serialize_backtest_value(value):
    """Recursively convert BSON and date values to JSON-compatible data."""
    if isinstance(value, ObjectId):
        return str(value)
    # MongoDB returns UTC datetimes as naive values by default. Preserve the
    # UTC meaning in API responses rather than exposing a timezone-less time.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            ("id" if key == "_id" else key): serialize_backtest_value(item)
            for key, item in value.items()
            if key
            not in {
                "user_id",
                "preparation_lease_owner",
                "preparation_lease_expires_at",
                "preparation_lease_generation",
                "lease_owner",
                "lease_expires_at",
            }
            and (not key.startswith("_") or key == "_id")
        }
    if isinstance(value, list):
        return [serialize_backtest_value(item) for item in value]
    return value


def serialize_run(run: dict, account: dict | None = None) -> dict:
    """Serialize a run and its account label for the public API."""
    result = serialize_backtest_value(run)
    result.setdefault("blind_mode", bool(run.get("blind_mode", False)))
    result.setdefault("normalized_reference_price", None)
    result.setdefault("initial_balance_usd", DEFAULT_INITIAL_BALANCE_USD)
    result.setdefault("current_balance_usd", result["initial_balance_usd"])
    result.setdefault("risk_percent", DEFAULT_RISK_PERCENT)
    if result["blind_mode"]:
        # Older linked accounts may still have a date-bearing persisted label.
        run_id = result.get("id", run.get("_id"))
        blind_label = "blind-manual" if run.get("source") == "manual" else "blind"
        result["account_label"] = (
            f"Backtest {result['instrument']} {blind_label} ({run_id})"
            if run_id is not None
            else f"Backtest {result['instrument']} {blind_label}"
        )
    elif account is not None:
        result["account_label"] = account.get("display_name") or account.get(
            "account_name"
        )
    return result


def serialize_notice(notice: dict) -> dict:
    """Serialize a user-facing preparation notice."""
    return serialize_backtest_value(notice)


def serialize_drawing_state(document: dict | None, interval_minutes: int) -> dict:
    """Return the stable drawing-state API shape for saved or empty state."""
    if document is None:
        return {
            "interval_minutes": interval_minutes,
            "candlekit_version": DEFAULT_CANDLEKIT_VERSION,
            "schema_version": DRAWING_SCHEMA_VERSION,
            "revision": 0,
            "serialized_state": None,
        }
    return {
        "interval_minutes": document["interval_minutes"],
        "candlekit_version": document["candlekit_version"],
        "schema_version": document["schema_version"],
        "revision": document["revision"],
        "serialized_state": document["serialized_state"],
    }


def _workspace_interval(value, field_name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > 1440
    ):
        raise ValueError(
            f"{field_name} must be a whole number from 1 to 1440."
        )
    return value


def _validate_workspace_weight(node: dict) -> None:
    if "weight" not in node:
        return
    weight = node["weight"]
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or weight <= 0
        or weight > 100
        or (isinstance(weight, float) and not math.isfinite(weight))
    ):
        raise ValueError("Workspace split weights must be from 0 to 100.")


def validate_chart_workspace(workspace: Any, run_id: str) -> dict:
    """Validate and normalize a FlexLayout workspace for one ready run."""
    if not isinstance(workspace, dict):
        raise ValueError("workspace must be an object.")
    version = workspace.get("schema_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != CHART_WORKSPACE_SCHEMA_VERSION
    ):
        raise ValueError("workspace.schema_version is not supported.")
    if workspace.get("layout_engine") != CHART_WORKSPACE_LAYOUT_ENGINE:
        raise ValueError("workspace.layout_engine is not supported.")
    if workspace.get("id") != run_id:
        raise ValueError("workspace.id must match the Backtest run.")
    if workspace.get("name") != "default":
        raise ValueError("workspace.name must be default.")

    tree = workspace.get("tree")
    if not isinstance(tree, dict):
        raise ValueError("workspace.tree must be an object.")
    if not isinstance(tree.get("global"), dict):
        raise ValueError("workspace.tree.global must be an object.")
    if not isinstance(tree.get("borders"), list):
        raise ValueError("workspace.tree.borders must be an array.")
    if not isinstance(tree.get("layout"), dict):
        raise ValueError("workspace.tree.layout must be an object.")

    panel_map = workspace.get("panels")
    if not isinstance(panel_map, dict):
        raise ValueError("workspace.panels must be an object.")
    normalized_panels = {}
    for panel_id, panel in panel_map.items():
        if not isinstance(panel_id, str) or not panel_id.strip():
            raise ValueError("Workspace panel ids must be nonempty strings.")
        if not isinstance(panel, dict) or panel.get("id") != panel_id:
            raise ValueError("Workspace panel metadata must match its key.")
        if panel.get("type") != BACKTEST_CHART_PANEL_TYPE:
            raise ValueError("Only Backtest chart panels are supported.")
        normalized_panels[panel_id] = {
            "id": panel_id,
            "type": BACKTEST_CHART_PANEL_TYPE,
            "interval_minutes": _workspace_interval(
                panel.get("interval_minutes"),
                f"workspace.panels.{panel_id}.interval_minutes",
            ),
        }

    tab_ids: set[str] = set()
    node_ids: set[str] = set()

    def validate_node(node: Any, field_name: str, *, is_root=False) -> None:
        if not isinstance(node, dict):
            raise ValueError(f"{field_name} must be an object.")
        node_type = node.get("type")
        if is_root and node_type != "row":
            raise ValueError("workspace.tree.layout must be a FlexLayout row.")
        _validate_workspace_weight(node)
        node_id = node.get("id")
        if node_id is not None:
            if not isinstance(node_id, str) or not node_id.strip():
                raise ValueError("FlexLayout node ids must be nonempty strings.")
            if node_id in node_ids:
                raise ValueError("FlexLayout node ids must be unique.")
            node_ids.add(node_id)

        if node_type in {"row", "tabset"}:
            children = node.get("children")
            if not isinstance(children, list) or not children:
                raise ValueError(f"{field_name}.children must not be empty.")
            if node_type == "row":
                if any(
                    not isinstance(child, dict)
                    or child.get("type") not in {"row", "tabset"}
                    for child in children
                ):
                    raise ValueError("FlexLayout rows may contain only rows or tabsets.")
                for index, child in enumerate(children):
                    validate_node(child, f"{field_name}.children[{index}]")
                return

            selected = node.get("selected", 0)
            if (
                isinstance(selected, bool)
                or not isinstance(selected, int)
                or selected < 0
                or selected >= len(children)
            ):
                raise ValueError(f"{field_name}.selected is outside its tabset.")
            for index, child in enumerate(children):
                if not isinstance(child, dict) or child.get("type") != "tab":
                    raise ValueError("FlexLayout tabsets may contain only tabs.")
                validate_node(child, f"{field_name}.children[{index}]")
            return

        if node_type != "tab":
            raise ValueError(f"{field_name}.type is not supported.")
        tab_id = node.get("id")
        title = node.get("name")
        if not isinstance(tab_id, str) or not tab_id.strip():
            raise ValueError("Chart tab ids must be nonempty strings.")
        if tab_id in tab_ids:
            raise ValueError("Chart tab ids must be unique.")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Chart tab names must be nonempty strings.")
        if node.get("component") != BACKTEST_CHART_PANEL_TYPE:
            raise ValueError("Only Backtest chart tabs are supported.")
        config = node.get("config")
        if (
            not isinstance(config, dict)
            or config.get("id") != tab_id
            or config.get("kind") != BACKTEST_CHART_PANEL_TYPE
            or not isinstance(config.get("config"), dict)
        ):
            raise ValueError("Chart tab config must identify its Backtest panel.")
        interval = _workspace_interval(
            config["config"].get("interval_minutes"),
            f"workspace.tree panel {tab_id}.interval_minutes",
        )
        panel = normalized_panels.get(tab_id)
        if panel is None or panel["interval_minutes"] != interval:
            raise ValueError("Workspace tree and panel metadata must correspond.")
        tab_ids.add(tab_id)

    validate_node(tree["layout"], "workspace.tree.layout", is_root=True)

    # FlexLayout can dock tabs into a border. Such tabs are still visible chart
    # panels and must participate in the same identity and minimum-one checks.
    for index, border in enumerate(tree["borders"]):
        if not isinstance(border, dict) or border.get("type") != "border":
            raise ValueError(f"workspace.tree.borders[{index}] is invalid.")
        children = border.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"workspace.tree.borders[{index}].children must be an array.")
        selected = border.get("selected", 0)
        if children and (
            isinstance(selected, bool)
            or not isinstance(selected, int)
            or selected < 0
            or selected >= len(children)
        ):
            raise ValueError(f"workspace.tree.borders[{index}].selected is invalid.")
        for child_index, child in enumerate(children):
            if not isinstance(child, dict) or child.get("type") != "tab":
                raise ValueError("Workspace borders may contain only chart tabs.")
            validate_node(child, f"workspace.tree.borders[{index}].children[{child_index}]")

    if not tab_ids:
        raise ValueError("A chart workspace must contain at least one chart panel.")
    if tab_ids != set(normalized_panels):
        raise ValueError("Workspace tree and panel metadata must correspond.")

    return {
        "schema_version": CHART_WORKSPACE_SCHEMA_VERSION,
        "layout_engine": CHART_WORKSPACE_LAYOUT_ENGINE,
        "id": run_id,
        "name": "default",
        "tree": tree,
        "panels": normalized_panels,
    }


def serialize_chart_workspace(document: dict | None) -> dict | None:
    """Serialize only public workspace metadata, omitting Mongo ownership keys."""
    if document is None:
        return None
    return serialize_backtest_value(
        {
            key: document[key]
            for key in (
                "schema_version",
                "layout_engine",
                "id",
                "name",
                "revision",
                "created_at",
                "updated_at",
                "tree",
                "panels",
            )
        }
    )
