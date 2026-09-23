import type { ReactNode } from 'react';

type FundamentalAuthShellProps = {
  children: ReactNode;
};

export function FundamentalAuthShell({ children }: FundamentalAuthShellProps) {
  return (
    <div data-auth-scope="fundamental-analysis" data-auth-mode="placeholder">
      {children}
    </div>
  );
}
