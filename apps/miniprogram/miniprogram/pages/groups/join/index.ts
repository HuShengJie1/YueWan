import { joinGroup } from "../../../services/group";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import {
  clearPendingGroupInvite,
  readPendingGroupInvite,
  savePendingGroupInvite,
} from "../../../stores/pending-group-invite";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId } from "../../../utils/group";
import {
  reLaunchForAuthenticatedUser,
  reLaunchToIndex,
  reLaunchToLogin,
} from "../../../utils/navigation";

type JoinPageStatus = "loading" | "error" | "invalid" | "ready";

const MAX_INVITE_TOKEN_LENGTH = 4096;

let launchOptions: Record<string, string | undefined> | undefined;
let preservePendingOnUnload = false;

function isValidInviteToken(inviteToken: string): boolean {
  return inviteToken.length > 0 && inviteToken.length <= MAX_INVITE_TOKEN_LENGTH;
}

function isTerminalInviteError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === 40410 ||
      error.code === 42210 ||
      error.code === 42211 ||
      error.code === 42212 ||
      error.statusCode === 422)
  );
}

function getInvalidInvitationMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 42211) {
      return "这份邀请已经过期，请联系朋友重新分享。";
    }

    if (error.code === 42212) {
      return "这份邀请与当前群组不匹配，请使用朋友最新分享的入口。";
    }

    if (error.code === 40410) {
      return "这个群组已不存在或暂时不可加入，请联系邀请人确认。";
    }
  }

  return "这份邀请无法验证，可能已失效。请联系朋友重新分享。";
}

function getJoinError(error: unknown): string {
  if (error instanceof ApiError && error.code === 40910) {
    return "群组状态正在变化，请稍后重试。";
  }

  return getUserFacingError(error, "加入失败，请稍后重试");
}

async function redirectPreservingPendingInvite(navigate: () => Promise<void>): Promise<void> {
  preservePendingOnUnload = true;
  try {
    await navigate();
  } catch (error) {
    preservePendingOnUnload = false;
    throw error;
  }
}

Page({
  data: {
    pageStatus: "loading" as JoinPageStatus,
    groupId: "",
    errorMessage: "",
    joinErrorMessage: "",
    isJoining: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    preservePendingOnUnload = false;
    launchOptions = options;
    void this.prepareInvitation(options);
  },

  onUnload() {
    launchOptions = undefined;
    if (!preservePendingOnUnload) {
      clearPendingGroupInvite();
    }
  },

  async prepareInvitation(options?: Record<string, string | undefined>, forceAuth = false) {
    this.setData({ pageStatus: "loading", errorMessage: "", joinErrorMessage: "" });

    const optionGroupId = options?.group_id?.trim() ?? "";
    const optionToken = options?.token?.trim() ?? "";
    let groupId = "";

    if (optionGroupId || optionToken) {
      if (!isValidGroupId(optionGroupId) || !isValidInviteToken(optionToken)) {
        clearPendingGroupInvite();
        this.showInvalidInvitation();
        return;
      }

      try {
        savePendingGroupInvite(optionGroupId, optionToken);
      } catch {
        this.setData({
          pageStatus: "error",
          errorMessage: "无法保存这份邀请，请清理小程序缓存后重试。",
        });
        return;
      }
      groupId = optionGroupId;
    } else {
      const pendingInvite = readPendingGroupInvite();
      if (!pendingInvite || !isValidGroupId(pendingInvite.group_id)) {
        this.showInvalidInvitation();
        return;
      }
      groupId = pendingInvite.group_id;
    }

    this.setData({ groupId });
    try {
      const authState = await bootstrapAuth(forceAuth);
      if (authState.status === "unauthenticated" || !authState.user) {
        await redirectPreservingPendingInvite(() =>
          reLaunchToLogin(authState.errorMessage ? "expired" : undefined),
        );
        return;
      }

      if (authState.status === "error") {
        this.setData({
          pageStatus: "error",
          errorMessage: authState.errorMessage ?? "无法恢复登录状态，请重试。",
        });
        return;
      }

      if (!authState.user.profile_completed) {
        const user = authState.user;
        await redirectPreservingPendingInvite(() => reLaunchForAuthenticatedUser(user));
        return;
      }

      this.setData({ pageStatus: "ready" });
    } catch (error) {
      this.setData({
        pageStatus: "error",
        errorMessage: getUserFacingError(error, "无法确认登录状态，请稍后重试"),
      });
    }
  },

  showInvalidInvitation(message?: string) {
    this.setData({
      pageStatus: "invalid",
      errorMessage: message ?? "邀请无效、已过期，或与当前群组不匹配。请联系朋友重新分享。",
    });
  },

  onRetry() {
    void this.prepareInvitation(launchOptions, true);
  },

  async onJoin() {
    if (this.data.isJoining) {
      return;
    }

    const pendingInvite = readPendingGroupInvite();
    if (!pendingInvite || pendingInvite.group_id !== this.data.groupId) {
      clearPendingGroupInvite();
      this.showInvalidInvitation();
      return;
    }

    this.setData({ isJoining: true, joinErrorMessage: "" });
    try {
      await joinGroup(pendingInvite.group_id, pendingInvite.invite_token);
      clearPendingGroupInvite();
      wx.showToast({ title: "已加入群组", icon: "success" });
      wx.redirectTo({
        url: `/pages/groups/detail/index?group_id=${encodeURIComponent(pendingInvite.group_id)}`,
      });
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await redirectPreservingPendingInvite(() => reLaunchToLogin("expired"));
        return;
      }

      if (isTerminalInviteError(error)) {
        clearPendingGroupInvite();
        this.showInvalidInvitation(getInvalidInvitationMessage(error));
        return;
      }

      this.setData({
        joinErrorMessage: getJoinError(error),
      });
    } finally {
      this.setData({ isJoining: false });
    }
  },

  onCancel() {
    clearPendingGroupInvite();
    void reLaunchToIndex();
  },
});
