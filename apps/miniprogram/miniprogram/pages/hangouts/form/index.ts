import { createHangout, getHangout, updateHangout } from "../../../services/hangout";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { Hangout, HangoutWriteInput } from "../../../types/hangout";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import {
  formatLocalDateInput,
  formatLocalTimeInput,
  toLocalDateTimeFields,
} from "../../../utils/hangout";
import { reLaunchToLogin } from "../../../utils/navigation";

type FormMode = "create" | "edit";
type FormPageStatus = "loading" | "error" | "ready";

let formRequestGeneration = 0;

function countCharacters(value: string): number {
  return Array.from(value).length;
}

function validateTitle(value: string): string {
  const title = value.trim();
  if (!title) {
    return "请填写约玩标题";
  }

  if (countCharacters(title) > 60) {
    return "约玩标题不能超过 60 个字符";
  }

  return "";
}

function validateDescription(value: string): string {
  return countCharacters(value.trim()) > 500 ? "约玩说明不能超过 500 个字符" : "";
}

function parseLocalDeadline(dateValue: string, timeValue: string): Date | null {
  const dateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  const timeMatch = /^(\d{2}):(\d{2})$/.exec(timeValue);
  if (!dateMatch || !timeMatch) {
    return null;
  }

  const year = Number(dateMatch[1]);
  const month = Number(dateMatch[2]);
  const day = Number(dateMatch[3]);
  const hour = Number(timeMatch[1]);
  const minute = Number(timeMatch[2]);
  const deadline = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (
    deadline.getFullYear() !== year ||
    deadline.getMonth() !== month - 1 ||
    deadline.getDate() !== day ||
    deadline.getHours() !== hour ||
    deadline.getMinutes() !== minute
  ) {
    return null;
  }

  return deadline;
}

function validateDeadline(dateValue: string, timeValue: string): string {
  if (!dateValue && !timeValue) {
    return "";
  }

  if (!dateValue || !timeValue) {
    return "请选择完整的截止日期和时间";
  }

  const deadline = parseLocalDeadline(dateValue, timeValue);
  if (!deadline) {
    return "截止时间格式无效，请重新选择";
  }

  return deadline.getTime() <= Date.now() ? "投票截止时间必须晚于当前时间" : "";
}

function isFormValid(
  title: string,
  description: string,
  deadlineDate: string,
  deadlineTime: string,
): boolean {
  return (
    !validateTitle(title) &&
    !validateDescription(description) &&
    !validateDeadline(deadlineDate, deadlineTime)
  );
}

function getPickerDefaults(): {
  minimumDate: string;
  datePickerValue: string;
  timePickerValue: string;
} {
  const now = new Date();
  const suggested = new Date(now.getTime() + 60 * 60 * 1000);
  suggested.setSeconds(0, 0);
  return {
    minimumDate: formatLocalDateInput(now),
    datePickerValue: formatLocalDateInput(suggested),
    timePickerValue: formatLocalTimeInput(suggested),
  };
}

function redirectTo(url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.redirectTo({
      url,
      success: () => resolve(),
      fail: ({ errMsg }) => reject(new Error(errMsg)),
    });
  });
}

function navigateBack(): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.navigateBack({
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
      title: "无法打开约玩局",
      message: "约玩局不存在或无权查看。",
      canRetry: false,
    };
  }

  return {
    title: "页面暂时无法打开",
    message: getUserFacingError(error, "无法读取约玩局，请稍后重试"),
    canRetry: true,
  };
}

Page({
  data: {
    pageStatus: "loading" as FormPageStatus,
    mode: "create" as FormMode,
    groupId: "",
    hangoutId: "",
    title: "",
    description: "",
    titleCount: 0,
    descriptionCount: 0,
    titleError: "",
    descriptionError: "",
    deadlineError: "",
    deadlineDate: "",
    deadlineTime: "",
    minimumDate: "",
    datePickerValue: "",
    timePickerValue: "",
    formCanSubmit: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    isSubmitting: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    formRequestGeneration += 1;
    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    const modeValue = options.mode?.trim() ?? "";
    const mode: FormMode = modeValue === "edit" ? "edit" : "create";
    const invalidMode = Boolean(modeValue) && modeValue !== "edit";
    const invalidEditParameters = mode === "edit" ? !isValidUuid(hangoutId) : Boolean(hangoutId);

    if (!isValidGroupId(groupId) || invalidMode || invalidEditParameters) {
      this.setData({
        pageStatus: "error",
        errorTitle: "页面链接无效",
        errorMessage: "这个链接缺少有效的群组或约玩局信息，请返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ mode, groupId, hangoutId, ...getPickerDefaults() });
    wx.setNavigationBarTitle({ title: mode === "edit" ? "编辑约玩" : "发起约玩" });
    void this.preparePage();
  },

  onUnload() {
    formRequestGeneration += 1;
  },

  async preparePage(forceAuth = false) {
    const requestGeneration = ++formRequestGeneration;
    this.setData({
      pageStatus: "loading",
      errorMessage: "",
      isSubmitting: false,
      ...getPickerDefaults(),
    });
    try {
      const authState = await bootstrapAuth(forceAuth);
      if (requestGeneration !== formRequestGeneration) {
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

      if (this.data.mode === "edit") {
        const hangout = await getHangout(this.data.groupId, this.data.hangoutId);
        if (requestGeneration !== formRequestGeneration) {
          return;
        }

        if (hangout.status !== "draft") {
          this.setData({
            pageStatus: "error",
            errorTitle: "约玩局不能编辑",
            errorMessage: "约玩局状态已经变化，请返回详情查看最新状态。",
            canRetry: false,
          });
          return;
        }

        this.fillForm(hangout);
        return;
      }

      this.setData({ pageStatus: "ready" });
    } catch (error) {
      if (requestGeneration !== formRequestGeneration) {
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

  fillForm(hangout: Hangout) {
    const deadline = hangout.voting_deadline
      ? toLocalDateTimeFields(hangout.voting_deadline)
      : null;
    const title = hangout.title;
    const description = hangout.description ?? "";
    const deadlineDate = deadline?.date ?? "";
    const deadlineTime = deadline?.time ?? "";
    const deadlineError = validateDeadline(deadlineDate, deadlineTime);
    this.setData({
      pageStatus: "ready",
      title,
      description,
      titleCount: countCharacters(title),
      descriptionCount: countCharacters(description),
      titleError: "",
      descriptionError: "",
      deadlineError,
      deadlineDate,
      deadlineTime,
      formCanSubmit: isFormValid(title, description, deadlineDate, deadlineTime),
    });
  },

  onRetry() {
    void this.preparePage(true);
  },

  onBack() {
    wx.navigateBack();
  },

  onTitleInput(event: WechatMiniprogram.Input) {
    const title = event.detail.value;
    const titleError = validateTitle(title);
    this.setData({
      title,
      titleCount: countCharacters(title),
      titleError,
      errorMessage: "",
      formCanSubmit: isFormValid(
        title,
        this.data.description,
        this.data.deadlineDate,
        this.data.deadlineTime,
      ),
    });
  },

  onDescriptionInput(event: WechatMiniprogram.TextareaInput) {
    const description = event.detail.value;
    const descriptionError = validateDescription(description);
    this.setData({
      description,
      descriptionCount: countCharacters(description),
      descriptionError,
      errorMessage: "",
      formCanSubmit: isFormValid(
        this.data.title,
        description,
        this.data.deadlineDate,
        this.data.deadlineTime,
      ),
    });
  },

  onDeadlineDateChange(event: WechatMiniprogram.PickerChange) {
    const deadlineDate = String(event.detail.value);
    const deadlineTime = this.data.deadlineTime || this.data.timePickerValue;
    const deadlineError = validateDeadline(deadlineDate, deadlineTime);
    this.setData({
      deadlineDate,
      deadlineTime,
      deadlineError,
      errorMessage: "",
      formCanSubmit: isFormValid(
        this.data.title,
        this.data.description,
        deadlineDate,
        deadlineTime,
      ),
    });
  },

  onDeadlineTimeChange(event: WechatMiniprogram.PickerChange) {
    const deadlineTime = String(event.detail.value);
    const deadlineDate = this.data.deadlineDate || this.data.datePickerValue;
    const deadlineError = validateDeadline(deadlineDate, deadlineTime);
    this.setData({
      deadlineDate,
      deadlineTime,
      deadlineError,
      errorMessage: "",
      formCanSubmit: isFormValid(
        this.data.title,
        this.data.description,
        deadlineDate,
        deadlineTime,
      ),
    });
  },

  onClearDeadline() {
    if (this.data.isSubmitting) {
      return;
    }

    this.setData({
      deadlineDate: "",
      deadlineTime: "",
      deadlineError: "",
      errorMessage: "",
      formCanSubmit: isFormValid(this.data.title, this.data.description, "", ""),
      ...getPickerDefaults(),
    });
  },

  async onSubmit() {
    if (this.data.isSubmitting || this.data.pageStatus !== "ready") {
      return;
    }

    const title = this.data.title.trim();
    const description = this.data.description.trim();
    const titleError = validateTitle(title);
    const descriptionError = validateDescription(description);
    const deadlineError = validateDeadline(this.data.deadlineDate, this.data.deadlineTime);
    if (titleError || descriptionError || deadlineError) {
      this.setData({
        titleError,
        descriptionError,
        deadlineError,
        formCanSubmit: false,
      });
      return;
    }

    const deadline =
      this.data.deadlineDate && this.data.deadlineTime
        ? parseLocalDeadline(this.data.deadlineDate, this.data.deadlineTime)
        : null;
    const input: HangoutWriteInput = {
      title,
      description: description || null,
      voting_deadline: deadline?.toISOString() ?? null,
    };
    const submissionGeneration = formRequestGeneration;
    this.setData({ isSubmitting: true, errorMessage: "" });
    try {
      if (this.data.mode === "edit") {
        await updateHangout(this.data.groupId, this.data.hangoutId, input);
        wx.showToast({ title: "约玩局已更新", icon: "success" });
        await this.returnFromEdit();
      } else {
        const hangout = await createHangout(this.data.groupId, input);
        wx.showToast({ title: "约玩局已创建", icon: "success" });
        await redirectTo(this.detailUrl(hangout.id));
      }
    } catch (error) {
      if (submissionGeneration !== formRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      if (error instanceof ApiError) {
        if (error.code === 40320) {
          this.setData({ errorMessage: "你没有编辑这个约玩局的权限。" });
          wx.showToast({ title: "没有编辑权限", icon: "none" });
          return;
        }

        if (error.code === 40410 || error.code === 40420) {
          this.setData({
            pageStatus: "error",
            errorTitle: "无法打开约玩局",
            errorMessage: "约玩局不存在或无权查看。",
            canRetry: false,
          });
          return;
        }

        if (error.code === 40920) {
          await this.handleStateConflict();
          return;
        }

        if (error.code === 40001) {
          this.setData({
            errorMessage: "标题、说明或截止时间不符合要求，请检查后重试。",
          });
          return;
        }
      }

      this.setData({
        errorMessage: getUserFacingError(error, "保存约玩局失败，请稍后重试"),
      });
    } finally {
      if (submissionGeneration === formRequestGeneration) {
        this.setData({ isSubmitting: false });
      }
    }
  },

  detailUrl(hangoutId?: string): string {
    const resolvedHangoutId = hangoutId ?? this.data.hangoutId;
    const query = [
      `group_id=${encodeURIComponent(this.data.groupId)}`,
      `hangout_id=${encodeURIComponent(resolvedHangoutId)}`,
    ].join("&");
    return `/pages/hangouts/detail/index?${query}`;
  },

  async returnFromEdit() {
    if (getCurrentPages().length > 1) {
      try {
        await navigateBack();
        return;
      } catch {
        // Fall through to the detail page if the previous page is unavailable.
      }
    }

    await redirectTo(this.detailUrl());
  },

  async handleStateConflict() {
    wx.showToast({ title: "约玩局状态已经变化", icon: "none" });
    this.setData({ pageStatus: "loading", errorMessage: "" });
    try {
      const hangout = await getHangout(this.data.groupId, this.data.hangoutId);
      if (hangout.status === "draft") {
        this.fillForm(hangout);
        this.setData({ errorMessage: "约玩局已重新加载，请确认最新内容后再保存。" });
        return;
      }

      await this.returnFromEdit();
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
});
