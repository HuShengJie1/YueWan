import type { User } from "./user";

export type AuthStatus = "initializing" | "unauthenticated" | "authenticated" | "error";

export interface WechatLoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}

export interface StoredAuthSession {
  accessToken: string;
  expiresAt: number;
  user: User;
}

export interface AuthState {
  status: AuthStatus;
  user: User | null;
  errorMessage: string | null;
}
