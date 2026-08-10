export interface User {
  id: string;
  nickname: string | null;
  avatar_url: string | null;
  profile_completed: boolean;
}

export interface UpdateCurrentUserRequest {
  nickname: string;
}
