import type {
  AuthenticatedSession,
  AuthenticatedUser,
  AuthLoginWireResponse,
  AuthPolicy,
  AuthSessionWire,
  AuthUserWire,
} from '../../types';

export function adaptAuthUser(user: AuthUserWire): AuthenticatedUser {
  return {
    userId: user.user_id ?? null,
    clientId: user.client_id ?? null,
    fullName: user.full_name ?? null,
    email: user.email ?? null,
    mobileE164: user.mobile_e164 ?? null,
    pan: user.pan ?? null,
    mpinEnabled: Boolean(user.mpin_enabled),
    createdAt: user.created_at ?? null,
    updatedAt: user.updated_at ?? null,
  };
}

export function adaptAuthSession(session: AuthSessionWire): AuthenticatedSession {
  return {
    token: session.token,
    expiresAt: session.expires_at,
    timeoutMinutes: session.timeout_minutes,
  };
}

export function adaptAuthPolicy(policy: AuthLoginWireResponse['auth_policy']): AuthPolicy {
  return {
    passwordReauthHours: policy.password_reauth_hours,
    lastPasswordAuthAt: policy.last_password_auth_at,
    passwordReauthDueAt: policy.password_reauth_due_at,
    passwordReauthRequired: policy.password_reauth_required,
  };
}
