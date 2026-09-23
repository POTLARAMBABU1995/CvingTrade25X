export type AuthenticatedUser = {
  userId: number | null;
  clientId: string | null;
  fullName: string | null;
  email: string | null;
  mobileE164: string | null;
  pan: string | null;
  mpinEnabled: boolean;
  createdAt: string | null;
  updatedAt: string | null;
};

export type AuthenticatedSession = {
  token: string;
  expiresAt: string;
  timeoutMinutes: number;
};

export type AuthPolicy = {
  passwordReauthHours: number;
  lastPasswordAuthAt: string | null;
  passwordReauthDueAt: string | null;
  passwordReauthRequired: boolean;
};
