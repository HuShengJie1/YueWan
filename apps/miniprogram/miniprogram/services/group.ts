import { API_V1_PREFIX } from "../constants/api";
import type {
  CreateGroupRequest,
  CursorPage,
  DeleteGroupRequest,
  GroupDetail,
  GroupInviteToken,
  GroupMember,
  GroupSummary,
} from "../types/group";
import { request } from "./request";

const DEFAULT_PAGE_LIMIT = 20;

interface CursorQuery {
  cursor?: string | null;
  limit?: number;
}

function buildCursorQuery({ cursor, limit = DEFAULT_PAGE_LIMIT }: CursorQuery): string {
  const query = [`limit=${encodeURIComponent(String(limit))}`];
  if (cursor) {
    query.push(`cursor=${encodeURIComponent(cursor)}`);
  }

  return query.join("&");
}

function groupPath(groupId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}`;
}

export function createGroup(input: CreateGroupRequest): Promise<GroupDetail> {
  return request<GroupDetail>({
    path: `${API_V1_PREFIX}/groups`,
    method: "POST",
    data: {
      name: input.name,
      ...(input.description === undefined ? {} : { description: input.description }),
    },
  });
}

export function listGroups(query: CursorQuery = {}): Promise<CursorPage<GroupSummary>> {
  return request<CursorPage<GroupSummary>>({
    path: `${API_V1_PREFIX}/groups?${buildCursorQuery(query)}`,
  });
}

export function getGroup(groupId: string): Promise<GroupDetail> {
  return request<GroupDetail>({ path: groupPath(groupId) });
}

export function listGroupMembers(
  groupId: string,
  query: CursorQuery = {},
): Promise<CursorPage<GroupMember>> {
  return request<CursorPage<GroupMember>>({
    path: `${groupPath(groupId)}/members?${buildCursorQuery(query)}`,
  });
}

export function createGroupInviteToken(groupId: string): Promise<GroupInviteToken> {
  return request<GroupInviteToken>({
    path: `${groupPath(groupId)}/invite-tokens`,
    method: "POST",
  });
}

export function joinGroup(groupId: string, inviteToken: string): Promise<GroupDetail> {
  return request<GroupDetail>({
    path: `${groupPath(groupId)}/members/me`,
    method: "PUT",
    data: { invite_token: inviteToken },
  });
}

export function deleteGroup(groupId: string, confirmationName: string): Promise<void> {
  const input: DeleteGroupRequest = { confirmation_name: confirmationName };
  return request<void>({
    path: groupPath(groupId),
    method: "DELETE",
    data: { confirmation_name: input.confirmation_name },
    responseMode: "no-content",
  });
}
