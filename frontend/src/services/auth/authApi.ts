import { legacyApiGet, legacyApiPost } from '../../api/client';
import type {
  AuthActivityWireResponse,
  AuthLoginWireResponse,
  AuthLogoutWireResponse,
  AuthRegisterWireResponse,
  AuthResetWireResponse,
  AuthSessionStatusWireResponse,
} from '../../types';

export type RegisterUserPayload = {
  full_name: string;
  email: string;
  mobile_e164?: string;
  mobileNumber?: string;
  dob: string;
  gender?: 'M' | 'F' | 'O';
  pan?: string;
  aadhaar_last4?: string;
  exp_months?: number;
  password: string;
  mpin?: string;
  client_id?: string;
};

export type PasswordLoginPayload = {
  identifier: string;
  password: string;
};

export type MpinLoginPayload = {
  identifier?: string;
  mpin: string;
  quick_token?: string;
};

export type ResetCredentialsPayload = {
  identifier: string;
  dob?: string;
  pan?: string;
  aadhaar_last4?: string;
  quick_token?: string;
  new_password?: string;
  new_mpin?: string;
};

export type RecordLoginActivityPayload = {
  user_id: number;
  method?: string;
};

export function registerUser(payload: RegisterUserPayload): Promise<AuthRegisterWireResponse> {
  return legacyApiPost<AuthRegisterWireResponse>('/api/auth/register', payload, { timeoutMs: 15000 });
}

export function loginWithPassword(payload: PasswordLoginPayload): Promise<AuthLoginWireResponse> {
  return legacyApiPost<AuthLoginWireResponse>('/api/auth/login', payload, { timeoutMs: 15000 });
}

export function loginWithMpin(payload: MpinLoginPayload): Promise<AuthLoginWireResponse> {
  return legacyApiPost<AuthLoginWireResponse>('/api/auth/login', payload, { timeoutMs: 15000 });
}

export function fetchAuthSession(): Promise<AuthSessionStatusWireResponse> {
  return legacyApiGet<AuthSessionStatusWireResponse>('/api/auth/session', undefined, { timeoutMs: 10000 });
}

export function logoutAuthSession(): Promise<AuthLogoutWireResponse> {
  return legacyApiPost<AuthLogoutWireResponse>('/api/auth/logout', {}, { timeoutMs: 10000 });
}

export function recordLoginActivity(payload: RecordLoginActivityPayload): Promise<AuthActivityWireResponse> {
  return legacyApiPost<AuthActivityWireResponse>('/api/auth/activity', payload, { timeoutMs: 10000 });
}

export function resetCredentials(payload: ResetCredentialsPayload): Promise<AuthResetWireResponse> {
  return legacyApiPost<AuthResetWireResponse>('/api/auth/reset', payload, { timeoutMs: 15000 });
}
