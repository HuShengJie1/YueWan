import { bootstrapAuth, getAuthState, updateAuthenticatedUser } from "../../stores/auth";
import { updateCurrentUser, uploadCurrentUserAvatar } from "../../services/user";
import { ApiError } from "../../services/request";
import { getUserFacingError } from "../../utils/errors";
import { reLaunchForAuthenticatedUser, reLaunchToLogin } from "../../utils/navigation";

type ProfilePageStatus = "loading" | "ready" | "error";
type ChooseAvatarEvent = WechatMiniprogram.CustomEvent<{ avatarUrl: string }>;

const MAX_AVATAR_FILE_SIZE = 5 * 1024 * 1024;

function getAvatarUploadError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 41301) {
      return "头像文件不能超过 5 MB";
    }

    if (error.code === 41501) {
      return "请选择 JPEG、PNG 或 WebP 图片";
    }

    if (error.code === 42201) {
      return "头像图片无法识别，请重新选择";
    }

    if (error.code === 50303) {
      return "头像存储暂时不可用，请稍后重试";
    }
  }

  return getUserFacingError(error, "头像上传失败，请重试");
}

function validateAvatarFile(filePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().stat({
      path: filePath,
      success: ({ stats }) => {
        if (Array.isArray(stats) || !stats.isFile()) {
          reject(new Error("选择的头像文件无效"));
          return;
        }

        if (stats.size > MAX_AVATAR_FILE_SIZE) {
          reject(new Error("头像文件不能超过 5 MB"));
          return;
        }

        resolve();
      },
      fail: () => reject(new Error("无法读取选择的头像")),
    });
  });
}

Page({
  data: {
    pageStatus: "loading" as ProfilePageStatus,
    nickname: "",
    avatarUrl: "",
    isUploadingAvatar: false,
    avatarErrorMessage: "",
    isSaving: false,
    errorMessage: "",
  },

  onLoad() {
    void this.loadProfile();
  },

  async loadProfile(force = false) {
    this.setData({ pageStatus: "loading", errorMessage: "" });
    try {
      const authState = await bootstrapAuth(force);
      if (authState.status === "unauthenticated" || !authState.user) {
        await reLaunchToLogin(authState.errorMessage ? "expired" : undefined);
        return;
      }

      if (authState.status === "error") {
        this.setData({
          pageStatus: "error",
          errorMessage: authState.errorMessage ?? "无法读取用户资料",
        });
        return;
      }

      this.setData({
        pageStatus: "ready",
        nickname: authState.user.nickname ?? "",
        avatarUrl: authState.user.avatar_url ?? "",
        avatarErrorMessage: "",
      });
    } catch (error) {
      this.setData({
        pageStatus: "error",
        errorMessage: getUserFacingError(error, "无法读取用户资料"),
      });
    }
  },

  onRetry() {
    void this.loadProfile(true);
  },

  onNicknameInput(event: WechatMiniprogram.Input) {
    this.setData({ nickname: event.detail.value, errorMessage: "" });
  },

  async onChooseAvatar(event: ChooseAvatarEvent) {
    if (this.data.isUploadingAvatar || this.data.isSaving) {
      return;
    }

    const filePath = event.detail.avatarUrl;
    if (!filePath) {
      this.setData({ avatarErrorMessage: "未获取到选择的头像" });
      return;
    }

    const previousAvatarUrl = this.data.avatarUrl;
    this.setData({
      avatarUrl: filePath,
      isUploadingAvatar: true,
      avatarErrorMessage: "",
    });

    try {
      await validateAvatarFile(filePath);
      const user = await uploadCurrentUserAvatar(filePath);
      if (!user.avatar_url) {
        throw new Error("头像上传成功，但服务未返回头像地址");
      }

      updateAuthenticatedUser(user);
      this.setData({ avatarUrl: user.avatar_url });
      wx.showToast({ title: "头像已更新", icon: "success" });
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        avatarUrl: previousAvatarUrl,
        avatarErrorMessage: getAvatarUploadError(error),
      });
    } finally {
      this.setData({ isUploadingAvatar: false });
    }
  },

  async onSave() {
    if (this.data.isSaving || this.data.isUploadingAvatar) {
      return;
    }

    const nickname = this.data.nickname.trim();
    if (!nickname) {
      this.setData({ errorMessage: "请填写一个昵称" });
      return;
    }

    this.setData({ isSaving: true, errorMessage: "" });
    try {
      const user = await updateCurrentUser({ nickname });
      updateAuthenticatedUser(user);

      if (!user.profile_completed) {
        this.setData({ errorMessage: "资料已保存，但账号状态尚未更新，请稍后重试" });
        return;
      }

      wx.showToast({ title: "资料已保存", icon: "success" });
      await reLaunchForAuthenticatedUser(user);
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        errorMessage: getUserFacingError(error, "保存资料失败，请稍后重试"),
      });
    } finally {
      this.setData({ isSaving: false });
    }
  },
});
