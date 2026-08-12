import { getGroup } from "../../../services/group";
import { getHangout } from "../../../services/hangout";
import { deleteProposal, listProposals } from "../../../services/proposal";
import { ApiError } from "../../../services/request";
import { deleteTimeOption, listTimeOptions } from "../../../services/time-option";
import { bootstrapAuth, getAuthState } from "../../../stores/auth";
import type { GroupDetail } from "../../../types/group";
import type { Proposal } from "../../../types/proposal";
import type { TimeOption } from "../../../types/time-option";
import { getUserFacingError } from "../../../utils/errors";
import { isValidGroupId, isValidUuid } from "../../../utils/group";
import { buildHangoutView, formatLocalDateTime, type HangoutView } from "../../../utils/hangout";
import { reLaunchToIndex, reLaunchToLogin } from "../../../utils/navigation";
import { formatLocalDate, formatLocalTime } from "../../../utils/time-option";

type DetailPageStatus = "loading" | "error" | "ready";
type CandidateSectionStatus = "loading" | "empty" | "error" | "ready";
type RefreshSection = "" | "proposal" | "time-option" | "all";

interface ProposalView extends Proposal {
  descriptionSummary: string;
  locationText: string;
  externalLinkText: string;
  createdAtText: string;
}

interface TimeOptionView extends TimeOption {
  localDateText: string;
  startTimeText: string;
  endTimeText: string;
  endDisplayText: string;
  displayLabelText: string;
  confirmationText: string;
}

interface CandidateLoadError {
  message: string;
  canRetry: boolean;
  parentUnavailable: boolean;
}

const PAGE_LIMIT = 20;
const requestedProposalCursors = new Set<string>();
const requestedTimeOptionCursors = new Set<string>();

let pageAlive = false;
let detailRequestGeneration = 0;
let proposalRequestGeneration = 0;
let timeOptionRequestGeneration = 0;
let detailRequestActive = false;
let proposalRequestActive = false;
let timeOptionRequestActive = false;
let detailRefreshQueued = false;
let proposalRefreshQueued = false;
let timeOptionRefreshQueued = false;

function buildProposalView(proposal: Proposal): ProposalView {
  const platform = proposal.external_platform?.trim();
  return {
    ...proposal,
    descriptionSummary: proposal.description || "暂无补充描述",
    locationText: proposal.location_text || "地点待定",
    externalLinkText: proposal.external_url
      ? platform
        ? `含 ${platform} 外部链接`
        : "含外部链接"
      : "",
    createdAtText: `提交于 ${formatLocalDateTime(proposal.created_at, "未知时间")}`,
  };
}

function buildTimeOptionView(timeOption: TimeOption): TimeOptionView {
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
    endTimeText,
    endDisplayText,
    displayLabelText: timeOption.display_label || "未设置展示标签",
    confirmationText: `${localDateText} ${startTimeText}${timeOption.ends_at ? `–${endDisplayText}` : ""}`,
  };
}

function mergeUniqueProposals(current: ProposalView[], incoming: Proposal[]): ProposalView[] {
  const proposalsById = new Map(current.map((proposal) => [proposal.id, proposal]));
  incoming.forEach((proposal) => proposalsById.set(proposal.id, buildProposalView(proposal)));
  return [...proposalsById.values()];
}

function mergeUniqueTimeOptions(
  current: TimeOptionView[],
  incoming: TimeOption[],
): TimeOptionView[] {
  const optionsById = new Map(current.map((timeOption) => [timeOption.id, timeOption]));
  incoming.forEach((timeOption) => optionsById.set(timeOption.id, buildTimeOptionView(timeOption)));
  return [...optionsById.values()];
}

function navigateTo(url: string, eventName?: string, payload?: unknown): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.navigateTo({
      url,
      success: ({ eventChannel }) => {
        if (eventName) {
          eventChannel.emit(eventName, payload);
        }
        resolve();
      },
      fail: ({ errMsg }) => reject(new Error(errMsg)),
    });
  });
}

function confirmDelete(title: string, content: string): Promise<boolean> {
  return new Promise((resolve) => {
    wx.showModal({
      title,
      content,
      confirmText: "删除",
      confirmColor: "#b54b43",
      success: ({ confirm }) => resolve(confirm),
      fail: () => resolve(false),
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
      title: "无法查看约玩局",
      message: "约玩局不存在或无权查看，请返回后重新进入。",
      canRetry: false,
    };
  }

  return {
    title: "约玩局暂时加载失败",
    message: getUserFacingError(error, "无法读取约玩局，请稍后重试"),
    canRetry: true,
  };
}

function getCandidateLoadError(error: unknown, resourceName: string): CandidateLoadError {
  if (error instanceof ApiError) {
    if (error.code === 40410 || error.code === 40420) {
      return {
        message: "约玩局已不可用，请返回后重新进入。",
        canRetry: false,
        parentUnavailable: true,
      };
    }

    if (error.code === 40430 || error.code === 40440) {
      return {
        message: `${resourceName}已不可用，请重新加载。`,
        canRetry: true,
        parentUnavailable: false,
      };
    }

    if (error.code === 42213) {
      return {
        message: "列表位置已失效，请重新加载。",
        canRetry: true,
        parentUnavailable: false,
      };
    }
  }

  return {
    message: getUserFacingError(error, `${resourceName}加载失败，请稍后重试`),
    canRetry: true,
    parentUnavailable: false,
  };
}

Page({
  data: {
    pageStatus: "loading" as DetailPageStatus,
    groupId: "",
    hangoutId: "",
    group: null as GroupDetail | null,
    hangout: null as HangoutView | null,
    canEdit: false,
    isDetailRefreshing: false,
    detailRefreshError: "",
    errorTitle: "",
    errorMessage: "",
    canRetry: true,
    proposalStatus: "loading" as CandidateSectionStatus,
    proposals: [] as ProposalView[],
    nextProposalCursor: null as string | null,
    hasMoreProposals: false,
    isRefreshingProposals: false,
    isLoadingMoreProposals: false,
    proposalErrorMessage: "",
    proposalRefreshError: "",
    proposalLoadMoreError: "",
    proposalCursorInvalid: false,
    timeOptionStatus: "loading" as CandidateSectionStatus,
    timeOptions: [] as TimeOptionView[],
    nextTimeOptionCursor: null as string | null,
    hasMoreTimeOptions: false,
    isRefreshingTimeOptions: false,
    isLoadingMoreTimeOptions: false,
    timeOptionErrorMessage: "",
    timeOptionRefreshError: "",
    timeOptionLoadMoreError: "",
    timeOptionCursorInvalid: false,
    isNavigating: false,
    pendingRefreshSection: "" as RefreshSection,
    deletingCandidateId: "",
    deletingCandidateType: "" as "" | "proposal" | "time-option",
  },

  onLoad(options: Record<string, string | undefined>) {
    pageAlive = true;
    detailRequestGeneration += 1;
    proposalRequestGeneration += 1;
    timeOptionRequestGeneration += 1;
    detailRequestActive = false;
    proposalRequestActive = false;
    timeOptionRequestActive = false;
    detailRefreshQueued = false;
    proposalRefreshQueued = false;
    timeOptionRefreshQueued = false;
    requestedProposalCursors.clear();
    requestedTimeOptionCursors.clear();

    const groupId = options.group_id?.trim() ?? "";
    const hangoutId = options.hangout_id?.trim() ?? "";
    if (!isValidGroupId(groupId) || !isValidUuid(hangoutId)) {
      this.setData({
        pageStatus: "error",
        errorTitle: "约玩局链接无效",
        errorMessage: "这个链接缺少有效的群组或约玩局信息，请返回后重新进入。",
        canRetry: false,
      });
      return;
    }

    this.setData({ groupId, hangoutId });
    void this.loadDetail();
  },

  onShow() {
    if (this.data.pageStatus !== "ready" || !this.data.groupId) {
      return;
    }

    const refreshSection = this.data.pendingRefreshSection;
    this.setData({ isNavigating: false, pendingRefreshSection: "" });
    void this.loadDetail(false, true);
    if (refreshSection === "proposal") {
      void this.loadProposals(false, true);
    } else if (refreshSection === "time-option") {
      void this.loadTimeOptions(false, true);
    } else {
      void this.loadProposals(false, true);
      void this.loadTimeOptions(false, true);
    }
  },

  onUnload() {
    pageAlive = false;
    detailRequestGeneration += 1;
    proposalRequestGeneration += 1;
    timeOptionRequestGeneration += 1;
    detailRequestActive = false;
    proposalRequestActive = false;
    timeOptionRequestActive = false;
    detailRefreshQueued = false;
    proposalRefreshQueued = false;
    timeOptionRefreshQueued = false;
    requestedProposalCursors.clear();
    requestedTimeOptionCursors.clear();
  },

  async loadDetail(forceAuth = false, preserveContent = false) {
    if (!pageAlive || !this.data.groupId || !this.data.hangoutId) {
      return;
    }
    if (detailRequestActive) {
      detailRefreshQueued = detailRefreshQueued || preserveContent;
      return;
    }

    detailRequestActive = true;
    const requestGeneration = ++detailRequestGeneration;
    const canPreserve = preserveContent && Boolean(this.data.hangout && this.data.group);
    this.setData({
      ...(canPreserve
        ? { isDetailRefreshing: true }
        : {
            pageStatus: "loading" as DetailPageStatus,
            group: null,
            hangout: null,
            canEdit: false,
            proposalStatus: "loading" as CandidateSectionStatus,
            proposals: [],
            timeOptionStatus: "loading" as CandidateSectionStatus,
            timeOptions: [],
          }),
      detailRefreshError: "",
      errorMessage: "",
    });

    try {
      const authState = await bootstrapAuth(forceAuth);
      if (!pageAlive || requestGeneration !== detailRequestGeneration) {
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

      const [hangout, group] = await Promise.all([
        getHangout(this.data.groupId, this.data.hangoutId),
        getGroup(this.data.groupId),
      ]);
      if (!pageAlive || requestGeneration !== detailRequestGeneration) {
        return;
      }

      const canEdit =
        hangout.status === "draft" &&
        (hangout.created_by_user_id === authState.user.id || group.current_user_role === "owner");
      this.setData({
        pageStatus: "ready",
        group,
        hangout: buildHangoutView(hangout),
        canEdit,
        isDetailRefreshing: false,
      });
      wx.setNavigationBarTitle({ title: hangout.title });

      if (!canPreserve) {
        void this.loadProposals();
        void this.loadTimeOptions();
      }
    } catch (error) {
      if (!pageAlive || requestGeneration !== detailRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getLoadError(error);
      if (canPreserve && loadError.canRetry) {
        this.setData({
          pageStatus: "ready",
          isDetailRefreshing: false,
          detailRefreshError: loadError.message,
        });
      } else {
        this.setData({
          pageStatus: "error",
          isDetailRefreshing: false,
          errorTitle: loadError.title,
          errorMessage: loadError.message,
          canRetry: loadError.canRetry,
        });
      }
    } finally {
      if (requestGeneration === detailRequestGeneration) {
        detailRequestActive = false;
        if (detailRefreshQueued && pageAlive) {
          detailRefreshQueued = false;
          void this.loadDetail(false, true);
        }
      }
    }
  },

  async loadProposals(forceAuth = false, preserveContent = false) {
    if (!pageAlive || !this.data.groupId || !this.data.hangoutId) {
      return;
    }
    if (proposalRequestActive) {
      proposalRefreshQueued = proposalRefreshQueued || preserveContent;
      return;
    }

    proposalRequestActive = true;
    const requestGeneration = ++proposalRequestGeneration;
    const canPreserve = preserveContent && this.data.proposals.length > 0;
    requestedProposalCursors.clear();
    this.setData({
      ...(canPreserve
        ? { isRefreshingProposals: true }
        : {
            proposalStatus: "loading" as CandidateSectionStatus,
            proposals: [],
            nextProposalCursor: null,
            hasMoreProposals: false,
          }),
      proposalErrorMessage: "",
      proposalRefreshError: "",
      proposalLoadMoreError: "",
      proposalCursorInvalid: false,
      isLoadingMoreProposals: false,
    });

    try {
      if (forceAuth) {
        const authState = await bootstrapAuth(true);
        if (authState.status === "unauthenticated" || !authState.user) {
          await reLaunchToLogin(authState.errorMessage ? "expired" : undefined);
          return;
        }
      }

      const page = await listProposals(this.data.groupId, this.data.hangoutId, {
        limit: PAGE_LIMIT,
      });
      if (!pageAlive || requestGeneration !== proposalRequestGeneration) {
        return;
      }

      const proposals = mergeUniqueProposals([], page.items);
      const nextCursor = page.next_cursor;
      this.setData({
        proposalStatus: proposals.length > 0 ? "ready" : "empty",
        proposals,
        nextProposalCursor: nextCursor,
        hasMoreProposals: page.has_more && Boolean(nextCursor),
        isRefreshingProposals: false,
      });
    } catch (error) {
      if (!pageAlive || requestGeneration !== proposalRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getCandidateLoadError(error, "候选活动");
      if (canPreserve && loadError.canRetry) {
        this.setData({
          proposalStatus: "ready",
          isRefreshingProposals: false,
          proposalRefreshError: loadError.message,
        });
      } else {
        this.setData({
          proposalStatus: "error",
          isRefreshingProposals: false,
          proposalErrorMessage: loadError.message,
        });
      }

      if (loadError.parentUnavailable) {
        void this.loadDetail(false, true);
      }
    } finally {
      if (requestGeneration === proposalRequestGeneration) {
        proposalRequestActive = false;
        if (proposalRefreshQueued && pageAlive) {
          proposalRefreshQueued = false;
          void this.loadProposals(false, true);
        }
      }
    }
  },

  async loadTimeOptions(forceAuth = false, preserveContent = false) {
    if (!pageAlive || !this.data.groupId || !this.data.hangoutId) {
      return;
    }
    if (timeOptionRequestActive) {
      timeOptionRefreshQueued = timeOptionRefreshQueued || preserveContent;
      return;
    }

    timeOptionRequestActive = true;
    const requestGeneration = ++timeOptionRequestGeneration;
    const canPreserve = preserveContent && this.data.timeOptions.length > 0;
    requestedTimeOptionCursors.clear();
    this.setData({
      ...(canPreserve
        ? { isRefreshingTimeOptions: true }
        : {
            timeOptionStatus: "loading" as CandidateSectionStatus,
            timeOptions: [],
            nextTimeOptionCursor: null,
            hasMoreTimeOptions: false,
          }),
      timeOptionErrorMessage: "",
      timeOptionRefreshError: "",
      timeOptionLoadMoreError: "",
      timeOptionCursorInvalid: false,
      isLoadingMoreTimeOptions: false,
    });

    try {
      if (forceAuth) {
        const authState = await bootstrapAuth(true);
        if (authState.status === "unauthenticated" || !authState.user) {
          await reLaunchToLogin(authState.errorMessage ? "expired" : undefined);
          return;
        }
      }

      const page = await listTimeOptions(this.data.groupId, this.data.hangoutId, {
        limit: PAGE_LIMIT,
      });
      if (!pageAlive || requestGeneration !== timeOptionRequestGeneration) {
        return;
      }

      const timeOptions = mergeUniqueTimeOptions([], page.items);
      const nextCursor = page.next_cursor;
      this.setData({
        timeOptionStatus: timeOptions.length > 0 ? "ready" : "empty",
        timeOptions,
        nextTimeOptionCursor: nextCursor,
        hasMoreTimeOptions: page.has_more && Boolean(nextCursor),
        isRefreshingTimeOptions: false,
      });
    } catch (error) {
      if (!pageAlive || requestGeneration !== timeOptionRequestGeneration) {
        return;
      }

      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const loadError = getCandidateLoadError(error, "候选时间");
      if (canPreserve && loadError.canRetry) {
        this.setData({
          timeOptionStatus: "ready",
          isRefreshingTimeOptions: false,
          timeOptionRefreshError: loadError.message,
        });
      } else {
        this.setData({
          timeOptionStatus: "error",
          isRefreshingTimeOptions: false,
          timeOptionErrorMessage: loadError.message,
        });
      }

      if (loadError.parentUnavailable) {
        void this.loadDetail(false, true);
      }
    } finally {
      if (requestGeneration === timeOptionRequestGeneration) {
        timeOptionRequestActive = false;
        if (timeOptionRefreshQueued && pageAlive) {
          timeOptionRefreshQueued = false;
          void this.loadTimeOptions(false, true);
        }
      }
    }
  },

  async loadMoreProposals() {
    const cursor = this.data.nextProposalCursor;
    if (
      !pageAlive ||
      this.data.proposalStatus !== "ready" ||
      !this.data.hasMoreProposals ||
      !cursor ||
      this.data.isLoadingMoreProposals ||
      proposalRequestActive ||
      requestedProposalCursors.has(cursor)
    ) {
      return;
    }

    const requestGeneration = proposalRequestGeneration;
    requestedProposalCursors.add(cursor);
    this.setData({
      isLoadingMoreProposals: true,
      proposalLoadMoreError: "",
      proposalCursorInvalid: false,
    });
    try {
      const page = await listProposals(this.data.groupId, this.data.hangoutId, {
        cursor,
        limit: PAGE_LIMIT,
      });
      if (!pageAlive || requestGeneration !== proposalRequestGeneration) {
        return;
      }

      const nextCursor = page.next_cursor;
      this.setData({
        proposals: mergeUniqueProposals(this.data.proposals, page.items),
        nextProposalCursor: nextCursor,
        hasMoreProposals: page.has_more && Boolean(nextCursor) && nextCursor !== cursor,
      });
    } catch (error) {
      if (!pageAlive || requestGeneration !== proposalRequestGeneration) {
        return;
      }

      requestedProposalCursors.delete(cursor);
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const cursorInvalid = error instanceof ApiError && error.code === 42213;
      const loadError = getCandidateLoadError(error, "更多候选活动");
      this.setData({
        proposalLoadMoreError: loadError.message,
        proposalCursorInvalid: cursorInvalid,
        ...(cursorInvalid ? { nextProposalCursor: null, hasMoreProposals: false } : {}),
      });
      if (loadError.parentUnavailable) {
        void this.loadDetail(false, true);
      }
    } finally {
      if (pageAlive && requestGeneration === proposalRequestGeneration) {
        this.setData({ isLoadingMoreProposals: false });
      }
    }
  },

  async loadMoreTimeOptions() {
    const cursor = this.data.nextTimeOptionCursor;
    if (
      !pageAlive ||
      this.data.timeOptionStatus !== "ready" ||
      !this.data.hasMoreTimeOptions ||
      !cursor ||
      this.data.isLoadingMoreTimeOptions ||
      timeOptionRequestActive ||
      requestedTimeOptionCursors.has(cursor)
    ) {
      return;
    }

    const requestGeneration = timeOptionRequestGeneration;
    requestedTimeOptionCursors.add(cursor);
    this.setData({
      isLoadingMoreTimeOptions: true,
      timeOptionLoadMoreError: "",
      timeOptionCursorInvalid: false,
    });
    try {
      const page = await listTimeOptions(this.data.groupId, this.data.hangoutId, {
        cursor,
        limit: PAGE_LIMIT,
      });
      if (!pageAlive || requestGeneration !== timeOptionRequestGeneration) {
        return;
      }

      const nextCursor = page.next_cursor;
      this.setData({
        timeOptions: mergeUniqueTimeOptions(this.data.timeOptions, page.items),
        nextTimeOptionCursor: nextCursor,
        hasMoreTimeOptions: page.has_more && Boolean(nextCursor) && nextCursor !== cursor,
      });
    } catch (error) {
      if (!pageAlive || requestGeneration !== timeOptionRequestGeneration) {
        return;
      }

      requestedTimeOptionCursors.delete(cursor);
      if (getAuthState().status === "unauthenticated") {
        await reLaunchToLogin("expired");
        return;
      }

      const cursorInvalid = error instanceof ApiError && error.code === 42213;
      const loadError = getCandidateLoadError(error, "更多候选时间");
      this.setData({
        timeOptionLoadMoreError: loadError.message,
        timeOptionCursorInvalid: cursorInvalid,
        ...(cursorInvalid ? { nextTimeOptionCursor: null, hasMoreTimeOptions: false } : {}),
      });
      if (loadError.parentUnavailable) {
        void this.loadDetail(false, true);
      }
    } finally {
      if (pageAlive && requestGeneration === timeOptionRequestGeneration) {
        this.setData({ isLoadingMoreTimeOptions: false });
      }
    }
  },

  onRetry() {
    void this.loadDetail(true);
  },

  onProposalRetry() {
    void this.loadProposals(true, this.data.proposals.length > 0);
  },

  onTimeOptionRetry() {
    void this.loadTimeOptions(true, this.data.timeOptions.length > 0);
  },

  onProposalRefreshRetry() {
    void this.loadProposals(false, true);
  },

  onTimeOptionRefreshRetry() {
    void this.loadTimeOptions(false, true);
  },

  onProposalLoadMoreTap() {
    if (this.data.proposalCursorInvalid) {
      void this.loadProposals(false, true);
      return;
    }
    void this.loadMoreProposals();
  },

  onTimeOptionLoadMoreTap() {
    if (this.data.timeOptionCursorInvalid) {
      void this.loadTimeOptions(false, true);
      return;
    }
    void this.loadMoreTimeOptions();
  },

  onReachBottom() {
    void this.loadMoreProposals();
    void this.loadMoreTimeOptions();
  },

  onBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack();
      return;
    }
    void reLaunchToIndex();
  },

  candidateFormUrl(
    resource: "proposal" | "time-option",
    mode: "create" | "edit",
    resourceId = "",
  ): string {
    const query = [
      `group_id=${encodeURIComponent(this.data.groupId)}`,
      `hangout_id=${encodeURIComponent(this.data.hangoutId)}`,
      `mode=${encodeURIComponent(mode)}`,
    ];
    if (resourceId) {
      query.push(
        `${resource === "proposal" ? "proposal_id" : "time_option_id"}=${encodeURIComponent(resourceId)}`,
      );
    }

    const pagePath =
      resource === "proposal" ? "/pages/proposals/form/index" : "/pages/time-options/form/index";
    return `${pagePath}?${query.join("&")}`;
  },

  async openCandidateForm(
    resource: "proposal" | "time-option",
    mode: "create" | "edit",
    item?: Proposal | TimeOption,
  ) {
    if (this.data.isNavigating || !this.data.hangout || this.data.hangout.status !== "draft") {
      return;
    }

    if (mode === "edit" && (!item || !item.can_manage)) {
      return;
    }

    this.setData({
      isNavigating: true,
      pendingRefreshSection: resource,
    });
    try {
      await navigateTo(
        this.candidateFormUrl(resource, mode, item?.id),
        mode === "edit"
          ? resource === "proposal"
            ? "proposalEditData"
            : "timeOptionEditData"
          : undefined,
        item,
      );
    } catch {
      if (pageAlive) {
        this.setData({ isNavigating: false, pendingRefreshSection: "" });
        wx.showToast({ title: "页面打开失败，请重试", icon: "none" });
      }
    }
  },

  onAddProposalTap() {
    void this.openCandidateForm("proposal", "create");
  },

  onAddTimeOptionTap() {
    void this.openCandidateForm("time-option", "create");
  },

  onEditProposalTap(event: WechatMiniprogram.TouchEvent) {
    const proposalId = String(event.currentTarget.dataset.proposalId ?? "");
    const proposal = this.data.proposals.find((item) => item.id === proposalId);
    if (proposal) {
      void this.openCandidateForm("proposal", "edit", proposal);
    }
  },

  onEditTimeOptionTap(event: WechatMiniprogram.TouchEvent) {
    const timeOptionId = String(event.currentTarget.dataset.timeOptionId ?? "");
    const timeOption = this.data.timeOptions.find((item) => item.id === timeOptionId);
    if (timeOption) {
      void this.openCandidateForm("time-option", "edit", timeOption);
    }
  },

  async onDeleteProposalTap(event: WechatMiniprogram.TouchEvent) {
    const proposalId = String(event.currentTarget.dataset.proposalId ?? "");
    const proposal = this.data.proposals.find((item) => item.id === proposalId);
    if (
      !proposal ||
      !proposal.can_manage ||
      this.data.hangout?.status !== "draft" ||
      this.data.deletingCandidateId
    ) {
      return;
    }

    const confirmed = await confirmDelete(
      "删除候选活动",
      `确定删除“${proposal.title}”吗？删除后无法恢复。`,
    );
    if (!confirmed || !pageAlive) {
      return;
    }

    this.setData({ deletingCandidateId: proposal.id, deletingCandidateType: "proposal" });
    try {
      await deleteProposal(this.data.groupId, this.data.hangoutId, proposal.id);
      if (!pageAlive) {
        return;
      }

      const proposals = this.data.proposals.filter((item) => item.id !== proposal.id);
      this.setData({
        proposals,
        proposalStatus: proposals.length > 0 ? "ready" : "empty",
      });
      wx.showToast({ title: "候选活动已删除", icon: "success" });
      void this.loadProposals(false, proposals.length > 0);
    } catch (error) {
      if (!pageAlive) {
        return;
      }
      await this.handleCandidateWriteError(error, "proposal", proposal.id);
    } finally {
      if (pageAlive) {
        this.setData({ deletingCandidateId: "", deletingCandidateType: "" });
      }
    }
  },

  async onDeleteTimeOptionTap(event: WechatMiniprogram.TouchEvent) {
    const timeOptionId = String(event.currentTarget.dataset.timeOptionId ?? "");
    const timeOption = this.data.timeOptions.find((item) => item.id === timeOptionId);
    if (
      !timeOption ||
      !timeOption.can_manage ||
      this.data.hangout?.status !== "draft" ||
      this.data.deletingCandidateId
    ) {
      return;
    }

    const confirmed = await confirmDelete(
      "删除候选时间",
      `确定删除“${timeOption.confirmationText}”吗？删除后无法恢复。`,
    );
    if (!confirmed || !pageAlive) {
      return;
    }

    this.setData({ deletingCandidateId: timeOption.id, deletingCandidateType: "time-option" });
    try {
      await deleteTimeOption(this.data.groupId, this.data.hangoutId, timeOption.id);
      if (!pageAlive) {
        return;
      }

      const timeOptions = this.data.timeOptions.filter((item) => item.id !== timeOption.id);
      this.setData({
        timeOptions,
        timeOptionStatus: timeOptions.length > 0 ? "ready" : "empty",
      });
      wx.showToast({ title: "候选时间已删除", icon: "success" });
      void this.loadTimeOptions(false, timeOptions.length > 0);
    } catch (error) {
      if (!pageAlive) {
        return;
      }
      await this.handleCandidateWriteError(error, "time-option", timeOption.id);
    } finally {
      if (pageAlive) {
        this.setData({ deletingCandidateId: "", deletingCandidateType: "" });
      }
    }
  },

  async handleCandidateWriteError(
    error: unknown,
    resource: "proposal" | "time-option",
    resourceId: string,
  ) {
    if (getAuthState().status === "unauthenticated") {
      await reLaunchToLogin("expired");
      return;
    }

    const resourceName = resource === "proposal" ? "候选活动" : "候选时间";
    if (error instanceof ApiError) {
      if (error.code === 40930 || error.code === 40940) {
        wx.showToast({ title: "约玩局状态已变化", icon: "none" });
        await this.loadDetail(false, true);
        if (resource === "proposal") {
          await this.loadProposals(false, true);
        } else {
          await this.loadTimeOptions(false, true);
        }
        return;
      }

      if (error.code === 40410 || error.code === 40420) {
        await this.loadDetail(false, true);
        return;
      }

      if (error.code === 40430 || error.code === 40440) {
        wx.showToast({ title: `${resourceName}已不可用`, icon: "none" });
        if (resource === "proposal") {
          const proposals = this.data.proposals.filter((item) => item.id !== resourceId);
          this.setData({
            proposals,
            proposalStatus: proposals.length > 0 ? "ready" : "empty",
          });
          await this.loadProposals(false, proposals.length > 0);
        } else {
          const timeOptions = this.data.timeOptions.filter((item) => item.id !== resourceId);
          this.setData({
            timeOptions,
            timeOptionStatus: timeOptions.length > 0 ? "ready" : "empty",
          });
          await this.loadTimeOptions(false, timeOptions.length > 0);
        }
        return;
      }

      if (error.code === 40330 || error.code === 40340) {
        wx.showToast({ title: `没有管理${resourceName}的权限`, icon: "none" });
        if (resource === "proposal") {
          await this.loadProposals(false, true);
        } else {
          await this.loadTimeOptions(false, true);
        }
        return;
      }
    }

    wx.showToast({
      title: getUserFacingError(error, `删除${resourceName}失败，请重试`),
      icon: "none",
    });
  },

  async onEditTap() {
    if (!this.data.canEdit || this.data.isNavigating || !this.data.hangout) {
      return;
    }

    this.setData({ isNavigating: true, pendingRefreshSection: "all" });
    try {
      const query = [
        `group_id=${encodeURIComponent(this.data.groupId)}`,
        `hangout_id=${encodeURIComponent(this.data.hangoutId)}`,
        `mode=${encodeURIComponent("edit")}`,
      ].join("&");
      await navigateTo(`/pages/hangouts/form/index?${query}`);
    } catch {
      if (pageAlive) {
        this.setData({ isNavigating: false, pendingRefreshSection: "" });
        wx.showToast({ title: "编辑页面打开失败，请重试", icon: "none" });
      }
    }
  },
});
