from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.schemas.user import UserRead

WeChatLoginCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]


class WeChatLoginRequest(BaseModel):
    code: WeChatLoginCode


class LoginData(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserRead
