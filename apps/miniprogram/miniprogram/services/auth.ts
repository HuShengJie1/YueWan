import { API_V1_PREFIX } from "../constants/api";
import type { WechatLoginResponse } from "../types/auth";
import { ApiError, request } from "./request";

let loginCodePromise: Promise<string> | null = null;

function getWechatLoginCode(): Promise<string> {
  if (loginCodePromise) {
    return loginCodePromise;
  }

  const pendingLogin = new Promise<string>((resolve, reject) => {
    wx.login({
      timeout: 10_000,
      success: ({ code }) => {
        if (!code) {
          reject(new ApiError("微信未返回登录凭证", 0));
          return;
        }

        resolve(code);
      },
      fail: () => {
        reject(new ApiError("无法获取微信登录凭证，请稍后重试", 0));
      },
    });
  });

  loginCodePromise = pendingLogin.finally(() => {
    loginCodePromise = null;
  });

  return pendingLogin;
}

export async function loginWithWechat(): Promise<WechatLoginResponse> {
  const code = await getWechatLoginCode();
  return request<WechatLoginResponse>({
    path: `${API_V1_PREFIX}/auth/wechat/login`,
    method: "POST",
    data: { code },
    authenticated: false,
  });
}
