export type GroupMemberRole = "owner" | "member";

export interface GroupSummary {
  id: string;
  name: string;
  description: string | null;
  current_user_role: GroupMemberRole;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export type GroupDetail = GroupSummary;

export interface GroupMember {
  user_id: string;
  nickname: string;
  avatar_url: string | null;
  role: GroupMemberRole;
  joined_at: string;
}

export interface CreateGroupRequest {
  name: string;
  description?: string | null;
}

export interface DeleteGroupRequest {
  confirmation_name: string;
}

export interface GroupInviteToken {
  invite_token: string;
  expires_at: string;
}
