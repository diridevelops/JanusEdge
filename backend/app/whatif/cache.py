"""Shared cache storage for What-if simulations."""

from typing import Any, Dict, Tuple


_sim_cache: Dict[str, Tuple[float, Any]] = {}
_CACHE_TTL = 300  # seconds


def clear_simulation_cache() -> None:
    """Clear all cached What-if simulation results."""
    _sim_cache.clear()