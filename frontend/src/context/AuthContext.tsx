import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  fetchAuthSession,
  loginWithMpin,
  loginWithPassword,
  logoutAuthSession,
  type MpinLoginPayload,
  type PasswordLoginPayload,
} from '../services/auth/authApi';
import { adaptAuthSession, adaptAuthUser } from '../services/auth/authAdapters';
import {
  AUTH_CHANGE_EVENT,
  AUTH_INVALID_EVENT,
  clearAuthSession,
  persistAuthSession,
  persistAuthSessionStatus,
  readStoredAuthState,
} from '../services/auth/authSessionStore';
import type {
  AuthenticatedSession,
  AuthenticatedUser,
  AuthLoginWireResponse,
  AuthSessionStatusWireResponse,
} from '../types';

type RefreshOptions = {
  silent?: boolean;
};

type AuthContextValue = {
  getAuthHeader: () => Record<string, string>;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: PasswordLoginPayload | MpinLoginPayload) => Promise<AuthLoginWireResponse>;
  logout: () => Promise<void>;
  refreshAuth: (options?: RefreshOptions) => Promise<boolean>;
  session: AuthenticatedSession | null;
  token: string;
  user: AuthenticatedUser | null;
};

const defaultAuthContext: AuthContextValue = {
  getAuthHeader: () => ({}),
  isAuthenticated: false,
  isLoading: typeof window !== 'undefined',
  login: async () => {
    throw new Error('AuthProvider is not mounted.');
  },
  logout: async () => undefined,
  refreshAuth: async () => false,
  session: null,
  token: '',
  user: null,
};

const AuthContext = createContext<AuthContextValue>(defaultAuthContext);

function statusCode(error: unknown): number {
  if (!error || typeof error !== 'object') return 0;
  const value = (error as { status?: unknown; httpStatus?: unknown }).status ?? (error as { httpStatus?: unknown }).httpStatus;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : 0;
}

function isConfirmedInvalidSession(error: unknown): boolean {
  return statusCode(error) === 401;
}

function sessionFromStatus(response: AuthSessionStatusWireResponse): AuthenticatedSession {
  const stored = readStoredAuthState();
  return {
    token: stored.token,
    expiresAt: response.session.expires_at,
    timeoutMinutes: response.session.timeout_minutes,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(() => typeof window !== 'undefined');
  const [session, setSession] = useState<AuthenticatedSession | null>(null);
  const [token, setToken] = useState('');
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  const applyStoredState = useCallback(() => {
    const stored = readStoredAuthState();
    setToken(stored.token);
    if (stored.isValid) {
      setSession({
        token: stored.token,
        expiresAt: stored.expiresAt,
        timeoutMinutes: 0,
      });
      setIsAuthenticated(true);
    } else {
      setSession(null);
      setIsAuthenticated(false);
    }
    return stored;
  }, []);

  const refreshAuth = useCallback(async (options: RefreshOptions = {}) => {
    if (typeof window === 'undefined') return false;
    if (!options.silent) setIsLoading(true);
    try {
      const response = await fetchAuthSession();
      persistAuthSessionStatus(response);
      const nextSession = sessionFromStatus(response);
      setSession(nextSession);
      setToken(nextSession.token);
      setIsAuthenticated(true);
      return true;
    } catch (error) {
      if (isConfirmedInvalidSession(error)) {
        clearAuthSession({ keepQuickMpin: true });
        setSession(null);
        setToken('');
        setUser(null);
        setIsAuthenticated(false);
        return false;
      }

      const stored = applyStoredState();
      return stored.isValid;
    } finally {
      setIsLoading(false);
    }
  }, [applyStoredState]);

  const login = useCallback(async (payload: PasswordLoginPayload | MpinLoginPayload) => {
    const response = 'password' in payload
      ? await loginWithPassword(payload)
      : await loginWithMpin(payload);
    persistAuthSession(response);
    setUser(adaptAuthUser(response.user));
    const nextSession = adaptAuthSession(response.session);
    setSession(nextSession);
    setToken(nextSession.token);
    setIsAuthenticated(true);
    setIsLoading(false);
    return response;
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutAuthSession();
    } catch {
      // Local logout must still clear UI auth state if the server session is already gone.
    } finally {
      clearAuthSession();
      setSession(null);
      setToken('');
      setUser(null);
      setIsAuthenticated(false);
      setIsLoading(false);
    }
  }, []);

  const getAuthHeader = useCallback((): Record<string, string> => {
    const activeToken = token || readStoredAuthState().token;
    if (!activeToken) return {};
    return {
      Authorization: `Bearer ${activeToken}`,
      'X-Session-Token': activeToken,
    };
  }, [token]);

  useEffect(() => {
    applyStoredState();
    void refreshAuth({ silent: false });

    const handleAuthChange = () => {
      applyStoredState();
    };
    const handleAuthInvalid = () => {
      clearAuthSession({ keepQuickMpin: true });
      setSession(null);
      setToken('');
      setUser(null);
      setIsAuthenticated(false);
      setIsLoading(false);
    };

    window.addEventListener('storage', handleAuthChange);
    window.addEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
    window.addEventListener(AUTH_INVALID_EVENT, handleAuthInvalid);
    return () => {
      window.removeEventListener('storage', handleAuthChange);
      window.removeEventListener(AUTH_CHANGE_EVENT, handleAuthChange);
      window.removeEventListener(AUTH_INVALID_EVENT, handleAuthInvalid);
    };
  }, [applyStoredState, refreshAuth]);

  const value = useMemo<AuthContextValue>(() => ({
    getAuthHeader,
    isAuthenticated,
    isLoading,
    login,
    logout,
    refreshAuth,
    session,
    token,
    user,
  }), [getAuthHeader, isAuthenticated, isLoading, login, logout, refreshAuth, session, token, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  return useContext(AuthContext);
}
