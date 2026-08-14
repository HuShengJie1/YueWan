import { API_V1_PREFIX, CLOUD_STORAGE_PUBLIC_BASE_URL } from "../constants/api";
import type { UpdateCurrentUserRequest, User } from "../types/user";
import { ApiError, request } from "./request";

const MAX_AVATAR_FILE_SIZE = 5 * 1024 * 1024;
const MAX_AVATAR_SOURCE_PIXELS = 20_000_000;
const MAX_AVATAR_DIMENSION = 512;
const MANAGED_AVATAR_FILENAME = /^[0-9]{13}-[0-9a-f]{16}\.(?:jpg|png)$/;

type SupportedAvatarType = "jpeg" | "png";

interface PreparedAvatar {
  filePath: string;
  extension: "jpg" | "png";
}

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

function makeFinalAvatarPath(userId: string, extension: "jpg" | "png"): string {
  const randomPart = Math.random().toString(16).slice(2, 18).padEnd(16, "0");
  return `avatars/${userId}/${Date.now()}-${randomPart}.${extension}`;
}

function validateFileSize(filePath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.getFileSystemManager().stat({
      path: filePath,
      success: ({ stats }) => {
        if (Array.isArray(stats) || !stats.isFile()) {
          reject(new ApiError("选择的头像文件无效", 422, 42201));
          return;
        }
        if (stats.size > MAX_AVATAR_FILE_SIZE) {
          reject(new ApiError("头像文件不能超过 5 MB", 413, 41301));
          return;
        }
        resolve();
      },
      fail: () => reject(new ApiError("无法读取选择的头像", 422, 42201)),
    });
  });
}

async function prepareAvatar(filePath: string): Promise<PreparedAvatar> {
  await validateFileSize(filePath);

  let imageInfo: WechatMiniprogram.GetImageInfoSuccessCallbackResult;
  try {
    imageInfo = await wx.getImageInfo({ src: filePath });
  } catch {
    throw new ApiError("头像图片无法识别", 422, 42201);
  }

  if (imageInfo.type !== "jpeg" && imageInfo.type !== "png") {
    throw new ApiError("请选择 JPEG 或 PNG 图片", 415, 41501);
  }
  if (
    imageInfo.width < 1 ||
    imageInfo.height < 1 ||
    imageInfo.width * imageInfo.height > MAX_AVATAR_SOURCE_PIXELS
  ) {
    throw new ApiError("头像图片尺寸过大或无效", 413, 41301);
  }

  const imageType: SupportedAvatarType = imageInfo.type;
  if (imageType === "png") {
    return { filePath, extension: "png" };
  }

  const scale = Math.min(1, MAX_AVATAR_DIMENSION / Math.max(imageInfo.width, imageInfo.height));
  const compressed = await wx.compressImage({
    src: filePath,
    quality: 85,
    compressedWidth: Math.max(1, Math.round(imageInfo.width * scale)),
    compressedHeight: Math.max(1, Math.round(imageInfo.height * scale)),
  });
  await validateFileSize(compressed.tempFilePath);
  return { filePath: compressed.tempFilePath, extension: "jpg" };
}

async function deleteCloudFile(fileId: string): Promise<void> {
  try {
    await wx.cloud.deleteFile({ fileList: [fileId] });
  } catch {
    // Cleanup is best effort and must not hide the upload result.
  }
}

function previousManagedFileId(
  avatarUrl: string | null,
  uploadedFileId: string,
  userId: string,
): string | null {
  if (!avatarUrl) {
    return null;
  }
  const publicPrefix = `${CLOUD_STORAGE_PUBLIC_BASE_URL}/`;
  if (!avatarUrl.startsWith(publicPrefix)) {
    return null;
  }
  const cloudPath = avatarUrl.slice(publicPrefix.length);
  const ownerPrefix = `avatars/${userId}/`;
  if (!cloudPath.startsWith(ownerPrefix)) {
    return null;
  }
  const filename = cloudPath.slice(ownerPrefix.length);
  if (!MANAGED_AVATAR_FILENAME.test(filename)) {
    return null;
  }
  const authority = /^cloud:\/\/([^/]+)\//.exec(uploadedFileId)?.[1];
  return authority ? `cloud://${authority}/${cloudPath}` : null;
}

export async function uploadCurrentUserAvatar(filePath: string, currentUser: User): Promise<User> {
  const prepared = await prepareAvatar(filePath);
  const uploaded = await wx.cloud.uploadFile({
    cloudPath: makeFinalAvatarPath(currentUser.id, prepared.extension),
    filePath: prepared.filePath,
  });

  try {
    const updatedUser = await request<User>({
      path: `${API_V1_PREFIX}/users/me/avatar`,
      method: "PUT",
      data: { file_id: uploaded.fileID },
    });
    const previousFileId = previousManagedFileId(
      currentUser.avatar_url,
      uploaded.fileID,
      currentUser.id,
    );
    if (previousFileId) {
      await deleteCloudFile(previousFileId);
    }
    return updatedUser;
  } catch (error) {
    await deleteCloudFile(uploaded.fileID);
    throw error;
  }
}
