import { useEffect } from 'react';

export function TrendIndicatorRedirect() {
  useEffect(() => {
    const target = `/app/technical/ema${window.location.search || ''}${window.location.hash || ''}`;
    window.location.replace(target);
  }, []);

  return null;
}
