"""Shared pytest fixtures for RET v4 backend tests."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Set test env before importing app modules
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_db():
    """Provide an in-memory async SQLAlchemy session for each test."""
    from api.models.models import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(async_db: AsyncSession):
    """Create a test user in the DB and return it."""
    from api.models.models import User
    from api.core.security import hash_password

    user = User(
        username="testuser",
        password_hash=hash_password("TestPass1!"),
        role="user",
        is_active=True,
        is_locked=False,
        failed_login_attempts=0,
    )
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(async_db: AsyncSession):
    """Create an admin user in the DB and return it."""
    from api.models.models import User
    from api.core.security import hash_password

    user = User(
        username="admin",
        password_hash=hash_password("AdminPass1!"),
        role="admin",
        is_active=True,
        is_locked=False,
        failed_login_attempts=0,
    )
    async_db.add(user)
    await async_db.commit()
    await async_db.refresh(user)
    return user
