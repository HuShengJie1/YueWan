import { API_V1_PREFIX } from "../constants/api";
import type { CursorPage } from "../types/pagination";
import type { TimeOption, TimeOptionListQuery, TimeOptionWriteInput } from "../types/time-option";
import { request } from "./request";

const DEFAULT_PAGE_LIMIT = 20;

function timeOptionCollectionPath(groupId: string, hangoutId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}/hangouts/${encodeURIComponent(hangoutId)}/time-options`;
}

function timeOptionPath(groupId: string, hangoutId: string, timeOptionId: string): string {
  return `${timeOptionCollectionPath(groupId, hangoutId)}/${encodeURIComponent(timeOptionId)}`;
}

function buildCursorQuery({ cursor, limit = DEFAULT_PAGE_LIMIT }: TimeOptionListQuery): string {
  const query = [`limit=${encodeURIComponent(String(limit))}`];
  if (cursor) {
    query.push(`cursor=${encodeURIComponent(cursor)}`);
  }

  return query.join("&");
}

function writeData(input: TimeOptionWriteInput): Record<string, unknown> {
  return {
    starts_at: input.starts_at,
    ends_at: input.ends_at,
    display_label: input.display_label,
  };
}

export function createTimeOption(
  groupId: string,
  hangoutId: string,
  input: TimeOptionWriteInput,
): Promise<TimeOption> {
  return request<TimeOption>({
    path: timeOptionCollectionPath(groupId, hangoutId),
    method: "POST",
    data: writeData(input),
  });
}

export function listTimeOptions(
  groupId: string,
  hangoutId: string,
  query: TimeOptionListQuery = {},
): Promise<CursorPage<TimeOption>> {
  return request<CursorPage<TimeOption>>({
    path: `${timeOptionCollectionPath(groupId, hangoutId)}?${buildCursorQuery(query)}`,
  });
}

export function updateTimeOption(
  groupId: string,
  hangoutId: string,
  timeOptionId: string,
  input: TimeOptionWriteInput,
): Promise<TimeOption> {
  return request<TimeOption>({
    path: timeOptionPath(groupId, hangoutId, timeOptionId),
    method: "PUT",
    data: writeData(input),
  });
}

export function deleteTimeOption(
  groupId: string,
  hangoutId: string,
  timeOptionId: string,
): Promise<void> {
  return request<void>({
    path: timeOptionPath(groupId, hangoutId, timeOptionId),
    method: "DELETE",
    responseMode: "no-content",
  });
}
