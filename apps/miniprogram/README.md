# Miniprogram

Native WeChat miniprogram client written in TypeScript. The checked-in
`touristappid` enables the WeChat Developer Tools tourist/test workflow; use a local
`project.private.config.json` for real developer settings and never commit credentials.

See [`../../docs/development.md`](../../docs/development.md) for setup instructions.

## Authentication frontend

The miniprogram includes the frontend boundary for WeChat identity:

- explicit first-time WeChat login and duplicate-submit protection;
- persisted application access tokens with expiry checks;
- startup validation through the current-user endpoint;
- centralized Bearer Token injection and `401` session cleanup;
- required nickname completion, user-initiated avatar selection/upload, profile editing, and
  local logout;
- loading, network failure, expired-session, and retry states.

The backend endpoints are intentionally not mocked. When the backend is unavailable, login
displays a retryable network or service state. The request and response shapes are documented
in [`../../docs/api-conventions.md`](../../docs/api-conventions.md).

Avatar selection uses WeChat's `chooseAvatar` open ability. The returned local temporary path
is previewed and uploaded immediately through the centralized request service; it is never
stored as a permanent user URL. `POST /api/v1/users/me/avatar` returns the persisted user URL
after the backend validates, normalizes, and stores the image.

The checked-in `touristappid` supports UI and build verification only. End-to-end login
requires a real AppID in the untracked `project.private.config.json` and corresponding
backend WeChat credentials in the backend's untracked environment file.
