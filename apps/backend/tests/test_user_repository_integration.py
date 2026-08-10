import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine
from app.repositories.user import UserRepository

pytestmark = [
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="set RUN_DATABASE_TESTS=1 when a migrated PostgreSQL test database is available",
    ),
    pytest.mark.asyncio(loop_scope="session"),
]


async def test_wechat_user_upsert_is_idempotent_in_postgresql() -> None:
    identity_suffix = uuid4().hex
    first_login = datetime(2026, 8, 9, 3, 0, tzinfo=UTC)
    second_login = first_login + timedelta(minutes=5)

    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        try:
            async with AsyncSession(
                bind=connection,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            ) as session:
                repository = UserRepository(session)
                first_user = await repository.upsert_wechat_user(
                    openid=f"test-openid-{identity_suffix}",
                    unionid=None,
                    logged_in_at=first_login,
                )
                await repository.commit()

                repeated_user = await repository.upsert_wechat_user(
                    openid=f"test-openid-{identity_suffix}",
                    unionid=f"test-unionid-{identity_suffix}",
                    logged_in_at=second_login,
                )
                await repository.commit()

                assert repeated_user.id == first_user.id
                assert repeated_user.wechat_unionid == f"test-unionid-{identity_suffix}"
                assert repeated_user.last_login_at == second_login
                assert repeated_user.is_active
                assert not repeated_user.profile_completed
        finally:
            await outer_transaction.rollback()
