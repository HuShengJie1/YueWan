import { getGroup } from "../../../services/group";
import { getHangout } from "../../../services/hangout";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { GroupDetail } from "../../../types/group";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { buildHangoutView, type HangoutView } from "../../../utils/hangout";
import { reLaunchToLogin } from "../../../utils/navigation";

type DetailPageStatus = "loading" | "error" | "ready";

let detailRequestGeneration = 0;

function navigateTo(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.navigateTo({
      url,
      success: () => resolve(),
      fail: ({ errMsg }) => reject(new Error(errMsg)),
    });
  });
}

function getLoadError(error: unknown): {
  title: string;
  message: string;
  canRetry: boolean;
} {
  if (error instanceof ApiError && (error.code === 40410 || error.code === 40420)) {
    return {
      title: "无法查看约玩局",
      message: "约玩局不存在或无权查看。",
      canRetry: false,
    };
  }

  return {
    title: "约玩局暂时加载失败",
    message: getUserFacingError(error, "无法读取约玩局，请稍后重试"),
    canRetry: true,
  };
}

Page({
  data: {
    pageStatus: "loading" as DetailPageStatus,
    groupId: "",
    hangoutId: "",
    group: null as GroupDetail | null,
    hangout: null as HangoutView | null,
    canEdit: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    isNavigating: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    detailRequestGeneration += 1;
    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    if (!isValidGroupId(groupId) || !isValidUuid(hangoutId)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "约玩局链接无效",
        errorMessage: "这个链接缺少有效的群组或约玩局信息，请返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ groupId, hangoutId });
    void this.loadDetail();
  },

  onShow() {
    if (this.data.pageStatus === "ready" && this.data.groupId && !this.data.isNavigating) {
      void this.loadDetail();
      return;
    }

    if (this.data.isNavigating) {
      this.setData({ isNavigating: false });
      void this.loadDetail();
    }
  },

  onUnload() {
    detailRequestGeneration += 1;
  },

  async loadDetail(forceAuth = false) {
    const requestGeneration = ++detailRequestGeneration;
    this.setData({
      pageStatus: "loading",
      group: null,
      hangout: null,
      canEdit: false,
      errorMessage: "",
    });
    try {
      const authState = await bootstrapAuth(forceAuth);
      if (requestGeneration !== detailRequestGeneration) {
        return;
      }

      if (authState.status === "unauthenticated" || !authState.user) {
        await reLaunchToLogin(authState.errorMessage ? "expired" : undefined);
        return;
      }

      if (authState.status === "error") {
        throw new Error(authState.errorMessage ?? "无法恢复登录状态");
      }

      if (!authState.user.profile_completed) {
        wx.reLaunch({ url: "/pages/profile/profile" });
        return;
      }

      const [hangout, group] = await Promise.all([
        getHangout(this.data.groupId, this.data.hangoutId),
        getGroup(this.data.groupId),
      ]);
      if (requestGeneration !== detailRequestGeneration) {
        return;
      }

      const canEdit =
        hangout.status === "draft" &&
        (hangout.created_by_user_id === authState.user.id || group.current_user_role === "owner");
      this.setData({
        pageStatus: "ready",
        group,
        hangout: buildHangoutView(hangout),
        canEdit,
      });
      wx.setNavigationBarTitle({ title: hangout.title });
    } catch (error) {
      if (requestGeneration !== detailRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getLoadError(error);
      this.setData({
        pageStatus: "error",
        errorTitle: loadError.title,
        errorMessage: loadError.message,
        canRetry: loadError.canRetry,
      });
    }
  },

  onRetry() {
    void this.loadDetail(true);
  },

  onBack() {
    wx.navigateBack();
  },

  async onEditTap() {
    if (!this.data.canEdit || this.data.isNavigating || !this.data.hangout) {
      return;
    }

    this.setData({ isNavigating: true });
    try {
      const query = [
        `group_id=${encodeURIComponent(this.data.groupId)}`,
        `hangout_id=${encodeURIComponent(this.data.hangoutId)}`,
        "mode=edit",
      ].join("&");
      await navigateTo(`/pages/hangouts/form/index?${query}`);
    } catch {
      this.setData({ isNavigating: false });
      wx.showToast({ title: "编辑页面打开失败，请重试", icon: "none" });
    }
  },
});
