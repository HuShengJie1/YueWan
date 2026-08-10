import { AUTH_SESSION_STORAGE_KEY } from "../constants/storage";
import type { StoredAuthSession } from "../types/auth";
import type { User } from "../types/user";

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isUser(value: unknown): value is User {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const user = value as Partial<User>;
  return (
    typeof user.id === "string" &&
    isNullableString(user.nickname) &&
    isNullableString(user.avatar_url) &&
    typeof user.profile_completed === "boolean"
  );
}

function isStoredAuthSession(value: unknown): value is StoredAuthSession {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const session = value as Partial<StoredAuthSession>;
  return (
    typeof session.accessToken === "string" &&
    session.accessToken.length > 0 &&
    typeof session.expiresAt === "number" &&
    Number.isFinite(session.expiresAt) &&
    isUser(session.user)
  );
}

export function readStoredAuthSession(): StoredAuthSession | null {
  try {
    const storedValue: unknown = wx.getStorageSync(AUTH_SESSION_STORAGE_KEY);
    if (isStoredAuthSession(storedValue)) {
      return storedValue;
    }

    clearStoredAuthSession();
    return null;
  } catch {
    return null;
  }
}

export function writeStoredAuthSession(session: StoredAuthSession): void {
  wx.setStorageSync(AUTH_SESSION_STORAGE_KEY, session);
}

export function clearStoredAuthSession(): void {
  try {
    wx.removeStorageSync(AUTH_SESSION_STORAGE_KEY);
  } catch {
    // A failed cleanup must not keep the in-memory session authenticated.
  }
}
