export interface TimeOption {
  id: string;
  hangout_id: string;
  created_by_user_id: string;
  starts_at: string;
  ends_at: string | null;
  display_label: string | null;
  created_at: string;
  updated_at: string;
  can_manage: boolean;
}

export interface TimeOptionWriteInput {
  starts_at: string;
  ends_at: string | null;
  display_label: string | null;
}

export interface TimeOptionListQuery {
  cursor?: string | null;
  limit?: number;
}
