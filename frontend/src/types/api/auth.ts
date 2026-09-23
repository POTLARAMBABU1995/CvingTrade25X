export type AuthUserWire = {
  user_id: number | null;
  client_id: string | null;
  full_name: string | null;
  email: string | null;
  mobile_e164: string | null;
  pan: string | null;
  mpin_enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type AuthSessionWire = {
  token: string;
  expires_at: string;
  timeout_minutes: number;
};

export type AuthPolicyWire = {
  password_reauth_hours: number;
  last_password_auth_at: string | null;
  password_reauth_due_at: string | null;
  password_reauth_required: boolean;
};

export type AuthRegisterWireResponse = {
  ok: boolean;
  client_id: string;
  user_id: number;
  created_at: string;
};

export type AuthLoginWireResponse = {
  ok: boolean;
  user: AuthUserWire;
  session: AuthSessionWire;
  session_token: string;
  session_expires_at: string;
  auth_policy: AuthPolicyWire;
  quick_mpin_token?: string;
  quick_mpin_expires_at?: string;
};

export type AuthSessionStatusWireResponse = {
  ok: boolean;
  session: {
    session_id: number;
    registration_id: number;
    expires_at: string;
    timeout_minutes: number;
  };
};

export type AuthLogoutWireResponse = {
  ok: boolean;
};

export type AuthResetWireResponse = {
  ok: boolean;
  message: string;
  user_id?: number;
};

export type AuthActivityWireResponse = {
  ok: boolean;
};
