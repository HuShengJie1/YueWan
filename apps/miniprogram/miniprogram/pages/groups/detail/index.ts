import {
  createGroupInviteToken,
  deleteGroup,
  getGroup,
  listGroupMembers,
} from "../../../services/group";
import { listHangouts } from "../../../services/hangout";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { GroupDetail, GroupMember } from "../../../types/group";
import type { Hangout } from "../../../types/hangout";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { buildHangoutView, type HangoutView } from "../../../utils/hangout";
import { reLaunchToIndex, reLaunchToLogin } from "../../../utils/navigation";

type DetailPageStatus = "loading" | "error" | "ready";
type InviteStatus = "idle" | "loading" | "error" | "ready";
type HangoutSectionStatus = "loading" | "empty" | "error" | "ready";

const PAGE_LIMIT = 30;
const RECENT_HANGOUT_LIMIT = 3;
const INVITE_EXPIRY_SKEW_MS = 30_000;

const requestedMemberCursors = new Set<string>();
let inviteRequestGeneration = 0;
let hangoutRequestGeneration = 0;
let hangoutRequestActive = false;

function mergeUniqueMembers(current: GroupMember[], incoming: GroupMember[]): GroupMember[] {
  const membersByUserId = new Map(current.map((member) => [member.user_id, member]));
  incoming.forEach((member) => membersByUserId.set(member.user_id, member));
  return [...membersByUserId.values()];
}

function getLoadError(error: unknown): {
  title: string;
  message: string;
  canRetry: boolean;
} {
  if (error instanceof ApiError && error.statusCode === 404) {
    return {
      title: "找不到这个群组",
      message: "群组不存在，或你暂时没有查看权限。",
      canRetry: false,
    };
  }

  return {
    title: "群组暂时加载失败",
    message: getUserFacingError(error, "无法读取群组信息，请稍后重试"),
    canRetry: true,
  };
}

function getMemberPaginationError(error: unknown): string {
  if (error instanceof ApiError && error.code === 42213) {
    return "成员列表已更新，点击重新加载。";
  }

  return getUserFacingError(error, "更多成员加载失败，请重试");
}

function buildRecentHangouts(hangouts: Hangout[]): HangoutView[] {
  return hangouts.map(buildHangoutView);
}

function getRecentHangoutError(error: unknown): string {
  if (error instanceof ApiError && error.code === 40410) {
    return "群组状态已变化，暂时无法读取约玩局。";
  }

  return getUserFacingError(error, "约玩局加载失败，请稍后重试");
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

Page({
  data: {
    pageStatus: "loading" as DetailPageStatus,
    groupId: "",
    group: null as GroupDetail | null,
    members: [] as GroupMember[],
    displayName: "微信用户",
    nextMemberCursor: null as string | null,
    hasMoreMembers: false,
    isLoadingMoreMembers: false,
    memberLoadError: "",
    hangoutStatus: "loading" as HangoutSectionStatus,
    recentHangouts: [] as HangoutView[],
    hangoutHasMore: false,
    hangoutErrorMessage: "",
    isHangoutNavigating: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    inviteStatus: "idle" as InviteStatus,
    inviteToken: "",
    inviteExpiresAt: 0,
    inviteErrorMessage: "",
    showDeleteConfirmation: false,
    deleteConfirmationName: "",
    isDeleteConfirmationMatched: false,
    deleteErrorMessage: "",
    isDeleting: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    wx.hideShareMenu();
    const groupId = options.group_id?.trim() ?? "";
    if (!isValidGroupId(groupId)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "群组链接无效",
        errorMessage: "这个群组链接不完整，请返回首页后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ groupId });
    void this.loadGroup();
  },

  onShow() {
    if (
      this.data.pageStatus === "ready" &&
      this.data.inviteExpiresAt > 0 &&
      this.data.inviteExpiresAt <= Date.now() + INVITE_EXPIRY_SKEW_MS
    ) {
      wx.hideShareMenu();
      void this.prepareInvite();
    }

    if (this.data.pageStatus === "ready" && this.data.groupId) {
      this.setData({ isHangoutNavigating: false });
      void this.loadRecentHangouts();
    }
  },

  onUnload() {
    inviteRequestGeneration += 1;
    hangoutRequestGeneration += 1;
    hangoutRequestActive = false;
    requestedMemberCursors.clear();
  },

  async loadGroup(forceAuth = false) {
    const groupId = this.data.groupId;
    if (!groupId) {
      return;
    }

    wx.hideShareMenu();
    inviteRequestGeneration += 1;
    hangoutRequestGeneration += 1;
    hangoutRequestActive = false;
    this.setData({
      pageStatus: "loading",
      members: [],
      nextMemberCursor: null,
      hasMoreMembers: false,
      memberLoadError: "",
      hangoutStatus: "loading",
      recentHangouts: [],
      hangoutHasMore: false,
      hangoutErrorMessage: "",
      isHangoutNavigating: false,
      errorMessage: "",
      inviteStatus: "idle",
      inviteToken: "",
      inviteExpiresAt: 0,
      inviteErrorMessage: "",
      showDeleteConfirmation: false,
      deleteConfirmationName: "",
      isDeleteConfirmationMatched: false,
      deleteErrorMessage: "",
      isDeleting: false,
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
          errorTitle: "无法恢复登录状态",
          errorMessage: authState.errorMessage ?? "请检查网络后重试",
          canRetry: true,
        });
        return;
      }

      if (!authState.user.profile_completed) {
        wx.reLaunch({ url: "/pages/profile/profile" });
        return;
      }

      const [group, memberPage] = await Promise.all([
        getGroup(groupId),
        listGroupMembers(groupId, { limit: PAGE_LIMIT }),
      ]);
      requestedMemberCursors.clear();
      this.setData({
        pageStatus: "ready",
        group,
        members: mergeUniqueMembers([], memberPage.items),
        displayName: authState.user.nickname ?? "微信用户",
        nextMemberCursor: memberPage.next_cursor,
        hasMoreMembers: memberPage.has_more && Boolean(memberPage.next_cursor),
      });
      wx.setNavigationBarTitle({ title: group.name });
      void this.prepareInvite();
      void this.loadRecentHangouts();
    } catch (error) {
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
    void this.loadGroup(true);
  },

  async prepareInvite() {
    if (!this.data.groupId || this.data.inviteStatus === "loading") {
      return;
    }

    const requestGeneration = ++inviteRequestGeneration;
    wx.hideShareMenu();
    this.setData({
      inviteStatus: "loading",
      inviteToken: "",
      inviteExpiresAt: 0,
      inviteErrorMessage: "",
    });
    try {
      const invite = await createGroupInviteToken(this.data.groupId);
      if (requestGeneration !== inviteRequestGeneration) {
        return;
      }

      const expiresAt = Date.parse(invite.expires_at);
      if (
        !invite.invite_token ||
        !Number.isFinite(expiresAt) ||
        expiresAt <= Date.now() + INVITE_EXPIRY_SKEW_MS
      ) {
        throw new Error("邀请凭证无效，请重新准备");
      }

      this.setData({
        inviteStatus: "ready",
        inviteToken: invite.invite_token,
        inviteExpiresAt: expiresAt,
      });
      wx.showShareMenu({ menus: ["shareAppMessage"] });
    } catch (error) {
      if (requestGeneration !== inviteRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        inviteStatus: "error",
        inviteErrorMessage: getUserFacingError(error, "邀请暂时无法准备，请稍后重试"),
      });
    }
  },

  onInviteRetry() {
    void this.prepareInvite();
  },

  async loadRecentHangouts() {
    if (!this.data.groupId || hangoutRequestActive) {
      return;
    }

    hangoutRequestActive = true;
    const requestGeneration = ++hangoutRequestGeneration;
    this.setData({ hangoutStatus: "loading", hangoutErrorMessage: "" });
    try {
      const page = await listHangouts(this.data.groupId, { limit: RECENT_HANGOUT_LIMIT });
      if (requestGeneration !== hangoutRequestGeneration) {
        return;
      }

      const recentHangouts = buildRecentHangouts(page.items);
      this.setData({
        hangoutStatus: recentHangouts.length > 0 ? "ready" : "empty",
        recentHangouts,
        hangoutHasMore: page.has_more,
      });
    } catch (error) {
      if (requestGeneration !== hangoutRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        hangoutStatus: "error",
        hangoutErrorMessage: getRecentHangoutError(error),
      });
    } finally {
      if (requestGeneration === hangoutRequestGeneration) {
        hangoutRequestActive = false;
      }
    }
  },

  onHangoutRetry() {
    if (this.data.hangoutStatus !== "loading") {
      void this.loadRecentHangouts();
    }
  },

  async onCreateHangout() {
    if (!this.data.groupId || this.data.isHangoutNavigating) {
      return;
    }

    this.setData({ isHangoutNavigating: true });
    try {
      await navigateTo(
        `/pages/hangouts/form/index?group_id=${encodeURIComponent(this.data.groupId)}`,
      );
    } catch {
      this.setData({ isHangoutNavigating: false });
      wx.showToast({ title: "页面打开失败，请重试", icon: "none" });
    }
  },

  async onHangoutTap(event: WechatMiniprogram.TouchEvent) {
    const hangoutId = String(event.currentTarget.dataset.hangoutId ?? "");
    if (!isValidUuid(hangoutId) || this.data.isHangoutNavigating) {
      return;
    }

    this.setData({ isHangoutNavigating: true });
    try {
      const query = [
        `group_id=${encodeURIComponent(this.data.groupId)}`,
        `hangout_id=${encodeURIComponent(hangoutId)}`,
      ].join("&");
      await navigateTo(`/pages/hangouts/detail/index?${query}`);
    } catch {
      this.setData({ isHangoutNavigating: false });
      wx.showToast({ title: "详情打开失败，请重试", icon: "none" });
    }
  },

  async onViewAllHangouts() {
    if (!this.data.groupId || this.data.isHangoutNavigating) {
      return;
    }

    this.setData({ isHangoutNavigating: true });
    try {
      await navigateTo(
        `/pages/hangouts/list/index?group_id=${encodeURIComponent(this.data.groupId)}`,
      );
    } catch {
      this.setData({ isHangoutNavigating: false });
      wx.showToast({ title: "列表打开失败，请重试", icon: "none" });
    }
  },

  async onReachBottom() {
    const cursor = this.data.nextMemberCursor;
    if (
      this.data.pageStatus !== "ready" ||
      !this.data.hasMoreMembers ||
      !cursor ||
      this.data.isLoadingMoreMembers ||
      requestedMemberCursors.has(cursor)
    ) {
      return;
    }

    requestedMemberCursors.add(cursor);
    this.setData({ isLoadingMoreMembers: true, memberLoadError: "" });
    try {
      const memberPage = await listGroupMembers(this.data.groupId, {
        cursor,
        limit: PAGE_LIMIT,
      });
      const nextCursor = memberPage.next_cursor;
      this.setData({
        members: mergeUniqueMembers(this.data.members, memberPage.items),
        nextMemberCursor: nextCursor,
        hasMoreMembers: memberPage.has_more && Boolean(nextCursor) && nextCursor !== cursor,
      });
    } catch (error) {
      requestedMemberCursors.delete(cursor);
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const cursorIsInvalid = error instanceof ApiError && error.code === 42213;
      this.setData({
        memberLoadError: getMemberPaginationError(error),
        ...(cursorIsInvalid ? { nextMemberCursor: null, hasMoreMembers: false } : {}),
      });
    } finally {
      this.setData({ isLoadingMoreMembers: false });
    }
  },

  onMemberLoadRetry() {
    if (!this.data.hasMoreMembers) {
      void this.loadGroup();
      return;
    }

    void this.onReachBottom();
  },

  onBackToIndex() {
    wx.reLaunch({ url: "/pages/index/index" });
  },

  onOpenDeleteConfirmation() {
    const group = this.data.group;
    if (
      this.data.pageStatus !== "ready" ||
      !group ||
      group.current_user_role !== "owner" ||
      this.data.isDeleting
    ) {
      return;
    }

    this.setData({
      showDeleteConfirmation: true,
      deleteConfirmationName: "",
      isDeleteConfirmationMatched: false,
      deleteErrorMessage: "",
    });
  },

  onDeleteConfirmationInput(event: WechatMiniprogram.Input) {
    const deleteConfirmationName = event.detail.value;
    const groupName = this.data.group?.name ?? "";
    this.setData({
      deleteConfirmationName,
      isDeleteConfirmationMatched:
        Boolean(groupName) && deleteConfirmationName.trim() === groupName,
      deleteErrorMessage: "",
    });
  },

  onCancelDelete() {
    if (this.data.isDeleting) {
      return;
    }

    this.setData({
      showDeleteConfirmation: false,
      deleteConfirmationName: "",
      isDeleteConfirmationMatched: false,
      deleteErrorMessage: "",
    });
  },

  preventDialogClose() {
    // Keep taps inside the confirmation dialog from reaching its cancel backdrop.
  },

  async onConfirmDelete() {
    const group = this.data.group;
    const confirmationName = this.data.deleteConfirmationName.trim();
    if (
      this.data.isDeleting ||
      this.data.pageStatus !== "ready" ||
      !group ||
      group.current_user_role !== "owner" ||
      !this.data.isDeleteConfirmationMatched ||
      confirmationName !== group.name
    ) {
      return;
    }

    this.setData({ isDeleting: true, deleteErrorMessage: "" });
    try {
      await deleteGroup(group.id, confirmationName);
      inviteRequestGeneration += 1;
      wx.hideShareMenu();
      this.setData({
        pageStatus: "loading",
        group: null,
        members: [],
        recentHangouts: [],
        hangoutStatus: "loading",
        inviteStatus: "idle",
        inviteToken: "",
        inviteExpiresAt: 0,
        inviteErrorMessage: "",
        showDeleteConfirmation: false,
      });
      wx.showToast({ title: "群组已删除", icon: "success" });
      try {
        await reLaunchToIndex();
      } catch {
        wx.reLaunch({ url: "/pages/index/index" });
      }
      return;
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      if (error instanceof ApiError) {
        if (error.code === 40310) {
          wx.showToast({ title: "只有群主可以删除群组", icon: "none" });
          await this.loadGroup(true);
          return;
        }

        if (error.code === 40410) {
          inviteRequestGeneration += 1;
          wx.hideShareMenu();
          this.setData({
            pageStatus: "loading",
            group: null,
            members: [],
            recentHangouts: [],
            hangoutStatus: "loading",
            inviteStatus: "idle",
            inviteToken: "",
            inviteExpiresAt: 0,
            inviteErrorMessage: "",
            showDeleteConfirmation: false,
          });
          wx.showToast({ title: "群组不存在或已被删除", icon: "none" });
          try {
            await reLaunchToIndex();
          } catch {
            wx.reLaunch({ url: "/pages/index/index" });
          }
          return;
        }

        if (error.code === 42214) {
          this.setData({
            isDeleteConfirmationMatched: false,
            deleteErrorMessage: "输入的群组名称不一致，请重新输入。",
          });
          return;
        }

        if (error.code === 40910) {
          wx.showToast({ title: "群组状态已变化，正在刷新", icon: "none" });
          await this.loadGroup(true);
          return;
        }

        if (error.statusCode === 403) {
          this.setData({ deleteErrorMessage: "当前账号无法删除这个群组。" });
          return;
        }
      }

      this.setData({
        deleteErrorMessage: getUserFacingError(error, "删除失败，请稍后重试"),
      });
    } finally {
      this.setData({ isDeleting: false });
    }
  },

  onShareAppMessage() {
    const group = this.data.group;
    const inviteIsReady =
      this.data.inviteStatus === "ready" &&
      Boolean(this.data.inviteToken) &&
      this.data.inviteExpiresAt > Date.now() + INVITE_EXPIRY_SKEW_MS;

    if (!group || !inviteIsReady) {
      return {
        title: "来约玩，和朋友更快定下见面安排",
        path: "/pages/index/index",
      };
    }

    const query = [
      `group_id=${encodeURIComponent(group.id)}`,
      `token=${encodeURIComponent(this.data.inviteToken)}`,
    ].join("&");
    return {
      title: `${this.data.displayName} 邀请你加入「${group.name}」`,
      path: `/pages/groups/join/index?${query}`,
    };
  },
});
