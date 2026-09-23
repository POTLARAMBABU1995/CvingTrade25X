import type * as React from 'react';

declare global {
  namespace JSX {
    interface IntrinsicElements {
      marquee: React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        direction?: string;
        height?: number | string;
        scrollamount?: number | string;
        width?: number | string;
      };
    }
  }
}

export {};
