import { API_V1_PREFIX } from "../constants/api";
import type { UpdateCurrentUserRequest, User } from "../types/user";
import { request, uploadFile } from "./request";

export function getCurrentUser(): Promise<User> {
  return request<User>({
    path: `${API_V1_PREFIX}/users/me`,
  });
}

export function updateCurrentUser(input: UpdateCurrentUserRequest): Promise<User> {
  return request<User>({
    path: `${API_V1_PREFIX}/users/me`,
    method: "PUT",
    data: { nickname: input.nickname },
  });
}

export function uploadCurrentUserAvatar(filePath: string): Promise<User> {
  return uploadFile<User>({
    path: `${API_V1_PREFIX}/users/me/avatar`,
    filePath,
    name: "file",
  });
}
