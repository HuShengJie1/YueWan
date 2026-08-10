import { createGroup } from "../../../services/group";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import { getUserFacingError } from "../../../utils/errors";
import { reLaunchToLogin } from "../../../utils/navigation";

type CreatePageStatus = "loading" | "error" | "ready";

function validateName(value: string): string {
  const name = value.trim();
  if (!name) {
    return "请填写群组名称";
  }

  if (name.length > 40) {
    return "群组名称不能超过 40 个字符";
  }

  return "";
}

function validateDescription(value: string): string {
  return value.trim().length > 200 ? "群组简介不能超过 200 个字符" : "";
}

function getCreateError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 40001) {
      return "群组名称或简介不符合要求，请检查后重试。";
    }

    if (error.code === 40910) {
      return "群组创建发生冲突，请重试。";
    }
  }

  return getUserFacingError(error, "创建群组失败，请稍后重试");
}

Page({
  data: {
    pageStatus: "loading" as CreatePageStatus,
    name: "",
    description: "",
    nameError: "",
    descriptionError: "",
    errorMessage: "",
    isSubmitting: false,
  },

  onLoad() {
    void this.preparePage();
  },

  async preparePage(force = false) {
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
          errorMessage: authState.errorMessage ?? "无法恢复登录状态",
        });
        return;
      }

      if (!authState.user.profile_completed) {
        wx.reLaunch({ url: "/pages/profile/profile" });
        return;
      }

      this.setData({ pageStatus: "ready" });
    } catch (error) {
      this.setData({
        pageStatus: "error",
        errorMessage: getUserFacingError(error, "页面加载失败，请稍后重试"),
      });
    }
  },

  onRetry() {
    void this.preparePage(true);
  },

  onNameInput(event: WechatMiniprogram.Input) {
    const name = event.detail.value;
    this.setData({ name, nameError: validateName(name), errorMessage: "" });
  },

  onDescriptionInput(event: WechatMiniprogram.TextareaInput) {
    const description = event.detail.value;
    this.setData({
      description,
      descriptionError: validateDescription(description),
      errorMessage: "",
    });
  },

  async onSubmit() {
    if (this.data.isSubmitting) {
      return;
    }

    const name = this.data.name.trim();
    const description = this.data.description.trim();
    const nameError = validateName(name);
    const descriptionError = validateDescription(description);
    if (nameError || descriptionError) {
      this.setData({ nameError, descriptionError });
      return;
    }

    this.setData({ isSubmitting: true, errorMessage: "" });
    try {
      const group = await createGroup({
        name,
        ...(description ? { description } : {}),
      });
      wx.showToast({ title: "群组已创建", icon: "success" });
      wx.redirectTo({
        url: `/pages/groups/detail/index?group_id=${encodeURIComponent(group.id)}`,
      });
    } catch (error) {
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      this.setData({
        errorMessage: getCreateError(error),
      });
    } finally {
      this.setData({ isSubmitting: false });
    }
  },
});
