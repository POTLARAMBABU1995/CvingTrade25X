import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { TechnicalSearchInput } from '../src/components/app/TechnicalSearchInput';

describe('TechnicalSearchInput', () => {
  test('hides the visible decor prefix when requested', () => {
    const markup = renderToStaticMarkup(
      <TechnicalSearchInput value="" onChange={() => undefined} showDecor={false} />,
    );

    expect(markup).toContain('Search NSE/BSE symbols');
    expect(markup).not.toContain('sr-search__decor');
  });
});
