import type { Hangout, HangoutStatus } from "../types/hangout";

interface HangoutStatusMeta {
  label: string;
  className: string;
}

export interface HangoutView extends Hangout {
  statusLabel: string;
  statusClass: string;
  descriptionText: string;
  votingDeadlineText: string;
  createdAtText: string;
}

export interface LocalDateTimeFields {
  date: string;
  time: string;
}

const STATUS_META: Record<HangoutStatus, HangoutStatusMeta> = {
  draft: { label: "草稿", className: "status-draft" },
  voting: { label: "投票中", className: "status-voting" },
  confirmed: { label: "已确认", className: "status-confirmed" },
  cancelled: { label: "已取消", className: "status-cancelled" },
  finished: { label: "已结束", className: "status-finished" },
};

const WEEKDAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function padNumber(value: number): string {
  return String(value).padStart(2, "0");
}

export function getHangoutStatusMeta(status: HangoutStatus): HangoutStatusMeta {
  return STATUS_META[status];
}

export function formatLocalDateTime(value: string | null, emptyText: string): string {
  if (!value) {
    return emptyText;
  }

  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return "时间信息异常";
  }

  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${WEEKDAY_LABELS[date.getDay()]} ${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
}

export function toLocalDateTimeFields(value: string): LocalDateTimeFields | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return null;
  }

  return {
    date: `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`,
    time: `${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`,
  };
}

export function formatLocalDateInput(date: Date): string {
  return `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`;
}

export function formatLocalTimeInput(date: Date): string {
  return `${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
}

export function buildHangoutView(hangout: Hangout): HangoutView {
  const status = getHangoutStatusMeta(hangout.status);
  return {
    ...hangout,
    statusLabel: status.label,
    statusClass: status.className,
    descriptionText: hangout.description || "还没有补充约玩说明",
    votingDeadlineText: formatLocalDateTime(hangout.voting_deadline, "暂未设置截止时间"),
    createdAtText: formatLocalDateTime(hangout.created_at, "创建时间未知"),
  };
}
