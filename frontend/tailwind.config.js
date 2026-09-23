/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--color-bg) / <alpha-value>)',
        panel: 'rgb(var(--color-panel) / <alpha-value>)',
        shell: 'rgb(var(--color-shell) / <alpha-value>)',
        line: 'rgb(var(--color-line) / <alpha-value>)',
        text: 'rgb(var(--color-text) / <alpha-value>)',
        muted: 'rgb(var(--color-muted) / <alpha-value>)',
        dim: 'rgb(var(--color-dim) / <alpha-value>)',
        cyan: 'rgb(var(--color-cyan) / <alpha-value>)',
        amber: 'rgb(var(--color-amber) / <alpha-value>)',
        emerald: 'rgb(var(--color-emerald) / <alpha-value>)',
        crimson: 'rgb(var(--color-crimson) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Space Grotesk"', '"Segoe UI Variable Display"', 'sans-serif'],
        sans: ['"IBM Plex Sans"', '"Segoe UI Variable Text"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      borderRadius: {
        '4xl': '2rem',
        '5xl': '2.5rem',
      },
      boxShadow: {
        panel: '0 24px 60px rgba(0, 0, 0, 0.38)',
        float: '0 18px 48px rgba(6, 8, 12, 0.45)',
        soft: '0 10px 30px rgba(5, 8, 12, 0.24)',
        glow: '0 0 0 1px rgba(125, 211, 252, 0.12), 0 18px 40px rgba(14, 165, 233, 0.18)',
        inset: 'inset 0 1px 0 rgba(255, 255, 255, 0.06)',
      },
      backgroundImage: {
        'ambient-mesh': 'radial-gradient(circle at top left, rgba(103, 232, 249, 0.14), transparent 26%), radial-gradient(circle at 82% 12%, rgba(245, 158, 11, 0.12), transparent 22%), linear-gradient(180deg, rgba(15, 23, 42, 0.14), transparent 38%)',
        'panel-glow': 'linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02))',
        'grid-fade': 'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(18px) scale(0.985)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        drift: {
          '0%, 100%': { transform: 'translate3d(0, 0, 0)' },
          '50%': { transform: 'translate3d(0, -10px, 0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(34, 211, 238, 0.14)' },
          '50%': { boxShadow: '0 0 0 10px rgba(34, 211, 238, 0.03)' },
        },
      },
      animation: {
        rise: 'rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) both',
        drift: 'drift 12s ease-in-out infinite',
        'pulse-glow': 'pulseGlow 3.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
