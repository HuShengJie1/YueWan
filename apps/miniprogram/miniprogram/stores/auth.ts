import {
  clearStoredAuthSession,
  readStoredAuthSession,
  writeStoredAuthSession,
} from "../services/auth-storage";
import { loginWithWechat as requestWechatLogin } from "../services/auth";
import { configureRequestAuth } from "../services/request";
import { getCurrentUser } from "../services/user";
import type { AuthState, StoredAuthSession, WechatLoginResponse } from "../types/auth";
import type { User } from "../types/user";
import { getUserFacingError } from "../utils/errors";

const SESSION_EXPIRY_SKEW_MS = 30_000;

let session: StoredAuthSession | null = null;
let initialized = false;
let bootstrapPromise: Promise<AuthState> | null = null;
let loginPromise: Promise<AuthState> | null = null;
let state: AuthState = {
  status: "initializing",
  user: null,
  errorMessage: null,
};

function snapshotState(): AuthState {
  return { ...state };
}

function setState(nextState: AuthState): AuthState {
  state = nextState;
  return snapshotState();
}

function clearSession(errorMessage: string | null = null): AuthState {
  session = null;
  clearStoredAuthSession();
  return setState({
    status: "unauthenticated",
    user: null,
    errorMessage,
  });
}

function isSessionExpired(storedSession: StoredAuthSession): boolean {
  return storedSession.expiresAt <= Date.now() + SESSION_EXPIRY_SKEW_MS;
}

function buildSession(response: WechatLoginResponse): StoredAuthSession {
  if (
    typeof response.access_token !== "string" ||
    !response.access_token ||
    typeof response.token_type !== "string" ||
    response.token_type.toLowerCase() !== "bearer" ||
    !Number.isFinite(response.expires_in) ||
    response.expires_in <= 0 ||
    !response.user?.id
  ) {
    throw new Error("登录服务返回了无效会话");
  }

  return {
    accessToken: response.access_token,
    expiresAt: Date.now() + response.expires_in * 1000,
    user: response.user,
  };
}

function authenticate(nextSession: StoredAuthSession): AuthState {
  try {
    writeStoredAuthSession(nextSession);
  } catch {
    throw new Error("无法保存登录状态，请清理小程序缓存后重试");
  }

  session = nextSession;
  return setState({
    status: "authenticated",
    user: nextSession.user,
    errorMessage: null,
  });
}

async function performBootstrap(): Promise<AuthState> {
  setState({ status: "initializing", user: null, errorMessage: null });

  const storedSession = readStoredAuthSession();
  if (!storedSession || isSessionExpired(storedSession)) {
    initialized = true;
    return clearSession();
  }

  session = storedSession;
  try {
    const user = await getCurrentUser();
    initialized = true;
    return authenticate({ ...storedSession, user });
  } catch (error) {
    initialized = true;

    if (!session) {
      return snapshotState();
    }

    return setState({
      status: "error",
      user: storedSession.user,
      errorMessage: getUserFacingError(error, "无法恢复登录状态"),
    });
  }
}

export function getAuthState(): AuthState {
  return snapshotState();
}

export function bootstrapAuth(force = false): Promise<AuthState> {
  if (!force && initialized) {
    return Promise.resolve(snapshotState());
  }

  if (bootstrapPromise) {
    return bootstrapPromise;
  }

  bootstrapPromise = performBootstrap().finally(() => {
    bootstrapPromise = null;
  });
  return bootstrapPromise;
}

export function loginWithWechat(): Promise<AuthState> {
  if (loginPromise) {
    return loginPromise;
  }

  setState({ status: "initializing", user: null, errorMessage: null });
  loginPromise = requestWechatLogin()
    .then((response) => {
      initialized = true;
      return authenticate(buildSession(response));
    })
    .catch((error: unknown) => {
      initialized = true;
      const errorMessage = getUserFacingError(error, "微信登录失败，请稍后重试");
      clearSession(errorMessage);
      throw error;
    })
    .finally(() => {
      loginPromise = null;
    });

  return loginPromise;
}

export function updateAuthenticatedUser(user: User): AuthState {
  if (!session) {
    return clearSession("登录已失效，请重新登录");
  }

  return authenticate({ ...session, user });
}

export function logout(): AuthState {
  initialized = true;
  return clearSession();
}

configureRequestAuth({
  getAccessToken: () => session?.accessToken ?? null,
  onUnauthorized: () => {
    initialized = true;
    clearSession("登录已失效，请重新登录");
  },
});
