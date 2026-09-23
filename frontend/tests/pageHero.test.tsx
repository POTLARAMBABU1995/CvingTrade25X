import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { PageHero } from '../src/pages/ops/opsPageHelpers';

describe('PageHero', () => {
  test('renders only the title text', () => {
    const markup = renderToStaticMarkup(
      <PageHero title="SECTOR ROTATION" />,
    );

    expect(markup).toContain('SECTOR ROTATION');
    expect(markup).not.toContain('Live sector breadth from the existing sector APIs.');
    expect(markup).not.toContain('Loading');
    expect(markup).not.toContain('Database Automation');
    expect(markup).not.toContain('rounded');
  });
});
