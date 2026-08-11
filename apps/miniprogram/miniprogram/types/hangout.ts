export type HangoutStatus = "draft" | "voting" | "confirmed" | "cancelled" | "finished";

export interface Hangout {
  id: string;
  group_id: string;
  created_by_user_id: string;
  title: string;
  description: string | null;
  status: HangoutStatus;
  voting_deadline: string | null;
  confirmed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface HangoutWriteInput {
  title: string;
  description: string | null;
  voting_deadline: string | null;
}

export interface HangoutListQuery {
  cursor?: string | null;
  limit?: number;
}
