import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const stylesheet = readFileSync(new URL('./backtest-candlekit.css', import.meta.url), 'utf8');

describe('Backtest replay layout', () => {
  it('keeps the trading sidebar beside the charts at all viewport widths', () => {
    const layoutRule = stylesheet.match(
      /^\.backtest-simulation-layout\s*\{([^}]*)\}/m
    )?.[1] ?? '';

    expect(layoutRule).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+clamp\(240px,\s*30vw,\s*350px\)/);
  });

  it('stretches the maximized chart and trading columns to the available height', () => {
    const maximizedRule = stylesheet.match(
      /\.backtest-simulation-layout-maximized\s*\{([^}]*)\}/
    )?.[1] ?? '';

    expect(maximizedRule).toMatch(/flex:\s*1/);
    expect(maximizedRule).toMatch(/(?:^|;)\s*align-items:\s*stretch\s*(?:;|$)/);
  });

  it('collapses the trading sidebar into a full-height narrow rail', () => {
    const collapsedRule = stylesheet.match(
      /\.backtest-simulation-layout\.backtest-simulation-layout-sidebar-collapsed\s*\{([^}]*)\}/
    )?.[1] ?? '';
    const sidebarRule = stylesheet.match(
      /^\.backtest-simulation-sidebar\s*\{([^}]*)\}/m
    )?.[1] ?? '';
    const railRule = stylesheet.match(
      /\.backtest-simulation-sidebar\.is-collapsed\s*\{([^}]*)\}/
    )?.[1] ?? '';
    const toggleRule = stylesheet.match(
      /\.backtest-simulation-sidebar\.is-collapsed\s+\.backtest-simulation-sidebar-toggle\s*\{([^}]*)\}/
    )?.[1] ?? '';

    expect(collapsedRule).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s+28px/);
    expect(sidebarRule).toMatch(/align-self:\s*stretch/);
    expect(railRule).toMatch(/align-self:\s*stretch/);
    expect(toggleRule).toMatch(/height:\s*100%/);
  });

  it('makes the entry panel and reset control fill the sidebar width', () => {
    expect(stylesheet).toMatch(/\.backtest-simulation-sidebar\s+\.backtest-simulation-sidebar-content\s*>\s*\.backtest-entry-panel\s*\{\s*width:\s*100%/);
    expect(stylesheet).toMatch(/\.backtest-simulation-sidebar-content\s*>\s*\.backtest-simulation-reset\s*\{\s*width:\s*100%/);
  });
});
