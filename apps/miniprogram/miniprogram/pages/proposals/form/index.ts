import { createProposal, updateProposal } from "../../../services/proposal";
import { ApiError } from "../../../services/request";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { Proposal, ProposalWriteInput } from "../../../types/proposal";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { reLaunchToIndex, reLaunchToLogin } from "../../../utils/navigation";

type FormMode = "create" | "edit";
type FormPageStatus = "loading" | "error" | "ready";

const TITLE_MAX_LENGTH = 80;
const DESCRIPTION_MAX_LENGTH = 500;
const LOCATION_MAX_LENGTH = 200;
const PLATFORM_MAX_LENGTH = 50;
const URL_MAX_LENGTH = 2048;

let pageAlive = false;
let formRequestGeneration = 0;
let editingProposal: Proposal | null = null;
let editDataPromise: Promise<Proposal | null> | null = null;
let resolveEditData: ((proposal: Proposal | null) => void) | null = null;
let editDataTimer: ReturnType<typeof setTimeout> | null = null;

function countCharacters(value: string): number {
  return Array.from(value).length;
}

function validateTitle(value: string): string {
  const title = value.trim();
  if (!title) {
    return "请填写候选活动标题";
  }
  return countCharacters(title) > TITLE_MAX_LENGTH ? `标题不能超过 ${TITLE_MAX_LENGTH} 个字符` : "";
}

function validateOptionalText(value: string, maxLength: number, label: string): string {
  return countCharacters(value.trim()) > maxLength ? `${label}不能超过 ${maxLength} 个字符` : "";
}

function validateExternalUrl(value: string): string {
  const externalUrl = value.trim();
  if (!externalUrl) {
    return "";
  }

  if (countCharacters(externalUrl) > URL_MAX_LENGTH) {
    return `外部链接不能超过 ${URL_MAX_LENGTH} 个字符`;
  }

  const authorityMatch = /^https?:\/\/([^/?#]+)(?:[/?#]|$)/i.exec(externalUrl);
  if (!authorityMatch || /\s/.test(externalUrl)) {
    return "请输入带网站地址的 HTTP/HTTPS 链接";
  }

  const authority = authorityMatch[1];
  if (authority.includes("@") || authority === ":" || authority.startsWith(":")) {
    return "外部链接不能包含用户名或密码";
  }

  return "";
}

function isFormValid(
  title: string,
  description: string,
  locationText: string,
  externalPlatform: string,
  externalUrl: string,
): boolean {
  return (
    !validateTitle(title) &&
    !validateOptionalText(description, DESCRIPTION_MAX_LENGTH, "描述") &&
    !validateOptionalText(locationText, LOCATION_MAX_LENGTH, "地点") &&
    !validateOptionalText(externalPlatform, PLATFORM_MAX_LENGTH, "平台名称") &&
    !validateExternalUrl(externalUrl)
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

function isProposal(value: unknown): value is Proposal {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const proposal = value as Partial<Proposal>;
  return (
    typeof proposal.id === "string" &&
    typeof proposal.hangout_id === "string" &&
    typeof proposal.title === "string" &&
    typeof proposal.can_manage === "boolean"
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
  eventChannel.on("proposalEditData", (value: unknown) => {
    if (editDataTimer) {
      clearTimeout(editDataTimer);
      editDataTimer = null;
    }
    editingProposal = isProposal(value) ? value : null;
    resolveEditData?.(editingProposal);
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
    proposalId: "",
    title: "",
    description: "",
    locationText: "",
    externalPlatform: "",
    externalUrl: "",
    titleCount: 0,
    descriptionCount: 0,
    locationCount: 0,
    platformCount: 0,
    urlCount: 0,
    titleError: "",
    descriptionError: "",
    locationError: "",
    platformError: "",
    urlError: "",
    formCanSubmit: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    isSubmitting: false,
  },

  onLoad(options: Record<string, string | undefined>) {
    pageAlive = true;
    formRequestGeneration += 1;
    editingProposal = null;
    editDataPromise = null;
    resolveEditData = null;
    if (editDataTimer) {
      clearTimeout(editDataTimer);
      editDataTimer = null;
    }

    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    const proposalId = options.proposal_id?.trim() ?? "";
    const modeValue = options.mode?.trim() ?? "create";
    const mode: FormMode = modeValue === "edit" ? "edit" : "create";
    const invalidMode = modeValue !== "create" && modeValue !== "edit";
    const invalidProposalId = mode === "edit" ? !isValidUuid(proposalId) : Boolean(proposalId);

    if (!isValidGroupId(groupId) || !isValidUuid(hangoutId) || invalidMode || invalidProposalId) {
      this.setData({
        pageStatus: "error",
        errorTitle: "页面链接无效",
        errorMessage: "这个链接缺少有效的约玩局或候选活动信息，请安全返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    if (mode === "edit") {
      prepareEditDataChannel(this);
    }
    this.setData({ mode, groupId, hangoutId, proposalId });
    wx.setNavigationBarTitle({ title: mode === "edit" ? "编辑候选活动" : "添加候选活动" });
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
    editingProposal = null;
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
        const proposal = editingProposal ?? (await editDataPromise);
        if (!pageAlive || requestGeneration !== formRequestGeneration) {
          return;
        }
        if (
          !proposal ||
          proposal.id !== this.data.proposalId ||
          proposal.hangout_id !== this.data.hangoutId ||
          !proposal.can_manage
        ) {
          this.setData({
            pageStatus: "error",
            errorTitle: "候选活动不可用",
            errorMessage: "候选活动已变化或无法编辑，请返回详情页重新进入。",
            canRetry: false,
          });
          return;
        }
        this.fillForm(proposal);
        return;
      }

      this.setData({ pageStatus: "ready", formCanSubmit: false });
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
        errorMessage: getUserFacingError(error, "无法准备候选活动表单，请稍后重试"),
        canRetry: true,
      });
    }
  },

  fillForm(proposal: Proposal) {
    editingProposal = proposal;
    const title = proposal.title;
    const description = proposal.description ?? "";
    const locationText = proposal.location_text ?? "";
    const externalPlatform = proposal.external_platform ?? "";
    const externalUrl = proposal.external_url ?? "";
    this.setData({
      pageStatus: "ready",
      title,
      description,
      locationText,
      externalPlatform,
      externalUrl,
      titleCount: countCharacters(title),
      descriptionCount: countCharacters(description),
      locationCount: countCharacters(locationText),
      platformCount: countCharacters(externalPlatform),
      urlCount: countCharacters(externalUrl),
      formCanSubmit: isFormValid(title, description, locationText, externalPlatform, externalUrl),
    });
  },

  updateValidation(
    next: Partial<
      Record<"title" | "description" | "locationText" | "externalPlatform" | "externalUrl", string>
    >,
  ) {
    const title = next.title ?? this.data.title;
    const description = next.description ?? this.data.description;
    const locationText = next.locationText ?? this.data.locationText;
    const externalPlatform = next.externalPlatform ?? this.data.externalPlatform;
    const externalUrl = next.externalUrl ?? this.data.externalUrl;
    this.setData({
      formCanSubmit: isFormValid(title, description, locationText, externalPlatform, externalUrl),
      errorMessage: "",
    });
  },

  onTitleInput(event: WechatMiniprogram.Input) {
    const title = event.detail.value;
    this.setData({
      title,
      titleCount: countCharacters(title),
      titleError: validateTitle(title),
    });
    this.updateValidation({ title });
  },

  onDescriptionInput(event: WechatMiniprogram.TextareaInput) {
    const description = event.detail.value;
    this.setData({
      description,
      descriptionCount: countCharacters(description),
      descriptionError: validateOptionalText(description, DESCRIPTION_MAX_LENGTH, "描述"),
    });
    this.updateValidation({ description });
  },

  onLocationInput(event: WechatMiniprogram.Input) {
    const locationText = event.detail.value;
    this.setData({
      locationText,
      locationCount: countCharacters(locationText),
      locationError: validateOptionalText(locationText, LOCATION_MAX_LENGTH, "地点"),
    });
    this.updateValidation({ locationText });
  },

  onPlatformInput(event: WechatMiniprogram.Input) {
    const externalPlatform = event.detail.value;
    this.setData({
      externalPlatform,
      platformCount: countCharacters(externalPlatform),
      platformError: validateOptionalText(externalPlatform, PLATFORM_MAX_LENGTH, "平台名称"),
    });
    this.updateValidation({ externalPlatform });
  },

  onUrlInput(event: WechatMiniprogram.Input) {
    const externalUrl = event.detail.value;
    this.setData({
      externalUrl,
      urlCount: countCharacters(externalUrl),
      urlError: validateExternalUrl(externalUrl),
    });
    this.updateValidation({ externalUrl });
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

    const title = this.data.title.trim();
    const description = this.data.description.trim();
    const locationText = this.data.locationText.trim();
    const externalPlatform = this.data.externalPlatform.trim();
    const externalUrl = this.data.externalUrl.trim();
    const titleError = validateTitle(title);
    const descriptionError = validateOptionalText(description, DESCRIPTION_MAX_LENGTH, "描述");
    const locationError = validateOptionalText(locationText, LOCATION_MAX_LENGTH, "地点");
    const platformError = validateOptionalText(externalPlatform, PLATFORM_MAX_LENGTH, "平台名称");
    const urlError = validateExternalUrl(externalUrl);
    if (titleError || descriptionError || locationError || platformError || urlError) {
      this.setData({
        titleError,
        descriptionError,
        locationError,
        platformError,
        urlError,
        formCanSubmit: false,
      });
      return;
    }

    const input: ProposalWriteInput = {
      title,
      description: description || null,
      location_text: locationText || null,
      external_platform: externalPlatform || null,
      external_url: externalUrl || null,
      external_data: editingProposal?.external_data ?? null,
    };
    const submissionGeneration = formRequestGeneration;
    this.setData({ isSubmitting: true, errorMessage: "" });
    try {
      if (this.data.mode === "edit") {
        await updateProposal(this.data.groupId, this.data.hangoutId, this.data.proposalId, input);
        wx.showToast({ title: "候选活动已更新", icon: "success" });
      } else {
        await createProposal(this.data.groupId, this.data.hangoutId, input);
        wx.showToast({ title: "候选活动已添加", icon: "success" });
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
        if (error.code === 40930) {
          wx.showToast({ title: "约玩局状态已变化", icon: "none" });
          await this.returnToDetail();
          return;
        }
        if (error.code === 40410 || error.code === 40420 || error.code === 40430) {
          this.setData({
            pageStatus: "error",
            errorTitle: "候选活动不可用",
            errorMessage: "约玩局或候选活动已不可用，请安全返回详情页。",
            canRetry: false,
          });
          return;
        }
        if (error.code === 40330) {
          this.setData({ errorMessage: "你没有管理这个候选活动的权限。" });
          return;
        }
        if (error.code === 40001) {
          this.setData({ errorMessage: "表单内容不符合要求，请检查后重试。" });
          return;
        }
      }
      this.setData({
        errorMessage: getUserFacingError(error, "保存候选活动失败，请稍后重试"),
      });
    } finally {
      if (pageAlive && submissionGeneration === formRequestGeneration) {
        this.setData({ isSubmitting: false });
      }
    }
  },
});
