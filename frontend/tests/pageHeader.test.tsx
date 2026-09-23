import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { PageHeader } from '../src/components/ui/PageHeader';

describe('PageHeader', () => {
  test('renders only the title text', () => {
    const markup = renderToStaticMarkup(
      <PageHeader title="Portfolio Gallery" />,
    );

    expect(markup).toContain('Portfolio Gallery');
    expect(markup).not.toContain('Database Automation');
    expect(markup).not.toContain('Banner copy that should no longer be visible.');
    expect(markup).not.toContain('Action');
    expect(markup).not.toContain('Badge');
    expect(markup).not.toContain('rounded');
  });
});
