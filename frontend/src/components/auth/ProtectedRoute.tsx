import { type ReactNode, useEffect, useRef } from 'react';
import { useAuth } from '../../context/AuthContext';
import { redirectToLogin } from '../../services/auth/authSessionStore';

type ProtectedRouteProps = {
  children: ReactNode;
};

type ProtectedRouteState = {
  isAuthenticated: boolean;
  isLoading: boolean;
};

export function shouldBlockProtectedRoute({
  isAuthenticated,
  isLoading,
}: ProtectedRouteState): boolean {
  return isLoading && !isAuthenticated;
}

function SessionLoadingState({ message }: { message: string }) {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-950 px-4 text-center text-slate-100">
      <div className="rounded-3xl border border-white/10 bg-white/10 px-6 py-5 shadow-2xl backdrop-blur-xl">
        <p className="text-sm font-black uppercase tracking-[0.24em] text-emerald">Secure Session</p>
        <p className="mt-2 text-lg font-black">{message}</p>
      </div>
    </div>
  );
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const redirectingRef = useRef(false);

  useEffect(() => {
    if (isLoading || isAuthenticated || redirectingRef.current) return;
    redirectingRef.current = true;
    redirectToLogin();
  }, [isAuthenticated, isLoading]);

  if (shouldBlockProtectedRoute({ isAuthenticated, isLoading })) {
    return <SessionLoadingState message="Checking secure session..." />;
  }

  if (!isAuthenticated) {
    return <SessionLoadingState message="Redirecting to login..." />;
  }

  return <>{children}</>;
}
