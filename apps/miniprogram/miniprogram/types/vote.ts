import type { HangoutStatus } from "./hangout";
import type { ProposalExternalData } from "./proposal";

export type ProposalVoteValue = "LIKE" | "OK" | "DISLIKE";

export interface ProposalVoteCounts {
  LIKE: number;
  OK: number;
  DISLIKE: number;
}

export interface ProposalVotingSummary {
  id: string;
  submitted_by_user_id: string;
  title: string;
  description: string | null;
  location_text: string | null;
  external_platform: string | null;
  external_url: string | null;
  external_data: ProposalExternalData | null;
  created_at: string;
  updated_at: string;
  vote_counts: ProposalVoteCounts;
  current_user_vote: ProposalVoteValue | null;
}

export interface TimeVotingSummary {
  id: string;
  created_by_user_id: string;
  starts_at: string;
  ends_at: string | null;
  display_label: string | null;
  created_at: string;
  updated_at: string;
  availability_count: number;
  current_user_selected: boolean;
}

export interface VotingSummary {
  hangout_id: string;
  status: HangoutStatus;
  voting_deadline: string | null;
  proposals: ProposalVotingSummary[];
  time_options: TimeVotingSummary[];
}

export interface TimeVoteListData {
  time_options: TimeVotingSummary[];
}
