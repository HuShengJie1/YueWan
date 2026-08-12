export type ProposalExternalData = Record<string, unknown>;

export interface Proposal {
  id: string;
  hangout_id: string;
  submitted_by_user_id: string;
  title: string;
  description: string | null;
  location_text: string | null;
  external_platform: string | null;
  external_url: string | null;
  external_data: ProposalExternalData | null;
  created_at: string;
  updated_at: string;
  can_manage: boolean;
}

export interface ProposalWriteInput {
  title: string;
  description: string | null;
  location_text: string | null;
  external_platform: string | null;
  external_url: string | null;
  external_data: ProposalExternalData | null;
}

export interface ProposalListQuery {
  cursor?: string | null;
  limit?: number;
}
