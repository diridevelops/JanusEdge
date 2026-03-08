"""Trade risk and R-multiple helpers."""

from typing import Optional


def calculate_initial_risk_no_fees(
    gross_pnl: float,
) -> float:
    """
    Derive default initial risk without fees.

    Parameters:
        gross_pnl: Profit or loss before fees.

    Returns:
        Absolute gross loss for losing trades, else 0.
    """
    return abs(gross_pnl) if gross_pnl < 0 else 0.0


def calculate_effective_risk(
    initial_risk: float, fee: float = 0.0
) -> Optional[float]:
    """
    Compute the risk denominator used for R-multiple.

    Parameters:
        initial_risk: User-entered initial risk excluding fees.
        fee: Total trade fee.

    Returns:
        Initial risk plus fees when initial risk is defined,
        otherwise None.
    """
    if initial_risk <= 0:
        return None
    return initial_risk + fee


def calculate_r_multiple(
    pnl: float,
    initial_risk: float,
    fee: float = 0.0,
) -> Optional[float]:
    """
    Compute R-multiple using fee-inclusive denominator.

    Parameters:
        pnl: Net profit or loss.
        initial_risk: User-entered initial risk excluding fees.
        fee: Total trade fee.

    Returns:
        R-multiple, or None when risk is undefined.
    """
    effective_risk = calculate_effective_risk(
        initial_risk, fee
    )
    if effective_risk is None:
        return None
    return pnl / effective_risk


def calculate_widened_effective_risk(
    initial_risk: float,
    fee: float,
    r_widening: float,
) -> Optional[float]:
    """
    Compute widened fee-inclusive risk for what-if simulation.

    Parameters:
        initial_risk: User-entered initial risk excluding fees.
        fee: Total trade fee.
        r_widening: Fractional widening of no-fee risk.

    Returns:
        Widened no-fee risk plus fees, or None when the
        initial risk is undefined.
    """
    if initial_risk <= 0:
        return None
    return (initial_risk * (1 + r_widening)) + fee