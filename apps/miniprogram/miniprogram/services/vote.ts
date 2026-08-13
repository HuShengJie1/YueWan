import { API_V1_PREFIX } from "../constants/api";
import type { Hangout } from "../types/hangout";
import type {
  ProposalVotingSummary,
  ProposalVoteValue,
  TimeVoteListData,
  VotingSummary,
} from "../types/vote";
import { request } from "./request";

function hangoutVotingPath(groupId: string, hangoutId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}/hangouts/${encodeURIComponent(hangoutId)}`;
}

function proposalVotePath(groupId: string, hangoutId: string, proposalId: string): string {
  return `${hangoutVotingPath(groupId, hangoutId)}/proposals/${encodeURIComponent(proposalId)}/vote`;
}

export function startVoting(groupId: string, hangoutId: string): Promise<Hangout> {
  return request<Hangout>({
    path: `${hangoutVotingPath(groupId, hangoutId)}/voting`,
    method: "PUT",
  });
}

export function getVotingSummary(groupId: string, hangoutId: string): Promise<VotingSummary> {
  return request<VotingSummary>({
    path: `${hangoutVotingPath(groupId, hangoutId)}/votes`,
  });
}

export function setProposalVote(
  groupId: string,
  hangoutId: string,
  proposalId: string,
  value: ProposalVoteValue,
): Promise<ProposalVotingSummary> {
  return request<ProposalVotingSummary>({
    path: proposalVotePath(groupId, hangoutId, proposalId),
    method: "PUT",
    data: { value },
  });
}

export function deleteProposalVote(
  groupId: string,
  hangoutId: string,
  proposalId: string,
): Promise<ProposalVotingSummary> {
  return request<ProposalVotingSummary>({
    path: proposalVotePath(groupId, hangoutId, proposalId),
    method: "DELETE",
  });
}

export function replaceTimeVotes(
  groupId: string,
  hangoutId: string,
  timeOptionIds: string[],
): Promise<TimeVoteListData> {
  return request<TimeVoteListData>({
    path: `${hangoutVotingPath(groupId, hangoutId)}/time-votes/me`,
    method: "PUT",
    data: { time_option_ids: timeOptionIds },
  });
}
