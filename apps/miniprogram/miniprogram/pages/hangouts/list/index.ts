import { listHangouts } from "../../../services/hangout";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { Hangout } from "../../../types/hangout";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { buildHangoutView, type HangoutView } from "../../../utils/hangout";
import { reLaunchToLogin } from "../../../utils/navigation";

type ListPageStatus = "loading" | "empty" | "error" | "ready";

const PAGE_LIMIT = 20;
const requestedCursors = new Set<string>();
let listRequestGeneration = 0;
let firstPageRequestActive = false;

function mergeUniqueHangouts(current: HangoutView[], incoming: Hangout[]): HangoutView[] {
  const hangoutsById = new Map(current.map((hangout) => [hangout.id, hangout]));
  incoming.forEach((hangout) => hangoutsById.set(hangout.id, buildHangoutView(hangout)));
  return [...hangoutsById.values()];
}

function navigateTo(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.navigateTo({
      url,
      success: () => resolve(),
      fail: ({ errMsg }) => reject(new Error(errMsg)),
    });
  });
}

function getInitialLoadError(error: unknown): {
  title: string;
  message: string;
  canRetry: boolean;
} {
  if (error instanceof ApiError && error.code === 40410) {
    return {
      title: "无法查看约玩局",
      message: "群组不存在，或你暂时没有查看权限。",
      canRetry: false,
    };
  }

  return {
    title: "约玩局暂时加载失败",
    message: getUserFacingError(error, "无法读取约玩局，请稍后重试"),
    canRetry: true,
  };
}

function getPaginationError(error: unknown): string {
  if (error instanceof ApiError && error.code === 42213) {
    return "列表位置已失效，请重新加载全部约玩局。";
  }

  return getUserFacingError(error, "更多约玩局加载失败，请重试");
}

Page({
  data: {
    pageStatus: "loading" as ListPageStatus,
    groupId: "",
    hangouts: [] as HangoutView[],
    nextCursor: null as string | null,
    hasMore: false,
    isLoadingMore: false,
    isRefreshing: false,
    loadMoreError: "",
    refreshErrorMessage: "",
    cursorInvalid: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    isNavigating: false,
    shouldRefreshOnShow: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    const groupId = options.group_id?.trim() ?? "";
    requestedCursors.clear();
    listRequestGeneration += 1;
    firstPageRequestActive = false;

    if (!isValidGroupId(groupId)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "群组链接无效",
        errorMessage: "这个链接缺少有效的群组信息，请返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ groupId });
    void this.loadFirstPage();
  },

  onShow() {
    if (!this.data.shouldRefreshOnShow) {
      return;
    }

    this.setData({ shouldRefreshOnShow: false, isNavigating: false });
    if (this.data.groupId) {
      void this.loadFirstPage(false, true);
    }
  },

  onUnload() {
    listRequestGeneration += 1;
    firstPageRequestActive = false;
    requestedCursors.clear();
  },

  async loadFirstPage(forceAuth = false, preserveContent = false) {
    if (!this.data.groupId || firstPageRequestActive) {
      return;
    }

    firstPageRequestActive = true;
    const requestGeneration = ++listRequestGeneration;
    requestedCursors.clear();
    this.setData({
      ...(preserveContent ? { isRefreshing: true } : { pageStatus: "loading" }),
      nextCursor: null,
      hasMore: false,
      isLoadingMore: false,
      loadMoreError: "",
      refreshErrorMessage: "",
      cursorInvalid: false,
      errorMessage: "",
    });

    try {
      const authState = await bootstrapAuth(forceAuth);
      if (requestGeneration !== listRequestGeneration) {
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

      const page = await listHangouts(this.data.groupId, { limit: PAGE_LIMIT });
      if (requestGeneration !== listRequestGeneration) {
        return;
      }

      const hangouts = mergeUniqueHangouts([], page.items);
      const nextCursor = page.next_cursor;
      this.setData({
        pageStatus: hangouts.length > 0 ? "ready" : "empty",
        hangouts,
        nextCursor,
        hasMore: page.has_more && Boolean(nextCursor),
        isRefreshing: false,
      });
    } catch (error) {
      if (requestGeneration !== listRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getInitialLoadError(error);
      if (preserveContent && this.data.hangouts.length > 0 && loadError.canRetry) {
        this.setData({
          pageStatus: "ready",
          isRefreshing: false,
          refreshErrorMessage: loadError.message,
        });
      } else {
        this.setData({
          pageStatus: "error",
          isRefreshing: false,
          errorTitle: loadError.title,
          errorMessage: loadError.message,
          canRetry: loadError.canRetry,
        });
      }
    } finally {
      if (requestGeneration === listRequestGeneration) {
        firstPageRequestActive = false;
      }
    }
  },

  onRetry() {
    void this.loadFirstPage(true);
  },

  onRefreshRetry() {
    void this.loadFirstPage(false, true);
  },

  async onPullDownRefresh() {
    try {
      await this.loadFirstPage(false, this.data.hangouts.length > 0);
    } finally {
      wx.stopPullDownRefresh();
    }
  },

  async onReachBottom() {
    const cursor = this.data.nextCursor;
    if (
      this.data.pageStatus !== "ready" ||
      !this.data.hasMore ||
      !cursor ||
      this.data.isLoadingMore ||
      firstPageRequestActive ||
      requestedCursors.has(cursor)
    ) {
      return;
    }

    const requestGeneration = listRequestGeneration;
    requestedCursors.add(cursor);
    this.setData({ isLoadingMore: true, loadMoreError: "", cursorInvalid: false });
    try {
      const page = await listHangouts(this.data.groupId, { cursor, limit: PAGE_LIMIT });
      if (requestGeneration !== listRequestGeneration) {
        return;
      }

      const nextCursor = page.next_cursor;
      this.setData({
        hangouts: mergeUniqueHangouts(this.data.hangouts, page.items),
        nextCursor,
        hasMore: page.has_more && Boolean(nextCursor) && nextCursor !== cursor,
      });
    } catch (error) {
      if (requestGeneration !== listRequestGeneration) {
        return;
      }

      requestedCursors.delete(cursor);
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const cursorInvalid = error instanceof ApiError && error.code === 42213;
      this.setData({
        loadMoreError: getPaginationError(error),
        cursorInvalid,
        ...(cursorInvalid ? { nextCursor: null, hasMore: false } : {}),
      });
    } finally {
      if (requestGeneration === listRequestGeneration) {
        this.setData({ isLoadingMore: false });
      }
    }
  },

  onLoadMoreRetry() {
    if (this.data.cursorInvalid) {
      void this.loadFirstPage();
      return;
    }

    void this.onReachBottom();
  },

  async onCreateTap() {
    if (!this.data.groupId || this.data.isNavigating) {
      return;
    }

    this.setData({ isNavigating: true, shouldRefreshOnShow: true });
    try {
      await navigateTo(
        `/pages/hangouts/form/index?group_id=${encodeURIComponent(this.data.groupId)}`,
      );
    } catch {
      this.setData({ isNavigating: false, shouldRefreshOnShow: false });
      wx.showToast({ title: "页面打开失败，请重试", icon: "none" });
    }
  },

  async onHangoutTap(event: WechatMiniprogram.TouchEvent) {
    const hangoutId = String(event.currentTarget.dataset.hangoutId ?? "");
    if (!isValidUuid(hangoutId) || this.data.isNavigating) {
      return;
    }

    this.setData({ isNavigating: true, shouldRefreshOnShow: true });
    try {
      const query = [
        `group_id=${encodeURIComponent(this.data.groupId)}`,
        `hangout_id=${encodeURIComponent(hangoutId)}`,
      ].join("&");
      await navigateTo(`/pages/hangouts/detail/index?${query}`);
    } catch {
      this.setData({ isNavigating: false, shouldRefreshOnShow: false });
      wx.showToast({ title: "详情打开失败，请重试", icon: "none" });
    }
  },

  onBack() {
    wx.navigateBack();
  },
});
