/** Trade risk and R-multiple helpers. */

/**
 * Default loser risk uses gross loss only so fees remain separate.
 */
export function getInitialRiskNoFees(
  grossPnl: number
): number {
  return grossPnl < 0 ? Math.abs(grossPnl) : 0;
}

/**
 * Effective R denominator adds fees onto the no-fee risk.
 */
export function getEffectiveRisk(
  initialRisk: number,
  fee = 0
): number | null {
  if (!(initialRisk > 0)) {
    return null;
  }
  return initialRisk + fee;
}

/**
 * Compute trade R-multiple using a fee-inclusive denominator.
 */
export function getTradeRMultiple(
  netPnl: number,
  initialRisk: number,
  fee = 0
): number | null {
  const effectiveRisk = getEffectiveRisk(
    initialRisk,
    fee
  );
  if (effectiveRisk === null) {
    return null;
  }
  return netPnl / effectiveRisk;
}