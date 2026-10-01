import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const stylesheet = readFileSync(new URL('./backtest-candlekit.css', import.meta.url), 'utf8');

describe('Backtest replay layout', () => {
  it('stretches the chart column to fill the available grid height', () => {
    const maximizedRule = stylesheet.match(
      /\.backtest-simulation-layout-maximized\s*\{([^}]*)\}/
    )?.[1] ?? '';

    expect(maximizedRule).toMatch(/(?:^|;)\s*align-items:\s*stretch\s*(?:;|$)/);
  });

  it('reserves a narrow grid column when the simulated trading sidebar is collapsed', () => {
    const collapsedRule = stylesheet.match(
      /\.backtest-simulation-layout-sidebar-collapsed\s*\{([^}]*)\}/
    )?.[1] ?? '';

    expect(collapsedRule).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+42px/);
    expect(stylesheet).toMatch(/\.backtest-simulation-sidebar\.is-collapsed/);
  });
});
