import { API_V1_PREFIX } from "../constants/api";
import type { ConfirmEventInput, HangoutEvent } from "../types/event";
import { request } from "./request";

function eventPath(groupId: string, hangoutId: string): string {
  return `${API_V1_PREFIX}/groups/${encodeURIComponent(groupId)}/hangouts/${encodeURIComponent(hangoutId)}/event`;
}

export function getEvent(groupId: string, hangoutId: string): Promise<HangoutEvent> {
  return request<HangoutEvent>({ path: eventPath(groupId, hangoutId) });
}

export function confirmEvent(
  groupId: string,
  hangoutId: string,
  input: ConfirmEventInput,
): Promise<HangoutEvent> {
  return request<HangoutEvent>({
    path: eventPath(groupId, hangoutId),
    method: "PUT",
    data: {
      proposal_id: input.proposal_id,
      time_option_id: input.time_option_id,
    },
  });
}
