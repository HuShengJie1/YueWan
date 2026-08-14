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

生产小程序使用 `PUT /api/v1/users/me/avatar`：

```json
{
  "file_id": "cloud://prod-env.bucket/avatars/<user-id>/<timestamp>-<random>.jpg"
}
```

- 需要 Bearer Token，请求为 JSON。
- 小程序先校验图片并通过 `wx.cloud.uploadFile` 把最终文件写入当前用户自己的
  `avatars/<user-id>/` 目录，再通过 `callContainer` 提交完整 `file_id`。
- 后端只接受当前 CloudBase 环境、当前用户目录、时间戳加随机串命名的 `.jpg`/`.png` 文件；跨环境、
  跨用户、目录逃逸或格式错误的
  `file_id` 返回 `42202`。
- 后端不接收客户端 URL，也不读取对象内容；验证 `file_id` 后使用服务端配置拼接最终 HTTPS CDN 地址。
- 请求失败时小程序尽力删除刚上传的文件；数据库更新成功后，再尽力删除上一张符合当前客户端命名规则的头像。
- 客户端直接上传是当前 MVP 的无密钥方案。文件存在性、真实内容和大小不由该 PUT 接口重新验证；存储权限、
  受限路径和“用户只能修改自己的头像资料”共同构成服务端边界。

本地后端调试继续支持 `POST /api/v1/users/me/avatar`：

- 需要 Bearer Token，请求为 `multipart/form-data`。
- 文件字段名固定为 `file`，限 JPEG、PNG 或 WebP，最大 5 MiB。
- 成功返回 `200 OK`，`data` 为更新后的 `user` 对象，其 `avatar_url` 为可持久访问的地址；本地开发可使用
  HTTP，真机和生产使用 CloudBase CDN 的 HTTPS 地址。
- 本地 multipart 调试由后端重新校验真实文件类型、大小和图片可解码性。
- 后端忽略客户端文件名和声明的 MIME 类型，以实际图片内容为准；图片按 EXIF 方向纠正，最长边缩放到 512 px，去除元数据并统一编码为 JPEG。
- 微信 `chooseAvatar` 返回的本地临时路径和 CloudBase `file_id` 都不进入 User 响应或数据库。

前端选择头像后会立即调用该接口；上传成功后才将服务端返回的 URL 写入会话用户。

头像相关错误码：

| HTTP | 业务 code | 语义 |
| ---- | --------- | ---- |
| 413 | `41301` | 本地接口或小程序预检发现图片超过大小/像素限制 |
| 415 | `41501` | 本地接口格式不是 JPEG/PNG/WebP，或生产小程序格式不是 JPEG/PNG |
| 422 | `42201` | 本地接口或小程序预检无法识别图片 |
| 422 | `42202` | CloudBase 文件引用不属于当前环境、当前用户或受管命名规则 |
| 503 | `50303` | 当前头像存储模式缺少必要配置或不可用 |

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

本阶段已提供从 `draft` 开启 `voting`、投票和手动确认 Event 的闭环。取消及 `cancelled/finished` 状态流转仍未实现。

### 约玩局错误码

| HTTP | 业务 code | 语义                                             |
| ---- | --------- | ------------------------------------------------ |
| 403  | `40320`   | 当前 active 成员不是约玩局创建者或群主           |
| 403  | `40321`   | 当前 active 成员不能开启该约玩局投票             |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员             |
| 404  | `40420`   | 约玩局不存在、与路径群组不匹配或不可见           |
| 409  | `40920`   | 约玩局当前状态不允许修改                         |
| 409  | `40921`   | 约玩局没有 Proposal，不能开启投票                   |
| 409  | `40922`   | 约玩局没有 TimeOption，不能开启投票                 |
| 409  | `40923`   | 开启投票时 `voting_deadline` 已到期                    |
| 422  | `42213`   | 分页 cursor 无效、被篡改、用途或群组作用域不匹配 |

字段格式、UUID 路径参数、未声明请求字段或 `limit` 校验失败继续使用通用 `422 / 40001`。

## 候选活动 Proposal 契约

以下接口均需要 Bearer Token：

- `POST /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals`
- `GET /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals?cursor=&limit=`
- `PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}`
- `DELETE /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}`

创建和完整更新使用相同的可写字段：

```json
{
  "title": "桌游店",
  "description": "可以提前订包间",
  "location_text": "徐汇区某商场 5 楼",
  "external_platform": "official",
  "external_url": "https://example.com/venues/42",
  "external_data": {
    "source_id": "42",
    "category": "board_game"
  }
}
```

- `title` 去除首尾空白后长度为 1–80。
- `description`、`location_text`、`external_platform` 均可为 `null`；去除首尾空白后最大长度分别为 500、200、50，空白转换为 `null`。
- `external_url` 可为 `null`，去除首尾空白后最长 2048；存在时必须是带主机名且不内嵌用户名或密码的 HTTP/HTTPS URL。
- `external_data` 可为 JSON object 或 `null`。任何层级都不得包含 token、password、secret、authorization、cookie、session key、API key 或 credential 等认证/秘密字段。
- `hangout_id`、`submitted_by_user_id`、ID、时间戳和 `can_manage` 由服务端决定；请求携带这些字段或其他未声明字段返回通用 `422 / 40001`。

成功创建返回 `201 Created` 和 `Location`；成功更新返回 `200 OK`。两者 `data` 示例：

```json
{
  "id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "hangout_id": "62429e4e-24cf-495c-b223-f63891147cf7",
  "submitted_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
  "title": "桌游店",
  "description": "可以提前订包间",
  "location_text": "徐汇区某商场 5 楼",
  "external_platform": "official",
  "external_url": "https://example.com/venues/42",
  "external_data": {
    "source_id": "42",
    "category": "board_game"
  },
  "created_at": "2026-08-11T03:00:00Z",
  "updated_at": "2026-08-11T03:00:00Z",
  "can_manage": true
}
```

权限和状态规则：

- 只有群组 active 成员可读取或创建；群组不存在、left 或非成员统一返回 `40410`。
- Hangout 必须属于路径 Group，否则返回 `40420`；Proposal 必须属于路径 Hangout，否则返回 `40430`。
- 只有 Proposal 提交者、Hangout 创建者或群主可更新、删除；其他 active 成员返回 `40330`。
- 只有 `Hangout.status=draft` 可以创建、更新或删除；其他状态明确返回 `40930`。
- `can_manage` 表示当前状态下当前用户能否管理，用于前端展示；非 `draft` 时固定为 `false`。写请求仍由服务端重新锁定资源并鉴权，不能信任该字段。
- 写入按 active 成员关系、Hangout、目标 Proposal 的顺序加锁，在同一事务内校验并提交；创建没有既存目标资源可锁。失败会 rollback，成功删除为硬删除并返回无响应体的 `204 No Content`。

Proposal 列表按 `created_at DESC, id DESC` 稳定分页，`limit` 默认 20、范围 1–100。cursor 是签名不透明值，同时绑定 `proposal_list` 用途、`group_id` 和 `hangout_id`；不能跨列表、Group 或 Hangout 复用，无效值返回 `42213`。响应使用标准 CursorPage envelope，列表权限上下文通过固定数量查询取得，不逐候选查询。

### Proposal 错误码

| HTTP | 业务 code | 语义                                                   |
| ---- | --------- | ------------------------------------------------------ |
| 403  | `40330`   | 当前 active 成员不能管理该 Proposal                    |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员                   |
| 404  | `40420`   | Hangout 不存在、与路径 Group 不匹配或不可见            |
| 404  | `40430`   | Proposal 不存在或与路径 Hangout 不匹配                 |
| 409  | `40930`   | Hangout 状态不允许新增、更新或删除 Proposal            |
| 422  | `42213`   | 分页 cursor 无效、被篡改、用途或 Group/Hangout 不匹配  |

字段校验、UUID 路径参数、未声明字段或 `limit` 校验失败继续使用通用 `422 / 40001`。

## 候选时间 TimeOption 契约

以下接口均需要 Bearer Token：

- `POST /api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options`
- `GET /api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options?cursor=&limit=`
- `PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options/{time_option_id}`
- `DELETE /api/v1/groups/{group_id}/hangouts/{hangout_id}/time-options/{time_option_id}`

创建和完整更新请求：

```json
{
  "starts_at": "2026-08-15T12:00:00Z",
  "ends_at": "2026-08-15T14:00:00Z",
  "display_label": "周六晚上"
}
```

- `starts_at` 必填，必须带时区，并在请求和事务写入校验时均晚于当前时间；写入前转换为 UTC。
- `ends_at` 可为 `null`；存在时必须带时区、转换为 UTC 且严格晚于 `starts_at`。
- `display_label` 可为 `null`，去除首尾空白后最长 80；空字符串或纯空白转换为 `null`。
- `hangout_id`、`created_by_user_id`、ID、时间戳和 `can_manage` 由服务端决定；请求携带这些字段或其他未声明字段返回通用 `422 / 40001`。

成功创建返回 `201 Created` 和 `Location`；成功更新返回 `200 OK`。两者 `data` 示例：

```json
{
  "id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "hangout_id": "62429e4e-24cf-495c-b223-f63891147cf7",
  "created_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
  "starts_at": "2026-08-15T12:00:00Z",
  "ends_at": "2026-08-15T14:00:00Z",
  "display_label": "周六晚上",
  "created_at": "2026-08-11T03:00:00Z",
  "updated_at": "2026-08-11T03:00:00Z",
  "can_manage": true
}
```

权限、资源隐藏、状态限制、加锁顺序、事务回滚、硬删除和 `can_manage` 语义与 Proposal 相同；管理者为 TimeOption 创建者、Hangout 创建者或群主。非管理者返回 `40340`，非 `draft` 写入返回 `40940`。

TimeOption 列表按 `starts_at ASC, id ASC` 稳定分页，`limit` 默认 20、范围 1–100。cursor 同时绑定 `time_option_list` 用途、`group_id` 和 `hangout_id`，不能与 Proposal 或其他列表互换；无效值返回 `42213`。响应使用标准 CursorPage envelope。

### TimeOption 错误码

| HTTP | 业务 code | 语义                                                    |
| ---- | --------- | ------------------------------------------------------- |
| 403  | `40340`   | 当前 active 成员不能管理该 TimeOption                   |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员                    |
| 404  | `40420`   | Hangout 不存在、与路径 Group 不匹配或不可见             |
| 404  | `40440`   | TimeOption 不存在或与路径 Hangout 不匹配                |
| 409  | `40940`   | Hangout 状态不允许新增、更新或删除 TimeOption           |
| 422  | `42213`   | 分页 cursor 无效、被篡改、用途或 Group/Hangout 不匹配   |

时间、字段格式、UUID 路径参数、未声明字段或 `limit` 校验失败继续使用通用 `422 / 40001`。

## 开启投票与投票契约

以下接口均需要 Bearer Token，路径作用域固定为当前 Group 下的当前 Hangout。群组不存在或当前用户不是 active 成员统一返回 `40410`；Hangout 不存在、跨 Group 或不可见统一返回 `40420`。当前 MVP 向所有 active 成员展示实时票数。

### 开启投票

`PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/voting`

- 请求无 body；客户端不提交 Hangout 状态、用户 ID 或票数。
- 只有约玩局创建者或群主可以开启；其他 active 成员返回 `40321`。
- 只能从 `draft` 开启；已是 `voting` 或其他状态返回 `40920`。
- 开启前至少要有 1 个 Proposal 和 1 个 TimeOption，否则分别返回 `40921` 和 `40922`。
- `voting_deadline=null` 表示没有自动截止时间；存在时必须在事务校验时仍严格晚于当前时间，否则返回 `40923`。
- Repository 按当前 active GroupMember、Hangout 的顺序加锁。状态检查、候选计数与 `status=voting` 写入处于同一事务。Proposal/TimeOption 写入也必须先获取同一 Hangout 行锁，因此候选变更与开启投票之间不存在竞态窗口。
- 进入 `voting` 后 Proposal 和 TimeOption 继续可读，但新增、更新和删除均按原契约返回 `40930` 或 `40940`。
- 成功返回 `200 OK`，`data` 为更新后的约玩局响应，其 `status` 为 `voting`。

### 投票摘要

`GET /api/v1/groups/{group_id}/hangouts/{hangout_id}/votes`

- 任何 active 群组成员可读。摘要可在 Hangout 任意状态读取；`status` 和 `voting_deadline` 告诉客户端当前是否可写票，最终可写性仍由服务端重新校验。
- Proposal 和 TimeOption 都在服务端稳定排序：Proposal 按 `created_at DESC, id DESC`，TimeOption 按 `starts_at ASC, id ASC`。
- 票数和当前用户选择使用每种候选一次批量聚合查询，不逐候选查询。计数以已成功写入的投票记录为准。

成功响应的 `data`：

```json
{
  "hangout_id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "status": "voting",
  "voting_deadline": "2026-08-15T12:00:00Z",
  "proposals": [
    {
      "id": "62429e4e-24cf-495c-b223-f63891147cf7",
      "submitted_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
      "title": "桌游店",
      "description": null,
      "location_text": "徐汇区某商场 5 楼",
      "external_platform": null,
      "external_url": null,
      "external_data": null,
      "created_at": "2026-08-11T03:00:00Z",
      "updated_at": "2026-08-11T03:00:00Z",
      "vote_counts": {
        "LIKE": 2,
        "OK": 1,
        "DISLIKE": 0
      },
      "current_user_vote": "LIKE"
    }
  ],
  "time_options": [
    {
      "id": "a377ae4f-37d2-48ad-9e18-f8b61cba1f93",
      "created_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
      "starts_at": "2026-08-16T10:00:00Z",
      "ends_at": "2026-08-16T12:00:00Z",
      "display_label": "周日晚上",
      "created_at": "2026-08-11T03:05:00Z",
      "updated_at": "2026-08-11T03:05:00Z",
      "availability_count": 2,
      "current_user_selected": true
    }
  ]
}
```

### 活动投票

- 创建或覆盖当前用户对单个 Proposal 的选择：`PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}/vote`
- 撤销当前用户对该 Proposal 的选择：`DELETE /api/v1/groups/{group_id}/hangouts/{hangout_id}/proposals/{proposal_id}/vote`

PUT 请求：

```json
{
  "value": "LIKE"
}
```

- `value` 只能是 `LIKE`、`OK` 或 `DISLIKE`；不区分创建和覆盖，成功均返回 `200 OK`。
- 当前用户对同一 Proposal 最多一票。PUT 使用数据库唯一约束和原子 upsert；重复提交同一值幂等，提交不同值覆盖原值，不会产生重复记录。
- Proposal 必须属于路径 Hangout；缺失或跨 Hangout 统一返回 `40430`。
- DELETE 在当前用户已无该票时仍幂等成功。PUT 和 DELETE 的 `data` 均返回上述单个 Proposal 摘要，包含操作后的实时计数和 `current_user_vote`。

### 时间多选

`PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/time-votes/me`

请求：

```json
{
  "time_option_ids": [
    "a377ae4f-37d2-48ad-9e18-f8b61cba1f93",
    "414426de-ff53-4838-8084-c98a19acaed5"
  ]
}
```

- 一次请求原子替换当前用户在该 Hangout 下的全部时间选择；不在新数组中的旧选择被删除，空数组表示全部清空。
- 服务端在删除任何旧票前，先校验数组中的全部 ID。任意 ID 不存在或属于其他 Hangout 均返回 `40440`，不改变原选择。
- 数组不允许重复 ID，否则返回 `42250`；完全相同的非重复数组可重复提交并幂等成功。
- 成功返回 `200 OK`，`data.time_options` 为该 Hangout 的全部 TimeOption 摘要，包含替换后的实时可用人数与当前用户选择。

### 写票状态、事务与错误码

- ProposalVote 和 TimeVote 只允许在 `status=voting` 且 `voting_deadline` 为 `null` 或事务校验时仍严格晚于当前时间时写入。非 `voting` 或已到截止时间统一返回 `40950`。
- 写票按当前 active GroupMember、Hangout 的固定顺序加锁，同一用户的并发写入被其 GroupMember 行串行化；Hangout 使用共享行锁，允许不同成员并发投票，同时与后续状态变更形成边界。
- 校验、写入、聚合结果读取和 commit 处于同一事务；任一步失败都 rollback。唯一约束或其他数据库完整性冲突只返回安全业务错误，不泄露 SQL、约束名或堆栈。

| HTTP | 业务 code | 语义                                                     |
| ---- | --------- | -------------------------------------------------------- |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员                   |
| 404  | `40420`   | Hangout 不存在、与路径 Group 不匹配或不可见              |
| 404  | `40430`   | Proposal 不存在或与路径 Hangout 不匹配                |
| 404  | `40440`   | TimeOption 不存在或与路径 Hangout 不匹配              |
| 409  | `40950`   | Hangout 未开放投票、已过截止时间或写票数据库冲突 |
| 422  | `42250`   | `time_option_ids` 包含重复 ID                          |

`value` 枚举、JSON 字段、UUID 路径参数或未声明字段校验失败继续使用通用 `422 / 40001`。

## 手动确认 Event 契约

以下接口均需要 Bearer Token：

- `PUT /api/v1/groups/{group_id}/hangouts/{hangout_id}/event`
- `GET /api/v1/groups/{group_id}/hangouts/{hangout_id}/event`

投票摘要只提供数据参考，后端不自动计算或选择获胜者。约玩局创建者或 active 群主必须手动选择一个 Proposal 和一个 TimeOption。

### 确认 Event

PUT 请求：

```json
{
  "proposal_id": "62429e4e-24cf-495c-b223-f63891147cf7",
  "time_option_id": "a377ae4f-37d2-48ad-9e18-f8b61cba1f93"
}
```

- 当前用户必须是 active 群组成员，并且是 Hangout 创建者或 active 群主；普通 active 成员返回 `40350`。
- 首次确认只允许从 `status=voting` 进行，是否已经到 `voting_deadline` 不阻止负责人确认，因此也允许在截止时间前提前确认。其他状态首次确认返回 `40960`。
- Proposal 和 TimeOption 必须都属于路径 Hangout；不存在或跨 Hangout 分别返回不会泄露其他作用域资源的 `40430` 和 `40440`。
- Event 快照复制 Proposal 的 `title`、`description`、`location_text`，以及 TimeOption 的 `starts_at`、`ends_at`；同时保存两个候选 ID 和当前确认用户 ID。
- Repository 按当前 active GroupMember、Hangout 的顺序获取排他锁。Event 创建、`Hangout.status=confirmed` 和 `confirmed_at` 在同一事务中提交；失败整体回滚。Hangout 锁将并发确认串行化，数据库的 `events.hangout_id` 唯一约束保证每个 Hangout 最多一个 Event。
- 已确认后用相同 `proposal_id` 和 `time_option_id` 重复 PUT 会幂等返回原 Event；任一选择不同返回 `40961`，不会覆盖 Event。
- 确认成功后 Hangout 立即成为 `confirmed`。投票摘要仍可 GET；现有活动投票和时间投票写接口统一返回 `40950`。

成功返回 `200 OK`，统一 envelope 的 `data`：

```json
{
  "id": "71e0ef1c-0a08-4561-b061-52f4dd997621",
  "hangout_id": "5b017070-0501-4b76-99dc-3aa57bc395ca",
  "proposal_id": "62429e4e-24cf-495c-b223-f63891147cf7",
  "time_option_id": "a377ae4f-37d2-48ad-9e18-f8b61cba1f93",
  "confirmed_by_user_id": "28a03322-3016-4142-b762-44ce83c5f1c1",
  "title": "桌游店",
  "description": "可以提前订包间",
  "location_text": "徐汇区某商场 5 楼",
  "starts_at": "2026-08-16T10:00:00Z",
  "ends_at": "2026-08-16T12:00:00Z",
  "created_at": "2026-08-12T03:00:00Z",
  "updated_at": "2026-08-12T03:00:00Z"
}
```

### 读取 Event

- 任何 active 群组成员都可以读取已确认 Event。
- 群组不存在、非成员或 left 成员返回 `40410`；Hangout 不存在、跨 Group 或不可见返回 `40420`。
- 路径作用域有效但尚无 Event 时返回 `40450`。不会通过该接口确认其他 Group/Hangout/Event 是否存在。
- 成功返回 `200 OK`，`data` 与上述 Event 结构相同。候选引用在数据库中允许因未来删除而变为 `null`，Event 快照不受影响。

### Event 错误码

| HTTP | 业务 code | 语义                                                   |
| ---- | --------- | ------------------------------------------------------ |
| 403  | `40350`   | 当前 active 成员不是 Hangout 创建者或群主              |
| 404  | `40410`   | 群组不存在或当前用户不是 active 成员                   |
| 404  | `40420`   | Hangout 不存在、与路径 Group 不匹配或不可见            |
| 404  | `40430`   | Proposal 不存在或与路径 Hangout 不匹配                 |
| 404  | `40440`   | TimeOption 不存在或与路径 Hangout 不匹配               |
| 404  | `40450`   | 路径作用域有效但 Event 不存在                           |
| 409  | `40960`   | Hangout 状态或数据库完整性不允许首次确认 Event          |
| 409  | `40961`   | Event 已使用不同 Proposal 或 TimeOption 确认            |

JSON 字段、UUID 路径参数或未声明字段校验失败继续使用通用 `422 / 40001`。所有错误消息隐藏 SQL、约束名、堆栈和其他作用域资源的存在性。

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
