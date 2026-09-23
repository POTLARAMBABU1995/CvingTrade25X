import type { SVGProps } from 'react';

function iconProps(props: SVGProps<SVGSVGElement>) {
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

export function PanelLeftIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16" />
    </svg>
  );
}

export function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export function BellIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M6 8a6 6 0 1 1 12 0c0 6 2.5 7 2.5 7H3.5S6 14 6 8" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </svg>
  );
}

export function SparkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m12 3 2.2 5.8L20 11l-5.8 2.2L12 19l-2.2-5.8L4 11l5.8-2.2z" />
    </svg>
  );
}

export function RadarIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 12 17 7" />
    </svg>
  );
}

export function ChartIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M4 19h16" />
      <path d="m6 15 4-4 3 3 5-6" />
    </svg>
  );
}

export function StrategyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M4 6h16" />
      <path d="M6 12h12" />
      <path d="M8 18h8" />
    </svg>
  );
}

export function LayersIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m12 4 8 4-8 4-8-4 8-4Z" />
      <path d="m4 12 8 4 8-4" />
      <path d="m4 16 8 4 8-4" />
    </svg>
  );
}

export function LabIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M10 3v5l-5 8a3 3 0 0 0 2.6 4.5h8.8A3 3 0 0 0 19 16l-5-8V3" />
      <path d="M8 8h8" />
    </svg>
  );
}

export function BookmarkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1Z" />
    </svg>
  );
}

export function ChevronRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function ArrowUpRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M7 17 17 7" />
      <path d="M9 7h8v8" />
    </svg>
  );
}

export function ArrowDownRightIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m7 7 10 10" />
      <path d="M17 9v8H9" />
    </svg>
  );
}

export function EyeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.8" />
    </svg>
  );
}

export function EyeOffIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="m3 3 18 18" />
      <path d="M10.6 10.6a2.8 2.8 0 0 0 3.8 3.8" />
      <path d="M9.4 5.4A10.2 10.2 0 0 1 12 5c6 0 9.5 7 9.5 7a16.4 16.4 0 0 1-2.7 3.4" />
      <path d="M6.1 6.9C3.8 8.5 2.5 12 2.5 12s3.5 7 9.5 7a9.5 9.5 0 0 0 4.6-1.2" />
    </svg>
  );
}

export function BullIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M5 8c.6-2.2 2-3.8 4-4" />
      <path d="M19 8c-.6-2.2-2-3.8-4-4" />
      <path d="M7 10c0-2.2 2.2-4 5-4s5 1.8 5 4v3.2c0 3-2.2 5.3-5 5.3s-5-2.3-5-5.3V10Z" />
      <path d="M9.2 12h.1" />
      <path d="M14.7 12h.1" />
      <path d="M10 16h4" />
    </svg>
  );
}

export function BearIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M7 7.5 5 5.8" />
      <path d="m17 7.5 2-1.7" />
      <path d="M6.5 11c0-2.8 2.5-5 5.5-5s5.5 2.2 5.5 5v2.4c0 3.1-2.4 5.6-5.5 5.6s-5.5-2.5-5.5-5.6V11Z" />
      <path d="M9.3 11.5h.1" />
      <path d="M14.6 11.5h.1" />
      <path d="M10 16c.7-.5 1.3-.7 2-.7s1.3.2 2 .7" />
    </svg>
  );
}

export function DotGridIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="7" cy="7" r="1.2" />
      <circle cx="12" cy="7" r="1.2" />
      <circle cx="17" cy="7" r="1.2" />
      <circle cx="7" cy="12" r="1.2" />
      <circle cx="12" cy="12" r="1.2" />
      <circle cx="17" cy="12" r="1.2" />
      <circle cx="7" cy="17" r="1.2" />
      <circle cx="12" cy="17" r="1.2" />
      <circle cx="17" cy="17" r="1.2" />
    </svg>
  );
}

export function CopyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <rect x="9" y="9" width="11" height="11" rx="2.2" />
      <path d="M6 15H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function TrashIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M4 7h16" />
      <path d="M9 7V5.6A1.6 1.6 0 0 1 10.6 4h2.8A1.6 1.6 0 0 1 15 5.6V7" />
      <path d="M6.2 7 7 18.4A2 2 0 0 0 9 20h6a2 2 0 0 0 2-1.6L17.8 7" />
      <path d="M10 11.2v5.2" />
      <path d="M14 11.2v5.2" />
    </svg>
  );
}

export function SunIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.8v2.2" />
      <path d="M12 19v2.2" />
      <path d="m4.9 4.9 1.6 1.6" />
      <path d="m17.5 17.5 1.6 1.6" />
      <path d="M2.8 12H5" />
      <path d="M19 12h2.2" />
      <path d="m4.9 19.1 1.6-1.6" />
      <path d="m17.5 6.5 1.6-1.6" />
    </svg>
  );
}

export function MoonIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M21 12.6A8.5 8.5 0 1 1 11.4 3 6.8 6.8 0 0 0 21 12.6Z" />
    </svg>
  );
}

export function PowerIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 2.8v9" />
      <path d="M18.4 6.8a8 8 0 1 1-12.8 0" />
    </svg>
  );
}
