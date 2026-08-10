import { PENDING_GROUP_INVITE_STORAGE_KEY } from "../constants/storage";

const PENDING_INVITE_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_INVITE_TOKEN_LENGTH = 4096;

export interface PendingGroupInvite {
  group_id: string;
  invite_token: string;
  received_at: number;
}

function isPendingGroupInvite(value: unknown): value is PendingGroupInvite {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const invite = value as Partial<PendingGroupInvite>;
  return (
    typeof invite.group_id === "string" &&
    invite.group_id.length > 0 &&
    typeof invite.invite_token === "string" &&
    invite.invite_token.length > 0 &&
    invite.invite_token.length <= MAX_INVITE_TOKEN_LENGTH &&
    typeof invite.received_at === "number" &&
    Number.isFinite(invite.received_at)
  );
}

function isExpired(invite: PendingGroupInvite): boolean {
  return invite.received_at <= Date.now() - PENDING_INVITE_TTL_MS;
}

export function readPendingGroupInvite(): PendingGroupInvite | null {
  try {
    const storedValue: unknown = wx.getStorageSync(PENDING_GROUP_INVITE_STORAGE_KEY);
    if (isPendingGroupInvite(storedValue) && !isExpired(storedValue)) {
      return storedValue;
    }

    clearPendingGroupInvite();
    return null;
  } catch {
    return null;
  }
}

export function savePendingGroupInvite(groupId: string, inviteToken: string): PendingGroupInvite {
  const invite: PendingGroupInvite = {
    group_id: groupId,
    invite_token: inviteToken,
    received_at: Date.now(),
  };

  wx.setStorageSync(PENDING_GROUP_INVITE_STORAGE_KEY, invite);
  return invite;
}

export function clearPendingGroupInvite(): void {
  try {
    wx.removeStorageSync(PENDING_GROUP_INVITE_STORAGE_KEY);
  } catch {
    // Expired and completed invitations must also be cleared from in-memory flows.
  }
}
