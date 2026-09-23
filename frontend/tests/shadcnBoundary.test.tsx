import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { Input } from '../src/components/ui/Input';
import { Select } from '../src/components/ui/Select';
import { Skeleton } from '../src/components/ui/Skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../src/components/ui/Tabs';

describe('shadcn compatibility boundary', () => {
  test('renders tabs with active trigger and active content only', () => {
    const markup = renderToStaticMarkup(
      <Tabs value="Overview" onValueChange={() => undefined}>
        <TabsList>
          <TabsTrigger value="Overview">Overview</TabsTrigger>
          <TabsTrigger value="Peers">Peers</TabsTrigger>
        </TabsList>
        <TabsContent value="Overview">Summary content</TabsContent>
        <TabsContent value="Peers">Peer content</TabsContent>
      </Tabs>,
    );

    expect(markup).toContain('role="tablist"');
    expect(markup).toContain('aria-selected="true"');
    expect(markup).toContain('Summary content');
    expect(markup).not.toContain('Peer content');
  });

  test('renders input, select, and skeleton primitives with data slots', () => {
    const markup = renderToStaticMarkup(
      <div>
        <Input variant="light" placeholder="Search symbol" />
        <Select variant="light" defaultValue="NSE">
          <option value="NSE">NSE</option>
          <option value="BSE">BSE</option>
        </Select>
        <Skeleton variant="light" className="h-10" />
      </div>,
    );

    expect(markup).toContain('data-slot="input"');
    expect(markup).toContain('data-slot="select"');
    expect(markup).toContain('data-slot="skeleton"');
    expect(markup).toContain('Search symbol');
  });
});
