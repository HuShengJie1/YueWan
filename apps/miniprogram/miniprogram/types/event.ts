export interface HangoutEvent {
  id: string;
  hangout_id: string;
  proposal_id: string | null;
  time_option_id: string | null;
  confirmed_by_user_id: string;
  title: string;
  description: string | null;
  location_text: string | null;
  starts_at: string;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConfirmEventInput {
  proposal_id: string;
  time_option_id: string;
}
