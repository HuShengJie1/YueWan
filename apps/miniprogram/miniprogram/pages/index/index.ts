import { listGroups } from "../../services/group";
import { ApiError } from "../../services/request";
import { clearPendingGroupInvite, readPendingGroupInvite } from "../../stores/pending-group-invite";
import { bootstrapAuth, getAuthState, logout } from "../../stores/auth";
import type { GroupSummary } from "../../types/group";
import { getUserFacingError } from "../../utils/errors";
import { reLaunchForAuthenticatedUser, reLaunchToLogin } from "../../utils/navigation";

type IndexPageStatus = "loading" | "empty" | "error" | "ready";
type GroupTapEvent = WechatMiniprogram.BaseEvent<Record<string, never>, { groupId: string }>;

const PAGE_LIMIT = 20;

let initialLoadPromise: Promise<void> | null = null;
let loadMorePromise: Promise<void> | null = null;
let refreshOnNextShow = true;
const requestedCursors = new Set<string>();

function mergeUniqueGroups(current: GroupSummary[], incoming: GroupSummary[]): GroupSummary[] {
  const groupsById = new Map(current.map((group) => [group.id, group]));
  incoming.forEach((group) => groupsById.set(group.id, group));
  return [...groupsById.values()];
}

function getPaginationError(error: unknown): string {
  if (error instanceof ApiError && error.code === 42213) {
    return "群组列表已更新，点击重新加载。";
  }

  return getUserFacingError(error, "更多群组加载失败，请重试");
}

Page({
  data: {
    pageStatus: "loading" as IndexPageStatus,
    displayName: "",
    avatarUrl: "",
    groups: [] as GroupSummary[],
    nextCursor: null as string | null,
    hasMore: false,
    isLoadingMore: false,
    loadMoreError: "",
    errorMessage: "",
  },

  onShow() {
    if (!refreshOnNextShow) {
      return;
    }

    refreshOnNextShow = false;
    void this.loadGroups();
  },

  onHide() {
    refreshOnNextShow = true;
  },

  onUnload() {
    refreshOnNextShow = true;
    requestedCursors.clear();
  },

  loadGroups(forceAuth = false): Promise<void> {
    if (initialLoadPromise) {
      return initialLoadPromise;
    }

    if (loadMorePromise) {
      return loadMorePromise.then(() => this.loadGroups(forceAuth));
    }

    const pendingLoad = this.performInitialLoad(forceAuth);
    initialLoadPromise = pendingLoad.finally(() => {
      initialLoadPromise = null;
    });
    return initialLoadPromise;
  },

  async performInitialLoad(forceAuth: boolean) {
    this.setData({
      pageStatus: "loading",
      nextCursor: null,
      hasMore: false,
      isLoadingMore: false,
      loadMoreError: "",
      errorMessage: "",
    });

    try {
      const authState = await bootstrapAuth(forceAuth);
      if (authState.status === "unauthenticated" || !authState.user) {
        await reLaunchToLogin(authState.errorMessage ? "expired" : undefined);
        return;
      }

      if (authState.status === "error") {
        this.setData({
          pageStatus: "error",
          errorMessage: authState.errorMessage ?? "无法恢复登录状态",
        });
        return;
      }

      if (!authState.user.profile_completed) {
        wx.reLaunch({ url: "/pages/profile/profile" });
        return;
      }

      if (readPendingGroupInvite()) {
        await reLaunchForAuthenticatedUser(authState.user);
        return;
      }

      const page = await listGroups({ limit: PAGE_LIMIT });
      requestedCursors.clear();
      this.setData({
        pageStatus: page.items.length > 0 ? "ready" : "empty",
        displayName: authState.user.nickname ?? "微信用户",
        avatarUrl: authState.user.avatar_url ?? "",
        groups: mergeUniqueGroups([], page.items),
        nextCursor: page.next_cursor,
        hasMore: page.has_more && Boolean(page.next_cursor),
      });
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        pageStatus: "error",
        errorMessage: getUserFacingError(error, "群组加载失败，请稍后重试"),
      });
    }
  },

  onRetry() {
    void this.loadGroups(true);
  },

  async onPullDownRefresh() {
    try {
      await this.loadGroups();
    } finally {
      wx.stopPullDownRefresh();
    }
  },

  onReachBottom(): Promise<void> {
    const cursor = this.data.nextCursor;
    if (
      this.data.pageStatus !== "ready" ||
      !this.data.hasMore ||
      !cursor ||
      this.data.isLoadingMore ||
      initialLoadPromise ||
      requestedCursors.has(cursor) ||
      loadMorePromise
    ) {
      return Promise.resolve();
    }

    const pendingLoad = this.performLoadMore(cursor);
    loadMorePromise = pendingLoad.finally(() => {
      loadMorePromise = null;
    });
    return loadMorePromise;
  },

  async performLoadMore(cursor: string) {
    requestedCursors.add(cursor);
    this.setData({ isLoadingMore: true, loadMoreError: "" });
    try {
      const page = await listGroups({ cursor, limit: PAGE_LIMIT });
      const nextCursor = page.next_cursor;
      this.setData({
        groups: mergeUniqueGroups(this.data.groups, page.items),
        nextCursor,
        hasMore: page.has_more && Boolean(nextCursor) && nextCursor !== cursor,
      });
    } catch (error) {
      requestedCursors.delete(cursor);
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const cursorIsInvalid = error instanceof ApiError && error.code === 42213;
      this.setData({
        loadMoreError: getPaginationError(error),
        ...(cursorIsInvalid ? { nextCursor: null, hasMore: false } : {}),
      });
    } finally {
      this.setData({ isLoadingMore: false });
    }
  },

  onLoadMoreRetry() {
    if (!this.data.hasMore) {
      void this.loadGroups();
      return;
    }

    void this.onReachBottom();
  },

  onCreateGroup() {
    wx.navigateTo({ url: "/pages/groups/create/index" });
  },

  onGroupTap(event: GroupTapEvent) {
    const groupId = event.currentTarget.dataset.groupId;
    if (!groupId) {
      return;
    }

    wx.navigateTo({
      url: `/pages/groups/detail/index?group_id=${encodeURIComponent(groupId)}`,
    });
  },

  onEditProfile() {
    wx.navigateTo({ url: "/pages/profile/profile" });
  },

  onLogout() {
    wx.showModal({
      title: "退出登录",
      content: "退出后，下次使用需要重新微信登录。",
      confirmText: "退出",
      confirmColor: "#b54b43",
      success: ({ confirm }) => {
        if (!confirm) {
          return;
        }

        clearPendingGroupInvite();
        logout();
        void reLaunchToLogin();
      },
    });
  },
});
