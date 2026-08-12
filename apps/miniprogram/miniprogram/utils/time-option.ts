export interface LocalDateTimeFields {
  date: string;
  time: string;
}

const WEEKDAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function padNumber(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatLocalDateInput(date: Date): string {
  return `${date.getFullYear()}-${padNumber(date.getMonth() + 1)}-${padNumber(date.getDate())}`;
}

export function formatLocalTimeInput(date: Date): string {
  return `${padNumber(date.getHours())}:${padNumber(date.getMinutes())}`;
}

export function parseLocalDateTime(dateValue: string, timeValue: string): Date | null {
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
  const date = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day ||
    date.getHours() !== hour ||
    date.getMinutes() !== minute
  ) {
    return null;
  }

  return date;
}

export function toLocalDateTimeFields(value: string): LocalDateTimeFields | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return null;
  }

  return {
    date: formatLocalDateInput(date),
    time: formatLocalTimeInput(date),
  };
}

export function formatLocalDate(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return "日期信息异常";
  }

  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${WEEKDAY_LABELS[date.getDay()]}`;
}

export function formatLocalTime(value: string | null, emptyText: string): string {
  if (!value) {
    return emptyText;
  }

  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) {
    return "时间信息异常";
  }

  return formatLocalTimeInput(date);
}
