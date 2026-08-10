import { bootstrapAuth, loginWithWechat } from "../../stores/auth";
import type { AuthState } from "../../types/auth";
import { getUserFacingError } from "../../utils/errors";
import { reLaunchForAuthenticatedUser } from "../../utils/navigation";

type LoginPageStatus = "checking" | "ready";

function expiredMessage(reason: string | undefined): string {
  return reason === "expired" ? "登录已失效，请重新登录" : "";
}

Page({
  data: {
    pageStatus: "checking" as LoginPageStatus,
    isLoggingIn: false,
    errorMessage: "",
  },

  onLoad(options: Record<string, string | undefined>) {
    void this.restoreSession(expiredMessage(options.reason));
  },

  async restoreSession(initialMessage = "") {
    this.setData({ pageStatus: "checking", errorMessage: initialMessage });

    try {
      const authState = await bootstrapAuth();
      if (await this.redirectIfAuthenticated(authState)) {
        return;
      }

      this.setData({
        pageStatus: "ready",
        errorMessage: authState.errorMessage ?? initialMessage,
      });
    } catch (error) {
      this.setData({
        pageStatus: "ready",
        errorMessage: getUserFacingError(error, "无法检查登录状态"),
      });
    }
  },

  async redirectIfAuthenticated(authState: AuthState): Promise<boolean> {
    if (authState.status !== "authenticated" || !authState.user) {
      return false;
    }

    await reLaunchForAuthenticatedUser(authState.user);
    return true;
  },

  async onLogin() {
    if (this.data.isLoggingIn) {
      return;
    }

    this.setData({ isLoggingIn: true, errorMessage: "" });
    try {
      const authState = await loginWithWechat();
      await this.redirectIfAuthenticated(authState);
    } catch (error) {
      this.setData({
        errorMessage: getUserFacingError(error, "微信登录失败，请稍后重试"),
      });
    } finally {
      this.setData({ isLoggingIn: false, pageStatus: "ready" });
    }
  },
});
