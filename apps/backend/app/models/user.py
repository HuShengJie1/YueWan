from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import MYSQL_TABLE_OPTIONS, UTCDateTime


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("wechat_openid"),
        UniqueConstraint("wechat_unionid"),
        CheckConstraint("char_length(trim(wechat_openid)) > 0", name="wechat_openid_not_blank"),
        CheckConstraint("char_length(trim(display_name)) > 0", name="display_name_not_blank"),
        MYSQL_TABLE_OPTIONS,
    )

    wechat_openid: Mapped[str] = mapped_column(
        String(128, collation="utf8mb4_0900_bin"), nullable=False
    )
    wechat_unionid: Mapped[str | None] = mapped_column(String(128, collation="utf8mb4_0900_bin"))
    display_name: Mapped[str] = mapped_column(String(24), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    profile_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
