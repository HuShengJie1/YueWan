import type { User } from "../types/user";
import { readPendingGroupInvite } from "../stores/pending-group-invite";

const INDEX_PAGE = "/pages/index/index";
const LOGIN_PAGE = "/pages/login/login";
const PROFILE_PAGE = "/pages/profile/profile";
const GROUP_JOIN_PAGE = "/pages/groups/join/index";

function reLaunch(url: string): Promise<void> {
  const pages = getCurrentPages();
  const currentRoute = pages[pages.length - 1]?.route;
  if (currentRoute === url.replace(/^\//, "")) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    wx.reLaunch({
      url,
      success: () => resolve(),
      fail: ({ errMsg }) => reject(new Error(errMsg)),
    });
  });
}

export function reLaunchForAuthenticatedUser(user: User): Promise<void> {
  if (!user.profile_completed) {
    return reLaunch(PROFILE_PAGE);
  }

  const pendingInvite = readPendingGroupInvite();
  if (pendingInvite) {
    const query = [
      `group_id=${encodeURIComponent(pendingInvite.group_id)}`,
      `token=${encodeURIComponent(pendingInvite.invite_token)}`,
    ].join("&");
    return reLaunch(`${GROUP_JOIN_PAGE}?${query}`);
  }

  return reLaunch(INDEX_PAGE);
}

export function reLaunchToLogin(reason?: "expired"): Promise<void> {
  const query = reason ? `?reason=${reason}` : "";
  return reLaunch(`${LOGIN_PAGE}${query}`);
}

export function reLaunchToIndex(): Promise<void> {
  return reLaunch(INDEX_PAGE);
}
