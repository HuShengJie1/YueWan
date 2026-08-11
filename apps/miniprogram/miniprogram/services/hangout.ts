import { API_V1_PREFIX } from "../constants/api";
import type { Hangout, HangoutListQuery, HangoutWriteInput } from "../types/hangout";
import type { CursorPage } from "../types/pagination";
import { request } from "./request";

const DEFAULT_PAGE_LIMIT = 20;

function groupHangoutsPath(groupId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}/hangouts`;
}

function hangoutPath(groupId: string, hangoutId: string): string {
  return `${groupHangoutsPath(groupId)}/${encodeURIComponent(hangoutId)}`;
}

function buildCursorQuery({ cursor, limit = DEFAULT_PAGE_LIMIT }: HangoutListQuery): string {
  const query = [`limit=${encodeURIComponent(String(limit))}`];
  if (cursor) {
    query.push(`cursor=${encodeURIComponent(cursor)}`);
  }

  return query.join("&");
}

function writeData(input: HangoutWriteInput): Record<string, unknown> {
  return {
    title: input.title,
    description: input.description,
    voting_deadline: input.voting_deadline,
  };
}

export function createHangout(groupId: string, input: HangoutWriteInput): Promise<Hangout> {
  return request<Hangout>({
    path: groupHangoutsPath(groupId),
    method: "POST",
    data: writeData(input),
  });
}

export function listHangouts(
  groupId: string,
  query: HangoutListQuery = {},
): Promise<CursorPage<Hangout>> {
  return request<CursorPage<Hangout>>({
    path: `${groupHangoutsPath(groupId)}?${buildCursorQuery(query)}`,
  });
}

export function getHangout(groupId: string, hangoutId: string): Promise<Hangout> {
  return request<Hangout>({ path: hangoutPath(groupId, hangoutId) });
}

export function updateHangout(
  groupId: string,
  hangoutId: string,
  input: HangoutWriteInput,
): Promise<Hangout> {
  return request<Hangout>({
    path: hangoutPath(groupId, hangoutId),
    method: "PUT",
    data: writeData(input),
  });
}
