import { ApiError } from "../../../services/request";
import { createTimeOption, updateTimeOption } from "../../../services/time-option";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { TimeOption, TimeOptionWriteInput } from "../../../types/time-option";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { reLaunchToIndex, reLaunchToLogin } from "../../../utils/navigation";
import {
  formatLocalDateInput,
  formatLocalTimeInput,
  parseLocalDateTime,
  toLocalDateTimeFields,
} from "../../../utils/time-option";

type FormMode = "create" | "edit";
type FormPageStatus = "loading" | "error" | "ready";

const DISPLAY_LABEL_MAX_LENGTH = 80;

let pageAlive = false;
let formRequestGeneration = 0;
let editingTimeOption: TimeOption | null = null;
let editDataPromise: Promise<TimeOption | null> | null = null;
let resolveEditData: ((timeOption: TimeOption | null) => void) | null = null;
let editDataTimer: ReturnType<typeof setTimeout> | null = null;

function countCharacters(value: string): number {
  return Array.from(value).length;
}

function getPickerDefaults(): {
  minimumDate: string;
  dateValue: string;
  startTimeValue: string;
  endTimeValue: string;
} {
  const now = new Date();
  const start = new Date(now.getTime() + 60 * 60 * 1000);
  start.setSeconds(0, 0);
  const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
  return {
    minimumDate: formatLocalDateInput(now),
    dateValue: formatLocalDateInput(start),
    startTimeValue: formatLocalTimeInput(start),
    endTimeValue: formatLocalTimeInput(end),
  };
}

function validateTimes(
  dateValue: string,
  startTimeValue: string,
  endDateValue: string,
  endTimeValue: string,
): string {
  if (!dateValue || !startTimeValue) {
    return "请选择完整的日期和开始时间";
  }

  const startsAt = parseLocalDateTime(dateValue, startTimeValue);
  if (!startsAt) {
    return "开始时间格式无效，请重新选择";
  }
  if (startsAt.getTime() <= Date.now()) {
    return "开始时间必须晚于当前时间";
  }

  if (endDateValue || endTimeValue) {
    if (!endDateValue || !endTimeValue) {
      return "请选择完整的结束日期和时间";
    }
    const endsAt = parseLocalDateTime(endDateValue, endTimeValue);
    if (!endsAt) {
      return "结束时间格式无效，请重新选择";
    }
    if (endsAt.getTime() <= startsAt.getTime()) {
      return "结束时间必须晚于开始时间";
    }
  }

  return "";
}

function validateDisplayLabel(value: string): string {
  return countCharacters(value.trim()) > DISPLAY_LABEL_MAX_LENGTH
    ? `展示标签不能超过 ${DISPLAY_LABEL_MAX_LENGTH} 个字符`
    : "";
}

function isFormValid(
  dateValue: string,
  startTimeValue: string,
  endDateValue: string,
  endTimeValue: string,
  displayLabel: string,
): boolean {
  return (
    !validateTimes(dateValue, startTimeValue, endDateValue, endTimeValue) &&
    !validateDisplayLabel(displayLabel)
  );
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

function isTimeOption(value: unknown): value is TimeOption {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const timeOption = value as Partial<TimeOption>;
  return (
    typeof timeOption.id === "string" &&
    typeof timeOption.hangout_id === "string" &&
    typeof timeOption.starts_at === "string" &&
    typeof timeOption.can_manage === "boolean"
  );
}

function prepareEditDataChannel(page: WechatMiniprogram.Page.TrivialInstance) {
  editDataPromise = new Promise((resolve) => {
    resolveEditData = resolve;
  });
  const eventChannel = page.getOpenerEventChannel();
  if (!eventChannel.on) {
    resolveEditData?.(null);
    resolveEditData = null;
    return;
  }
  eventChannel.on("timeOptionEditData", (value: unknown) => {
    if (editDataTimer) {
      clearTimeout(editDataTimer);
      editDataTimer = null;
    }
    editingTimeOption = isTimeOption(value) ? value : null;
    resolveEditData?.(editingTimeOption);
    resolveEditData = null;
  });
  editDataTimer = setTimeout(() => {
    resolveEditData?.(null);
    resolveEditData = null;
    editDataTimer = null;
  }, 1500);
}

Page({
  data: {
    pageStatus: "loading" as FormPageStatus,
    mode: "create" as FormMode,
    groupId: "",
    hangoutId: "",
    timeOptionId: "",
    dateValue: "",
    startTimeValue: "",
    endDateValue: "",
    endTimeValue: "",
    displayLabel: "",
    displayLabelCount: 0,
    minimumDate: "",
    defaultEndTimeValue: "",
    timeError: "",
    displayLabelError: "",
    formCanSubmit: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    isSubmitting: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    pageAlive = true;
    formRequestGeneration += 1;
    editingTimeOption = null;
    editDataPromise = null;
    resolveEditData = null;
    if (editDataTimer) {
      clearTimeout(editDataTimer);
      editDataTimer = null;
    }

    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    const timeOptionId = options.time_option_id?.trim() ?? "";
    const modeValue = options.mode?.trim() ?? "create";
    const mode: FormMode = modeValue === "edit" ? "edit" : "create";
    const invalidMode = modeValue !== "create" && modeValue !== "edit";
    const invalidTimeOptionId =
      mode === "edit" ? !isValidUuid(timeOptionId) : Boolean(timeOptionId);

    if (!isValidGroupId(groupId) || !isValidUuid(hangoutId) || invalidMode || invalidTimeOptionId) {
      this.setData({
        pageStatus: "error",
        errorTitle: "页面链接无效",
        errorMessage: "这个链接缺少有效的约玩局或候选时间信息，请安全返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    if (mode === "edit") {
      prepareEditDataChannel(this);
    }
    const defaults = getPickerDefaults();
    this.setData({
      mode,
      groupId,
      hangoutId,
      timeOptionId,
      minimumDate: defaults.minimumDate,
      dateValue: mode === "create" ? defaults.dateValue : "",
      startTimeValue: mode === "create" ? defaults.startTimeValue : "",
      defaultEndTimeValue: defaults.endTimeValue,
      formCanSubmit:
        mode === "create"
          ? isFormValid(defaults.dateValue, defaults.startTimeValue, "", "", "")
          : false,
    });
    wx.setNavigationBarTitle({ title: mode === "edit" ? "编辑候选时间" : "添加候选时间" });
    void this.preparePage();
  },

  onUnload() {
    pageAlive = false;
    formRequestGeneration += 1;
    if (editDataTimer) {
      clearTimeout(editDataTimer);
      editDataTimer = null;
    }
    resolveEditData?.(null);
    resolveEditData = null;
    editDataPromise = null;
    editingTimeOption = null;
  },

  async preparePage(forceAuth = false) {
    const requestGeneration = ++formRequestGeneration;
    this.setData({ pageStatus: "loading", errorMessage: "", isSubmitting: false });
    try {
      const authState = await bootstrapAuth(forceAuth);
      if (!pageAlive || requestGeneration !== formRequestGeneration) {
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
        const timeOption = editingTimeOption ?? (await editDataPromise);
        if (!pageAlive || requestGeneration !== formRequestGeneration) {
          return;
        }
        if (
          !timeOption ||
          timeOption.id !== this.data.timeOptionId ||
          timeOption.hangout_id !== this.data.hangoutId ||
          !timeOption.can_manage
        ) {
          this.setData({
            pageStatus: "error",
            errorTitle: "候选时间不可用",
            errorMessage: "候选时间已变化或无法编辑，请返回详情页重新进入。",
            canRetry: false,
          });
          return;
        }
        this.fillForm(timeOption);
        return;
      }

      this.setData({ pageStatus: "ready" });
    } catch (error) {
      if (!pageAlive || requestGeneration !== formRequestGeneration) {
        return;
      }
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }
      this.setData({
        pageStatus: "error",
        errorTitle: "页面暂时无法打开",
        errorMessage: getUserFacingError(error, "无法准备候选时间表单，请稍后重试"),
        canRetry: true,
      });
    }
  },

  fillForm(timeOption: TimeOption) {
    editingTimeOption = timeOption;
    const start = toLocalDateTimeFields(timeOption.starts_at);
    const end = timeOption.ends_at ? toLocalDateTimeFields(timeOption.ends_at) : null;
    if (!start || (timeOption.ends_at && !end)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "候选时间不可编辑",
        errorMessage: "当前时间信息无法用本地表单表示，请返回详情页查看。",
        canRetry: false,
      });
      return;
    }

    const displayLabel = timeOption.display_label ?? "";
    const endDateValue = end?.date ?? "";
    const endTimeValue = end?.time ?? "";
    const defaults = getPickerDefaults();
    this.setData({
      pageStatus: "ready",
      dateValue: start.date,
      startTimeValue: start.time,
      endDateValue,
      endTimeValue,
      displayLabel,
      displayLabelCount: countCharacters(displayLabel),
      minimumDate: defaults.minimumDate,
      defaultEndTimeValue: defaults.endTimeValue,
      timeError: validateTimes(start.date, start.time, endDateValue, endTimeValue),
      displayLabelError: validateDisplayLabel(displayLabel),
      formCanSubmit: isFormValid(start.date, start.time, endDateValue, endTimeValue, displayLabel),
    });
  },

  updateValidation(
    dateValue: string,
    startTimeValue: string,
    endDateValue: string,
    endTimeValue: string,
    displayLabel: string,
  ) {
    this.setData({
      timeError: validateTimes(dateValue, startTimeValue, endDateValue, endTimeValue),
      displayLabelError: validateDisplayLabel(displayLabel),
      formCanSubmit: isFormValid(
        dateValue,
        startTimeValue,
        endDateValue,
        endTimeValue,
        displayLabel,
      ),
      errorMessage: "",
    });
  },

  onDateChange(event: WechatMiniprogram.PickerChange) {
    const dateValue = String(event.detail.value);
    const endDateValue =
      this.data.endTimeValue && this.data.endDateValue === this.data.dateValue
        ? dateValue
        : this.data.endDateValue;
    this.setData({ dateValue, endDateValue });
    this.updateValidation(
      dateValue,
      this.data.startTimeValue,
      endDateValue,
      this.data.endTimeValue,
      this.data.displayLabel,
    );
  },

  onStartTimeChange(event: WechatMiniprogram.PickerChange) {
    const startTimeValue = String(event.detail.value);
    this.setData({ startTimeValue });
    this.updateValidation(
      this.data.dateValue,
      startTimeValue,
      this.data.endDateValue,
      this.data.endTimeValue,
      this.data.displayLabel,
    );
  },

  onEndTimeChange(event: WechatMiniprogram.PickerChange) {
    const endTimeValue = String(event.detail.value);
    const endDateValue = this.data.endDateValue || this.data.dateValue;
    this.setData({ endDateValue, endTimeValue });
    this.updateValidation(
      this.data.dateValue,
      this.data.startTimeValue,
      endDateValue,
      endTimeValue,
      this.data.displayLabel,
    );
  },

  onEndDateChange(event: WechatMiniprogram.PickerChange) {
    const endDateValue = String(event.detail.value);
    this.setData({ endDateValue });
    this.updateValidation(
      this.data.dateValue,
      this.data.startTimeValue,
      endDateValue,
      this.data.endTimeValue,
      this.data.displayLabel,
    );
  },

  onClearEndTime() {
    if (this.data.isSubmitting) {
      return;
    }
    this.setData({ endDateValue: "", endTimeValue: "" });
    this.updateValidation(
      this.data.dateValue,
      this.data.startTimeValue,
      "",
      "",
      this.data.displayLabel,
    );
  },

  onDisplayLabelInput(event: WechatMiniprogram.Input) {
    const displayLabel = event.detail.value;
    this.setData({
      displayLabel,
      displayLabelCount: countCharacters(displayLabel),
    });
    this.updateValidation(
      this.data.dateValue,
      this.data.startTimeValue,
      this.data.endDateValue,
      this.data.endTimeValue,
      displayLabel,
    );
  },

  onRetry() {
    void this.preparePage(true);
  },

  async onBack() {
    if (getCurrentPages().length > 1) {
      try {
        await navigateBack();
        return;
      } catch {
        // Fall through to a safe known page.
      }
    }
    await reLaunchToIndex();
  },

  detailUrl(): string {
    const query = [
      `group_id=${encodeURIComponent(this.data.groupId)}`,
      `hangout_id=${encodeURIComponent(this.data.hangoutId)}`,
    ].join("&");
    return `/pages/hangouts/detail/index?${query}`;
  },

  async returnToDetail() {
    if (getCurrentPages().length > 1) {
      try {
        await navigateBack();
        return;
      } catch {
        // Fall through when the opener is no longer available.
      }
    }
    await redirectTo(this.detailUrl());
  },

  async onSubmit() {
    if (this.data.isSubmitting || this.data.pageStatus !== "ready" || !this.data.formCanSubmit) {
      return;
    }

    const displayLabel = this.data.displayLabel.trim();
    const timeError = validateTimes(
      this.data.dateValue,
      this.data.startTimeValue,
      this.data.endDateValue,
      this.data.endTimeValue,
    );
    const displayLabelError = validateDisplayLabel(displayLabel);
    const startsAt = parseLocalDateTime(this.data.dateValue, this.data.startTimeValue);
    const endsAt = this.data.endTimeValue
      ? parseLocalDateTime(this.data.endDateValue, this.data.endTimeValue)
      : null;
    if (timeError || displayLabelError || !startsAt) {
      this.setData({ timeError, displayLabelError, formCanSubmit: false });
      return;
    }

    const input: TimeOptionWriteInput = {
      starts_at: startsAt.toISOString(),
      ends_at: endsAt?.toISOString() ?? null,
      display_label: displayLabel || null,
    };
    const submissionGeneration = formRequestGeneration;
    this.setData({ isSubmitting: true, errorMessage: "" });
    try {
      if (this.data.mode === "edit") {
        await updateTimeOption(
          this.data.groupId,
          this.data.hangoutId,
          this.data.timeOptionId,
          input,
        );
        wx.showToast({ title: "候选时间已更新", icon: "success" });
      } else {
        await createTimeOption(this.data.groupId, this.data.hangoutId, input);
        wx.showToast({ title: "候选时间已添加", icon: "success" });
      }
      await this.returnToDetail();
    } catch (error) {
      if (!pageAlive || submissionGeneration !== formRequestGeneration) {
        return;
      }
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }
      if (error instanceof ApiError) {
        if (error.code === 40940) {
          wx.showToast({ title: "约玩局状态已变化", icon: "none" });
          await this.returnToDetail();
          return;
        }
        if (error.code === 40410 || error.code === 40420 || error.code === 40440) {
          this.setData({
            pageStatus: "error",
            errorTitle: "候选时间不可用",
            errorMessage: "约玩局或候选时间已不可用，请安全返回详情页。",
            canRetry: false,
          });
          return;
        }
        if (error.code === 40340) {
          this.setData({ errorMessage: "你没有管理这个候选时间的权限。" });
          return;
        }
        if (error.code === 40001 || error.statusCode === 422) {
          this.setData({ errorMessage: "时间或展示标签不符合要求，请检查后重试。" });
          return;
        }
      }
      this.setData({
        errorMessage: getUserFacingError(error, "保存候选时间失败，请稍后重试"),
      });
    } finally {
      if (pageAlive && submissionGeneration === formRequestGeneration) {
        this.setData({ isSubmitting: false });
      }
    }
  },
});
