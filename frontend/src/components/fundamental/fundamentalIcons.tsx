import type { SVGProps } from 'react';

function baseIconProps(props: SVGProps<SVGSVGElement>) {
  return {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    ...props,
  };
}

export function FundamentalSearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-3.4-3.4" />
    </svg>
  );
}

export function FundamentalTrendUpIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M4 17 10 11l4 4 6-8" />
      <path d="M14 7h6v6" />
    </svg>
  );
}

export function FundamentalTrendDownIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M4 7 10 13l4-4 6 8" />
      <path d="M14 17h6v-6" />
    </svg>
  );
}

export function FundamentalShieldIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M12 3 19 6v5c0 4.5-2.8 8-7 10-4.2-2-7-5.5-7-10V6l7-3Z" />
      <path d="m9 12 2 2 4-5" />
    </svg>
  );
}

export function FundamentalAlertIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="m12 3 9 16H3L12 3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

export function FundamentalWalletIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M4 7h14a2 2 0 0 1 2 2v9H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h12" />
      <path d="M16 13h4" />
      <path d="M16 13a1 1 0 1 0 0 .01" />
    </svg>
  );
}

export function FundamentalBuildingIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M4 21V6l8-3 8 3v15" />
      <path d="M9 21v-6h6v6" />
      <path d="M8 9h.01M12 9h.01M16 9h.01M8 13h.01M12 13h.01M16 13h.01" />
    </svg>
  );
}

export function FundamentalScaleIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M12 3v18" />
      <path d="M5 7h14" />
      <path d="m6 7-3 6h6L6 7Z" />
      <path d="m18 7-3 6h6l-3-6Z" />
    </svg>
  );
}

export function FundamentalChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M4 19h16" />
      <path d="M7 16V9" />
      <path d="M12 16V5" />
      <path d="M17 16v-7" />
    </svg>
  );
}

export function FundamentalRefreshIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <path d="M20 12a8 8 0 0 1-13.5 5.8" />
      <path d="M4 12A8 8 0 0 1 17.5 6.2" />
      <path d="M17 3v4h4" />
      <path d="M7 21v-4H3" />
    </svg>
  );
}

export function FundamentalCopyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...baseIconProps(props)}>
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
    </svg>
  );
}
