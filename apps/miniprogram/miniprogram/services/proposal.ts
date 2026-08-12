import { API_V1_PREFIX } from "../constants/api";
import type { CursorPage } from "../types/pagination";
import type { Proposal, ProposalListQuery, ProposalWriteInput } from "../types/proposal";
import { request } from "./request";

const DEFAULT_PAGE_LIMIT = 20;

function proposalCollectionPath(groupId: string, hangoutId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}/hangouts/${encodeURIComponent(hangoutId)}/proposals`;
}

function proposalPath(groupId: string, hangoutId: string, proposalId: string): string {
  return `${proposalCollectionPath(groupId, hangoutId)}/${encodeURIComponent(proposalId)}`;
}

function buildCursorQuery({ cursor, limit = DEFAULT_PAGE_LIMIT }: ProposalListQuery): string {
  const query = [`limit=${encodeURIComponent(String(limit))}`];
  if (cursor) {
    query.push(`cursor=${encodeURIComponent(cursor)}`);
  }

  return query.join("&");
}

function writeData(input: ProposalWriteInput): Record<string, unknown> {
  return {
    title: input.title,
    description: input.description,
    location_text: input.location_text,
    external_platform: input.external_platform,
    external_url: input.external_url,
    external_data: input.external_data,
  };
}

export function createProposal(
  groupId: string,
  hangoutId: string,
  input: ProposalWriteInput,
): Promise<Proposal> {
  return request<Proposal>({
    path: proposalCollectionPath(groupId, hangoutId),
    method: "POST",
    data: writeData(input),
  });
}

export function listProposals(
  groupId: string,
  hangoutId: string,
  query: ProposalListQuery = {},
): Promise<CursorPage<Proposal>> {
  return request<CursorPage<Proposal>>({
    path: `${proposalCollectionPath(groupId, hangoutId)}?${buildCursorQuery(query)}`,
  });
}

export function updateProposal(
  groupId: string,
  hangoutId: string,
  proposalId: string,
  input: ProposalWriteInput,
): Promise<Proposal> {
  return request<Proposal>({
    path: proposalPath(groupId, hangoutId, proposalId),
    method: "PUT",
    data: writeData(input),
  });
}

export function deleteProposal(
  groupId: string,
  hangoutId: string,
  proposalId: string,
): Promise<void> {
  return request<void>({
    path: proposalPath(groupId, hangoutId, proposalId),
    method: "DELETE",
    responseMode: "no-content",
  });
}
