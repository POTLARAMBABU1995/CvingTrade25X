import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { FyersHoldingsPage, getNextHoldingFormExpandedState } from '../src/pages/fyers/FyersHoldingsPage';

describe('FyersHoldingsPage create holding panel', () => {
  test('renders a right-side expand collapse button on the create holding header', () => {
    const markup = renderToStaticMarkup(<FyersHoldingsPage />);

    expect(markup).toContain('Create Holding');
    expect(markup).toContain('Verify P&amp;L');
    expect(markup).toContain('fyers-holdings-form-toggle');
    expect(markup).toContain('aria-controls="fyers-holdings-form-panel"');
    expect(markup).toContain('aria-expanded="true"');
    expect(markup).toContain('aria-label="Hide create holding form"');
    expect(markup).toContain('>-</button>');
  });

  test('keeps manual toggle separate while edit always expands the form', () => {
    expect(getNextHoldingFormExpandedState(true, 'toggle')).toBe(false);
    expect(getNextHoldingFormExpandedState(false, 'toggle')).toBe(true);
    expect(getNextHoldingFormExpandedState(false, 'edit')).toBe(true);
    expect(getNextHoldingFormExpandedState(true, 'edit')).toBe(true);
  });
});
