import { API_V1_PREFIX } from "../constants/api";
import type { UpdateCurrentUserRequest, User } from "../types/user";
import { request } from "./request";

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

function makeTemporaryAvatarPath(userId: string): string {
  const randomPart = Math.random().toString(16).slice(2, 18).padEnd(16, "0");
  return `avatar-uploads/${userId}/${Date.now()}-${randomPart}.source`;
}

async function deleteTemporaryCloudFile(fileId: string): Promise<void> {
  try {
    await wx.cloud.deleteFile({ fileList: [fileId] });
  } catch {
    // The backend normally removes the temporary object. This is only compensation
    // for a request that failed before reaching it and must not mask the real error.
  }
}

export async function uploadCurrentUserAvatar(filePath: string, userId: string): Promise<User> {
  const uploaded = await wx.cloud.uploadFile({
    cloudPath: makeTemporaryAvatarPath(userId),
    filePath,
  });

  try {
    return await request<User>({
      path: `${API_V1_PREFIX}/users/me/avatar`,
      method: "PUT",
      data: { file_id: uploaded.fileID },
    });
  } catch (error) {
    await deleteTemporaryCloudFile(uploaded.fileID);
    throw error;
  }
}
