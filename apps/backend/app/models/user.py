from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("wechat_openid"),
        UniqueConstraint("wechat_unionid"),
        CheckConstraint("length(btrim(wechat_openid)) > 0", name="wechat_openid_not_blank"),
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_not_blank"),
    )

    wechat_openid: Mapped[str] = mapped_column(Text, nullable=False)
    wechat_unionid: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    profile_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
