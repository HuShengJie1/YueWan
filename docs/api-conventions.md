# API 约定

## 路径和命名

- 业务 REST API 使用 `/api/v1` 前缀；根级 `/health` 仅供基础存活检查。
- 资源路径使用小写复数名词和 kebab-case，例如 `/api/v1/groups/{group_id}/hangouts`。
- 行为优先通过资源和 HTTP 方法表达，避免 `/doSomething` 风格路径。
- JSON 字段使用 `snake_case`，与 Python 模型保持一致。

## HTTP 状态码

- `200 OK`：读取或更新成功。
- `201 Created`：资源创建成功，并尽量返回 `Location`。
- `204 No Content`：成功且无响应体。
- `400 Bad Request`：请求语义不合法。
- `401 Unauthorized`：缺失或无效认证。
- `403 Forbidden`：身份有效但无权限。
- `404 Not Found`：资源不存在或对当前用户不可见。
- `409 Conflict`：资源状态或唯一约束冲突。
- `413 Payload Too Large`：上传文件超过服务端限制。
- `415 Unsupported Media Type`：上传文件格式不受支持。
- `422 Unprocessable Entity`：字段校验失败。
- `500 Internal Server Error`：未预期服务端错误。
- `503 Service Unavailable`：依赖服务或文件存储暂时不可用。

业务 `code` 不替代 HTTP 状态码，失败请求不得全部返回 HTTP 200。

## 响应格式

成功：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

失败：

```json
{
  "code": 40001,
  "message": "Invalid request",
  "data": null
}
```

业务错误码按领域分段，在实现相应领域时登记。错误消息不得泄露堆栈、SQL、密钥或第三方 token。FastAPI 请求验证、HTTP 错误和已知业务异常均通过统一处理器适配本 envelope。

## 分页

列表优先采用游标分页。标准查询参数是 `cursor` 和 `limit`，其中 `limit` 必须设置服务端上限。响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [],
    "next_cursor": null,
    "has_more": false
  }
}
```

只有后台报表等明确需要总数和随机跳页的场景才使用 `page` / `page_size`。

## 日期、ID 和认证

- 日期时间为带时区 ISO 8601 UTC 字符串。
- API ID 为 UUID 字符串。
- 认证 Header 为 `Authorization: Bearer <access_token>`。
- Token 只进入 Header，不放 URL、日志或错误消息。

当前后端和小程序已按下述契约实现微信登录、会话恢复与当前用户资料更新。

## 微信登录契约

### 微信登录

`POST /api/v1/auth/wechat/login`

请求：

```json
{
  "code": "wx.login returned code"
}
```

成功响应的 `data`：

```json
{
  "access_token": "application access token",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": {
    "id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
    "nickname": null,
    "avatar_url": null,
    "profile_completed": false
  }
}
```

- `expires_in` 单位为秒。
- `code` 必填，去除首尾空白后长度为 1–256。
- 后端负责用 code 换取微信标识、查找或创建 User 并签发本系统 access token。
- 无论内部是首次建立 User 还是已有用户登录，都返回 `200 OK`。
- 小程序不保存 code、openid、unionid 或 session_key。

### 当前用户

`GET /api/v1/users/me`

需要 Bearer Token，成功响应的 `data` 为上述 `user` 对象。小程序在冷启动时通过该接口验证本地会话，不把用户缓存当作权威数据。

### 更新当前用户

`PUT /api/v1/users/me`

请求：

```json
{
  "nickname": "小林"
}
```

成功响应的 `data` 为更新后的 `user` 对象。当用户已满足必填资料条件时，后端返回 `profile_completed: true`。

`nickname` 去除首尾空白后长度为 1–24；空白或过长返回 `422` 统一错误 envelope。微信首次登录不会自动获取昵称，因此新用户响应为 `nickname: null` 和 `profile_completed: false`。

微信小程序 `wx.request` 不提供 PATCH 方法，因此当前用户更新统一使用 PUT。

### 上传当前用户头像

`POST /api/v1/users/me/avatar`

- 需要 Bearer Token，请求为 `multipart/form-data`。
- 文件字段名固定为 `file`，限 JPEG、PNG 或 WebP，最大 5 MiB。
- 成功返回 `200 OK`，`data` 为更新后的 `user` 对象，其 `avatar_url` 为可持久访问的地址；本地开发可使用 HTTP，真机和生产必须使用 HTTPS。
- 小程序会在上传前检查文件大小；后端仍必须重新校验真实文件类型、大小和图片可解码性。
- 后端忽略客户端文件名和声明的 MIME 类型，以实际图片内容为准；图片按 EXIF 方向纠正，最长边缩放到 512 px，去除元数据并统一编码为 JPEG。
- 微信 `chooseAvatar` 返回的本地临时路径只用于预览和本次上传，不进入 User 响应或数据库。

前端选择头像后会立即调用该接口；上传成功后才将服务端返回的 URL 写入会话用户。

## 群组与成员契约

以下接口均需要 `Authorization: Bearer <access_token>`。除成功删除固定返回空的 `204 No Content` 外，接口使用统一响应 envelope。群组不存在与当前用户不是 active 成员时统一返回 `40410`，不会透露群组是否真实存在。

### 创建群组

`POST /api/v1/groups`

请求：

```json
{
  "name": "周末搭子",
  "description": "周末一起吃饭和玩桌游"
}
```

- `name` 去除首尾空白后长度为 1–40。
- `description` 可为 `null`，去除首尾空白后最长 200；空字符串或纯空白转换为 `null`。
- 后端在同一事务内创建 Group 和当前用户的 `owner/active` GroupMember，任一步失败都会整体回滚。
- 成功返回 `201 Created`，设置指向群组详情的 `Location`，`data` 为下述群组详情。

### 群组列表

`GET /api/v1/groups?cursor=&limit=`

- 只返回当前用户 `status=active` 的群组。
- `limit` 默认为 20，范围为 1–100。
- 按当前用户成员关系的加入时间倒序，再按成员关系 UUID 倒序，使用键集游标保证稳定分页。
- `cursor` 是绑定当前用户和列表用途的签名不透明值；不得解析、修改或跨用户复用。无效或被篡改的 cursor 返回 `42213`。
- 每个列表项的 `member_count` 只统计 active 成员，并通过集合查询获取，不逐群组查询。

成功响应的 `data`：

```json
{
  "items": [
    {
      "id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
      "name": "周末搭子",
      "description": null,
      "current_user_role": "owner",
      "member_count": 1,
      "created_at": "2026-08-15T11:00:00Z",
      "updated_at": "2026-08-15T11:00:00Z"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

### 群组详情

`GET /api/v1/groups/{group_id}`

- 只有 active 成员可读；不存在、已退出或从未加入均返回相同的 `40410`。
- 成功响应的 `data` 为群组列表项结构，`current_user_role` 是当前用户的角色，`member_count` 只统计 active 成员。

### 永久删除群组

`DELETE /api/v1/groups/{group_id}`

请求：

```json
{
  "confirmation_name": "周末搭子"
}
```

- 只有 `status=active` 且 `role=owner` 的成员可以删除。active member 但不是 owner 返回 `40310`；不存在、非成员或 left 成员统一返回 `40410`。
- `confirmation_name` 在 Service 中去除首尾空白后，必须与数据库当前群组名称完全一致；空字符串、纯空白或名称错误均返回 `42214`。
- Repository 在鉴权与名称校验前锁定目标 Group 和当前 active GroupMember，删除及提交保持在同一个短事务内；并发状态冲突使用 `40910`，提交失败会回滚。
- 成功返回 `204 No Content`，响应体为空，不返回成功 envelope。删除后详情、成员列表和加入均返回 `40410`。
- 删除是不可恢复的硬删除。数据库外键会级联删除该群组的 `group_members`、`hangouts`、`proposals`、`proposal_votes`、`time_options`、`time_votes` 和 `events`。
- 不删除任何 User、头像文件或其他群组的数据。
- 已签发的邀请 token 不单独撤销；由于目标 Group 已不存在，使用旧 token 加入会返回 `40410`，不会重新创建群组或成员关系。

### 群组成员列表

`GET /api/v1/groups/{group_id}/members?cursor=&limit=`

- 只有群组 active 成员可读，只返回 active 成员。
- `limit` 默认为 20，范围为 1–100；按加入时间倒序和成员关系 UUID 倒序稳定分页。
- cursor 绑定群组和成员列表用途，不能复用于其他群组或群组列表；无效值返回 `42213`。
- `User.display_name` 对外字段名为 `nickname`。响应不包含 `wechat_openid`、`wechat_unionid`、`session_key` 或其他认证字段。

成功响应的成员项：

```json
{
  "user_id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "nickname": "小林",
  "avatar_url": null,
  "role": "member",
  "joined_at": "2026-08-15T11:00:00Z"
}
```

### 生成群组邀请

`POST /api/v1/groups/{group_id}/invite-tokens`

- 只有群组 active 成员可以生成，成功返回 `201 Created`。
- 邀请 token 有效期为 7 天，可重复使用；当前 MVP 不持久化、不撤销、不限制使用次数，也不记录邀请审计。
- token 使用 HS256 签名，包含 `group_id`、`iat`、`exp`、`iss`、`aud` 和严格的 `type=group_invite`。
- 邀请 token 使用独立 audience 且严格校验 type，不能作为 access token；access token 也不能作为邀请 token。
- token 不得进入 URL、应用日志或错误消息。

成功响应的 `data`：

```json
{
  "invite_token": "signed opaque token",
  "expires_at": "2026-08-22T11:00:00Z"
}
```

### 加入或恢复群组成员关系

`PUT /api/v1/groups/{group_id}/members/me`

请求：

```json
{
  "invite_token": "signed opaque token"
}
```

- 后端严格校验签名、期限、type、用途及 token 的 `group_id` 与路径一致。
- 从未加入时原子创建 `member/active` 关系；已 active 时幂等成功且不创建重复记录；已 left 时恢复为 `member/active` 并清空 `left_at`。
- 该接口不会把已有 owner 降级为 member。
- PostgreSQL `ON CONFLICT` 与 `(group_id, user_id)` 唯一约束保证并发加入不会产生重复 GroupMember；整个加入和详情读取在一个事务中提交。
- 成功返回 `200 OK`，`data` 为加入后的群组详情。

### 群组错误码

| HTTP | 业务 code | 语义                                         |
| ---- | --------- | -------------------------------------------- |
| 403  | `40310`   | 当前用户是 active 成员，但不是可删除群组的 owner |
| 404  | `40410`   | 群组不存在或对当前用户不可见                 |
| 409  | `40910`   | 群组并发写入、唯一约束或资源状态冲突         |
| 422  | `42210`   | 邀请 token 签名、声明、type 或用途无效        |
| 422  | `42211`   | 邀请 token 已过期                            |
| 422  | `42212`   | 邀请 token 中的群组与路径群组不匹配          |
| 422  | `42213`   | 分页 cursor 无效、被篡改、用途或作用域不匹配 |
| 422  | `42214`   | 删除确认名称与数据库当前群组名称不一致       |

字段格式、UUID 路径参数或 `limit` 校验失败继续使用通用 `422 / 40001`。所有错误响应均隐藏 SQL、token、内部堆栈和群组存在性细节。

## 约玩局契约

以下接口均需要 `Authorization: Bearer <access_token>`，并使用统一响应 envelope。群组不存在或当前用户不是 active 成员统一返回 `40410`；约玩局不存在、与路径群组不匹配或不可见统一返回 `40420`。

约玩局响应：

```json
{
  "id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "group_id": "62429e4e-24cf-495c-b223-f63891147cf7",
  "created_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
  "title": "周末一起出去玩",
  "description": null,
  "status": "draft",
  "voting_deadline": null,
  "confirmed_at": null,
  "cancelled_at": null,
  "created_at": "2026-08-10T03:00:00Z",
  "updated_at": "2026-08-10T03:00:00Z"
}
```

### 创建约玩局

`POST /api/v1/groups/{group_id}/hangouts`

请求：

```json
{
  "title": "周末一起出去玩",
  "description": "先把时间和活动定下来",
  "voting_deadline": "2026-08-15T12:00:00Z"
}
```

- `title` 去除首尾空白后长度为 1–60。
- `description` 可为 `null`，去除首尾空白后最长 500；空字符串或纯空白转换为 `null`。
- `voting_deadline` 可为 `null`；存在时必须包含时区、晚于请求校验时刻，并转换为 UTC。
- 只有群组 active 成员可创建；`created_by_user_id` 固定为当前用户，`status` 固定为 `draft`。客户端提交 `status`、`group_id`、`created_by_user_id` 或其他未声明字段会返回通用 `422 / 40001`。
- 成功返回 `201 Created`，设置指向约玩局详情的 `Location`。

### 约玩局列表

`GET /api/v1/groups/{group_id}/hangouts?cursor=&limit=`

- 只有群组 active 成员可读。
- `limit` 默认为 20，范围为 1–100。
- 按 `created_at DESC, id DESC` 跨状态稳定排序。
- cursor 是签名不透明值，绑定路径 `group_id` 和 `hangout_list` 用途，不能跨群组或与其他列表复用；无效值返回 `42213`。
- 成功响应的 `data` 使用标准 CursorPage envelope，`items` 为约玩局响应数组。

### 约玩局详情

`GET /api/v1/groups/{group_id}/hangouts/{hangout_id}`

- 只有群组 active 成员可读。
- 后端同时按 `group_id` 和 `hangout_id` 查询；属于其他群组的 Hangout 不可见并返回 `40420`。

### 更新约玩局草稿

`PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}`

- 请求字段和创建约玩局一致，是对当前可编辑字段的完整更新；不能修改 `status`、`group_id` 或 `created_by_user_id`。
- 只有约玩局创建者或群主可以编辑；其他 active 成员返回 `40320`。
- 只有 `draft` 状态允许编辑，其他状态返回 `40920`。
- Repository 在写入前锁定当前 active 成员关系和目标 Hangout；校验、更新、提交处于同一事务，任一步失败都会回滚。
- 成功返回 `200 OK` 和更新后的约玩局响应。

本阶段不提供候选活动、候选时间、投票、开始投票、取消、确认活动、状态流转或 Event 创建接口。

### 约玩局错误码

| HTTP | 业务 code | 语义                                             |
| ---- | --------- | ------------------------------------------------ |
| 403  | `40320`   | 当前 active 成员不是约玩局创建者或群主           |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员             |
| 404  | `40420`   | 约玩局不存在、与路径群组不匹配或不可见           |
| 409  | `40920`   | 约玩局当前状态不允许修改                         |
| 422  | `42213`   | 分页 cursor 无效、被篡改、用途或群组作用域不匹配 |

字段格式、UUID 路径参数、未声明请求字段或 `limit` 校验失败继续使用通用 `422 / 40001`。

### 头像上传错误码

| HTTP | 业务 code | 语义                     |
| ---- | --------- | ------------------------ |
| 413  | `41301`   | 头像文件超过限制         |
| 415  | `41501`   | 头像文件类型不支持       |
| 422  | `42201`   | 文件不是可解码的有效图片 |
| 503  | `50303`   | 头像存储暂时不可用       |

### 认证错误码

| HTTP | 业务 code | 语义                               |
| ---- | --------- | ---------------------------------- |
| 401  | `40101`   | 微信临时 code 无效或过期           |
| 401  | `40102`   | access token 缺失、无效或过期      |
| 403  | `40301`   | User 已禁用                        |
| 403  | `40302`   | 微信风险策略拦截登录               |
| 503  | `50301`   | 微信服务繁忙、限额、超时或响应无效 |
| 503  | `50302`   | 后端未配置微信或 JWT 凭据          |

微信每分钟限额错误在可用时附带 `Retry-After: 60`。不向客户端透传微信原始 `errmsg`。
