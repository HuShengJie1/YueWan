import { confirmEvent, getEvent } from "../../../services/event";
import { getGroup } from "../../../services/group";
import { getHangout } from "../../../services/hangout";
import { ApiError } from "../../../services/request";
import { getVotingSummary } from "../../../services/vote";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { HangoutEvent } from "../../../types/event";
import type { GroupDetail } from "../../../types/group";
import type { ProposalVotingSummary, TimeVotingSummary } from "../../../types/vote";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { buildHangoutView, formatLocalDateTime, type HangoutView } from "../../../utils/hangout";
import { reLaunchToIndex, reLaunchToLogin } from "../../../utils/navigation";
import { formatLocalDate, formatLocalTime } from "../../../utils/time-option";

type ConfirmPageStatus = "loading" | "error" | "ready";

interface ProposalResultView extends ProposalVotingSummary {
  descriptionText: string;
  locationText: string;
  isSelected: boolean;
}

interface TimeResultView extends TimeVotingSummary {
  localDateText: string;
  startTimeText: string;
  endDisplayText: string;
  displayLabelText: string;
  confirmationText: string;
  isSelected: boolean;
}

interface EventView extends HangoutEvent {
  locationText: string;
  startsAtText: string;
  endsAtText: string;
}

interface LoadPageOptions {
  forceAuth?: boolean;
  preserveContent?: boolean;
  preserveSelections?: boolean;
  notice?: string;
}

let pageAlive = false;
let pageHasShown = false;
let requestGeneration = 0;
let pageRequestActive = false;
let pageRefreshQueued = false;
let confirmFlowActive = false;

function buildProposalResultView(
  proposal: ProposalVotingSummary,
  selectedProposalId = "",
): ProposalResultView {
  return {
    ...proposal,
    descriptionText: proposal.description || "暂无补充描述",
    locationText: proposal.location_text || "地点待定",
    isSelected: proposal.id === selectedProposalId,
  };
}

function buildTimeResultView(
  timeOption: TimeVotingSummary,
  selectedTimeOptionId = "",
): TimeResultView {
  const localDateText = formatLocalDate(timeOption.starts_at);
  const startTimeText = formatLocalTime(timeOption.starts_at, "开始时间异常");
  const endTimeText = formatLocalTime(timeOption.ends_at, "未设置结束时间");
  const endDateText = timeOption.ends_at ? formatLocalDate(timeOption.ends_at) : "";
  const endDisplayText =
    timeOption.ends_at && endDateText !== localDateText
      ? `${endDateText} ${endTimeText}`
      : endTimeText;

  return {
    ...timeOption,
    localDateText,
    startTimeText,
    endDisplayText,
    displayLabelText: timeOption.display_label || "未设置展示标签",
    confirmationText: `${localDateText} ${startTimeText}${timeOption.ends_at ? `–${endDisplayText}` : ""}`,
    isSelected: timeOption.id === selectedTimeOptionId,
  };
}

function buildEventView(event: HangoutEvent): EventView {
  return {
    ...event,
    locationText: event.location_text || "地点待定",
    startsAtText: formatLocalDateTime(event.starts_at, "开始时间异常"),
    endsAtText: formatLocalDateTime(event.ends_at, "未设置结束时间"),
  };
}

function getPageLoadError(error: unknown): {
  title: string;
  message: string;
  canRetry: boolean;
} {
  if (error instanceof ApiError) {
    if (error.code === 40410 || error.code === 40420) {
      return {
        title: "无法查看约玩局",
        message: "约玩局不存在、已不可见，或你已不在该群组中。",
        canRetry: false,
      };
    }

    if (error.code === 40450) {
      return {
        title: "正式活动不可见",
        message: "约玩局已确认，但暂时无法读取对应 Event，请刷新后重试。",
        canRetry: true,
      };
    }
  }

  return {
    title: "确认页暂时加载失败",
    message: getUserFacingError(error, "无法读取投票结果，请稍后重试"),
    canRetry: true,
  };
}

function getOptionalEvent(groupId: string, hangoutId: string): Promise<HangoutEvent | null> {
  return getEvent(groupId, hangoutId).catch((error: unknown) => {
    if (error instanceof ApiError && error.code === 40450) {
      return null;
    }
    throw error;
  });
}

function showFinalConfirmation(
  proposal: ProposalResultView,
  timeOption: TimeResultView,
): Promise<boolean> {
  const content = [
    `活动：${proposal.title}`,
    `地点：${proposal.locationText}`,
    `时间：${timeOption.confirmationText}`,
  ].join("\n");

  return new Promise((resolve) => {
    wx.showModal({
      title: "确认正式活动",
      content,
      confirmText: "确认活动",
      confirmColor: "#176348",
      success: ({ confirm }) => resolve(confirm),
      fail: () => resolve(false),
    });
  });
}

Page({
  data: {
    pageStatus: "loading" as ConfirmPageStatus,
    groupId: "",
    hangoutId: "",
    group: null as GroupDetail | null,
    hangout: null as HangoutView | null,
    proposals: [] as ProposalResultView[],
    timeOptions: [] as TimeResultView[],
    selectedProposalId: "",
    selectedTimeOptionId: "",
    selectedProposal: null as ProposalResultView | null,
    selectedTimeOption: null as TimeResultView | null,
    confirmedEvent: null as EventView | null,
    canConfirm: false,
    canSubmit: false,
    isSubmitting: false,
    isRefreshing: false,
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    refreshError: "",
    noticeMessage: "",
    permissionMessage: "",
    statusMessage: "",
    submitErrorMessage: "",
  },

  onLoad(options: Record<string, string | undefined>) {
    pageAlive = true;
    pageHasShown = false;
    requestGeneration += 1;
    pageRequestActive = false;
    pageRefreshQueued = false;
    confirmFlowActive = false;

    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    if (!isValidGroupId(groupId) || !isValidUuid(hangoutId)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "确认链接无效",
        errorMessage: "这个链接缺少有效的群组或约玩局信息，请返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ groupId, hangoutId });
    void this.loadPageData();
  },

  onShow() {
    if (!pageHasShown) {
      pageHasShown = true;
      return;
    }
    if (this.data.pageStatus === "ready" && !this.data.isSubmitting) {
      void this.loadPageData({ preserveContent: true, preserveSelections: true });
    }
  },

  onUnload() {
    pageAlive = false;
    requestGeneration += 1;
    pageRequestActive = false;
    pageRefreshQueued = false;
    confirmFlowActive = false;
  },

  async loadPageData(options: LoadPageOptions = {}) {
    const {
      forceAuth = false,
      preserveContent = false,
      preserveSelections = false,
      notice = "",
    } = options;
    if (!pageAlive || !this.data.groupId || !this.data.hangoutId) {
      return;
    }
    if (pageRequestActive) {
      pageRefreshQueued = true;
      return;
    }

    pageRequestActive = true;
    const currentGeneration = ++requestGeneration;
    const canPreserve = preserveContent && this.data.pageStatus === "ready";
    const previousProposalId = preserveSelections ? this.data.selectedProposalId : "";
    const previousTimeOptionId = preserveSelections ? this.data.selectedTimeOptionId : "";
    this.setData({
      ...(canPreserve
        ? { isRefreshing: true }
        : {
            pageStatus: "loading" as ConfirmPageStatus,
            group: null,
            hangout: null,
            proposals: [],
            timeOptions: [],
            confirmedEvent: null,
          }),
      refreshError: "",
      errorMessage: "",
      submitErrorMessage: "",
      noticeMessage: notice,
    });

    try {
      const authState = await bootstrapAuth(forceAuth);
      if (!pageAlive || currentGeneration !== requestGeneration) {
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

      const [hangout, group, summary, event] = await Promise.all([
        getHangout(this.data.groupId, this.data.hangoutId),
        getGroup(this.data.groupId),
        getVotingSummary(this.data.groupId, this.data.hangoutId),
        getOptionalEvent(this.data.groupId, this.data.hangoutId),
      ]);
      if (!pageAlive || currentGeneration !== requestGeneration) {
        return;
      }
      if (summary.hangout_id !== hangout.id || hangout.id !== this.data.hangoutId) {
        throw new Error("投票信息与当前约玩局不匹配");
      }
      const effectiveStatus = event ? "confirmed" : summary.status;
      if (effectiveStatus === "confirmed" && !event) {
        throw new ApiError("Event not found", 404, 40450);
      }

      const hasPermission =
        hangout.created_by_user_id === authState.user.id || group.current_user_role === "owner";
      const canConfirm =
        hangout.status === "voting" && summary.status === "voting" && hasPermission && !event;
      const selectedProposalId = summary.proposals.some(
        (proposal) => proposal.id === previousProposalId,
      )
        ? previousProposalId
        : "";
      const selectedTimeOptionId = summary.time_options.some(
        (timeOption) => timeOption.id === previousTimeOptionId,
      )
        ? previousTimeOptionId
        : "";
      const proposals = summary.proposals.map((proposal) =>
        buildProposalResultView(proposal, canConfirm ? selectedProposalId : ""),
      );
      const timeOptions = summary.time_options.map((timeOption) =>
        buildTimeResultView(timeOption, canConfirm ? selectedTimeOptionId : ""),
      );
      const selectedProposal =
        proposals.find((proposal) => proposal.id === selectedProposalId) ?? null;
      const selectedTimeOption =
        timeOptions.find((timeOption) => timeOption.id === selectedTimeOptionId) ?? null;

      this.setData({
        pageStatus: "ready",
        group,
        hangout: buildHangoutView({
          ...hangout,
          status: effectiveStatus,
          voting_deadline: summary.voting_deadline,
        }),
        proposals,
        timeOptions,
        selectedProposalId: canConfirm ? selectedProposalId : "",
        selectedTimeOptionId: canConfirm ? selectedTimeOptionId : "",
        selectedProposal: canConfirm ? selectedProposal : null,
        selectedTimeOption: canConfirm ? selectedTimeOption : null,
        confirmedEvent: event ? buildEventView(event) : null,
        canConfirm,
        canSubmit: canConfirm && Boolean(selectedProposal && selectedTimeOption),
        isRefreshing: false,
        permissionMessage:
          effectiveStatus === "voting" && !hasPermission
            ? "只有约玩局创建者或群主可以确认正式活动。"
            : "",
        statusMessage:
          effectiveStatus === "confirmed"
            ? "这场约玩已由负责人确认，下面展示服务端保存的正式活动。"
            : effectiveStatus !== "voting"
              ? "当前约玩局状态已不能确认活动。"
              : "",
      });
      wx.setNavigationBarTitle({ title: `确认 · ${hangout.title}` });
    } catch (error) {
      if (!pageAlive || currentGeneration !== requestGeneration) {
        return;
      }
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getPageLoadError(error);
      if (canPreserve && loadError.canRetry) {
        this.setData({
          isRefreshing: false,
          refreshError: loadError.message,
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
      if (currentGeneration === requestGeneration) {
        pageRequestActive = false;
        if (pageRefreshQueued && pageAlive) {
          pageRefreshQueued = false;
          void this.loadPageData({ preserveContent: true, preserveSelections: true });
        }
      }
    }
  },

  onProposalTap(event: WechatMiniprogram.TouchEvent) {
    const proposalId = String(event.currentTarget.dataset.proposalId ?? "");
    if (
      !this.data.canConfirm ||
      this.data.isSubmitting ||
      this.data.isRefreshing ||
      pageRequestActive ||
      confirmFlowActive
    ) {
      return;
    }
    const selectedProposal = this.data.proposals.find((proposal) => proposal.id === proposalId);
    if (!selectedProposal) {
      return;
    }

    this.setData({
      selectedProposalId: proposalId,
      selectedProposal: { ...selectedProposal, isSelected: true },
      proposals: this.data.proposals.map((proposal) => ({
        ...proposal,
        isSelected: proposal.id === proposalId,
      })),
      canSubmit: Boolean(this.data.selectedTimeOptionId),
      submitErrorMessage: "",
    });
  },

  onTimeOptionTap(event: WechatMiniprogram.TouchEvent) {
    const timeOptionId = String(event.currentTarget.dataset.timeOptionId ?? "");
    if (
      !this.data.canConfirm ||
      this.data.isSubmitting ||
      this.data.isRefreshing ||
      pageRequestActive ||
      confirmFlowActive
    ) {
      return;
    }
    const selectedTimeOption = this.data.timeOptions.find(
      (timeOption) => timeOption.id === timeOptionId,
    );
    if (!selectedTimeOption) {
      return;
    }

    this.setData({
      selectedTimeOptionId: timeOptionId,
      selectedTimeOption: { ...selectedTimeOption, isSelected: true },
      timeOptions: this.data.timeOptions.map((timeOption) => ({
        ...timeOption,
        isSelected: timeOption.id === timeOptionId,
      })),
      canSubmit: Boolean(this.data.selectedProposalId),
      submitErrorMessage: "",
    });
  },

  async onConfirmTap() {
    if (
      confirmFlowActive ||
      pageRequestActive ||
      this.data.isSubmitting ||
      this.data.isRefreshing ||
      !this.data.canSubmit ||
      !this.data.canConfirm ||
      !this.data.selectedProposal ||
      !this.data.selectedTimeOption
    ) {
      return;
    }

    confirmFlowActive = true;
    const proposal = this.data.selectedProposal;
    const timeOption = this.data.selectedTimeOption;
    const accepted = await showFinalConfirmation(proposal, timeOption);
    if (!accepted || !pageAlive) {
      confirmFlowActive = false;
      return;
    }

    this.setData({ isSubmitting: true, submitErrorMessage: "" });
    try {
      await confirmEvent(this.data.groupId, this.data.hangoutId, {
        proposal_id: proposal.id,
        time_option_id: timeOption.id,
      });
      if (!pageAlive) {
        return;
      }

      wx.showToast({ title: "正式活动已确认", icon: "success" });
      this.onBack();
    } catch (error) {
      if (!pageAlive) {
        return;
      }
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      if (error instanceof ApiError && (error.code === 40350 || error.statusCode === 403)) {
        this.setData({ canConfirm: false, canSubmit: false });
        wx.showToast({ title: "没有确认权限，正在刷新", icon: "none" });
        await this.loadPageData({
          preserveContent: true,
          notice: "确认权限已变化，已重新读取群组权限。",
        });
        return;
      }

      if (error instanceof ApiError && (error.code === 40410 || error.code === 40420)) {
        this.setData({ canConfirm: false, canSubmit: false });
        wx.showToast({ title: "约玩局已不可见", icon: "none" });
        await this.loadPageData({
          preserveContent: true,
          notice: "约玩局或 Event 已不可见。",
        });
        return;
      }

      if (error instanceof ApiError && (error.code === 40430 || error.code === 40440)) {
        this.setData({ canConfirm: false, canSubmit: false });
        wx.showToast({ title: "候选项已变化，正在刷新", icon: "none" });
        await this.loadPageData({
          preserveContent: true,
          notice: "活动或时间候选已变化，请根据最新结果重新选择。",
        });
        return;
      }

      if (error instanceof ApiError && error.statusCode === 409) {
        this.setData({ canConfirm: false, canSubmit: false });
        wx.showToast({ title: "状态已变化，正在刷新", icon: "none" });
        await this.loadPageData({
          preserveContent: true,
          notice: "约玩局状态已变化，已加载服务端最新 Hangout、票数和 Event。",
        });
        return;
      }

      this.setData({
        submitErrorMessage: getUserFacingError(error, "确认失败，请检查网络后重新核对并提交"),
      });
    } finally {
      confirmFlowActive = false;
      if (pageAlive) {
        this.setData({ isSubmitting: false });
      }
    }
  },

  onRetry() {
    void this.loadPageData({ forceAuth: true });
  },

  onRefreshRetry() {
    void this.loadPageData({ preserveContent: true, preserveSelections: true });
  },

  async onPullDownRefresh() {
    if (this.data.isSubmitting || confirmFlowActive) {
      wx.stopPullDownRefresh();
      return;
    }
    try {
      await this.loadPageData({ preserveContent: true, preserveSelections: true });
    } finally {
      if (pageAlive) {
        wx.stopPullDownRefresh();
      }
    }
  },

  onBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack();
      return;
    }

    if (!isValidGroupId(this.data.groupId) || !isValidUuid(this.data.hangoutId)) {
      void reLaunchToIndex();
      return;
    }

    const query = [
      `group_id=${encodeURIComponent(this.data.groupId)}`,
      `hangout_id=${encodeURIComponent(this.data.hangoutId)}`,
    ].join("&");
    wx.redirectTo({
      url: `/pages/hangouts/detail/index?${query}`,
      fail: () => {
        void reLaunchToIndex();
      },
    });
  },
});
