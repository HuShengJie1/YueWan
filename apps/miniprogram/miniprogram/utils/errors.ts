import { ApiError } from "../services/request";

export function getUserFacingError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.statusCode === 0) {
      return "网络连接失败，请检查网络后重试";
    }

    if (error.code === 50301) {
      return "微信登录服务暂时不可用，请稍后重试";
    }

    if (error.code === 50302) {
      return "登录服务配置异常，请检查后端微信凭据";
    }

    if (error.statusCode === 401) {
      return "登录凭证已失效，请重新登录";
    }

    if (error.statusCode === 404 || error.statusCode >= 500) {
      return "服务暂时不可用，请稍后重试";
    }

    return error.message || fallback;
  }

  return error instanceof Error && error.message ? error.message : fallback;
}
