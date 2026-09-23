const INTERNAL_ROUTE_PREFIXES = [
  '/app/',
  '/database/',
  '/fundamental',
  '/fyers/',
  '/sector/',
  '/strategy',
  '/technical/',
] as const;

const INTERNAL_ROUTE_PATHS = new Set([
  '/',
  '/dashboard',
  '/home',
  '/index',
  '/login',
  '/portfolio',
  '/register',
]);

type InternalNavigationClickEvent = {
  altKey: boolean;
  button: number;
  ctrlKey: boolean;
  currentTarget: {
    getAttribute(name: string): string | null;
    hasAttribute(name: string): boolean;
  };
  defaultPrevented: boolean;
  metaKey: boolean;
  preventDefault(): void;
  shiftKey: boolean;
};

function isInternalAppPath(pathname: string): boolean {
  if (INTERNAL_ROUTE_PATHS.has(pathname)) return true;
  return INTERNAL_ROUTE_PREFIXES.some((prefix) => pathname === prefix.replace(/\/$/, '') || pathname.startsWith(prefix));
}

export function getInternalNavigationTarget(href: string, baseHref?: string): string | null {
  if (!href.trim()) return null;

  const currentBase = baseHref ?? (typeof window !== 'undefined' ? window.location.href : 'http://127.0.0.1/');

  try {
    const baseUrl = new URL(currentBase);
    const targetUrl = new URL(href, baseUrl);

    if (targetUrl.origin !== baseUrl.origin) return null;
    if (!['http:', 'https:'].includes(targetUrl.protocol)) return null;
    if (!isInternalAppPath(targetUrl.pathname)) return null;

    return `${targetUrl.pathname}${targetUrl.search}${targetUrl.hash}`;
  } catch {
    return null;
  }
}

export function navigateToInternalRoute(target: string): void {
  if (typeof window === 'undefined') return;

  const currentTarget = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (currentTarget !== target) {
    window.history.pushState(window.history.state ?? {}, '', target);
  }

  try {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  } catch {
    window.dispatchEvent(new Event('popstate'));
  }

  if (!target.includes('#')) {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }
}

export function handleInternalNavigationClick(event: InternalNavigationClickEvent, href: string): boolean {
  const target = event.currentTarget.getAttribute('target');
  const shouldPreserveBrowserNavigation =
    event.defaultPrevented ||
    event.button !== 0 ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    event.currentTarget.hasAttribute('download') ||
    (target !== null && target.trim() !== '' && target.toLowerCase() !== '_self');

  if (shouldPreserveBrowserNavigation) return false;

  const navigationTarget = getInternalNavigationTarget(href);
  if (!navigationTarget) return false;

  event.preventDefault();
  navigateToInternalRoute(navigationTarget);
  return true;
}
