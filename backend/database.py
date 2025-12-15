"""
Database Connection and Session Management

Provides async database engine and session factory for SQLModel.
Uses Neon PostgreSQL with connection pooling.
"""

from typing import AsyncGenerator, Optional
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker

from backend.settings import settings


def get_async_database_url(url: str) -> str:
    """
    Convert standard PostgreSQL URL to asyncpg format.
    
    Neon provides: postgresql://user:pass@host/db
    We need:       postgresql+asyncpg://user:pass@host/db
    """
    if not url:
        return ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Convert URL for async driver
async_database_url = get_async_database_url(settings.DATABASE_URL)

# Create async engine with Neon PostgreSQL (lazy - only if URL is provided)
engine: Optional[AsyncEngine] = None
async_session_maker = None

if async_database_url:
    engine = create_async_engine(
        async_database_url,
        echo=settings.DEBUG,  # Log SQL in debug mode
        pool_pre_ping=True,   # Verify connections before use
        pool_size=5,          # Connection pool size
        max_overflow=10,      # Additional connections when pool is full
    )
    
    # Async session factory
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints.
    
    Usage:
        @app.get("/sessions")
        async def list_sessions(db: AsyncSession = Depends(get_session)):
            ...
    """
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Set DATABASE_URL in .env")
    
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    """
    Create all tables in the database.
    
    Call this on application startup.
    """
    if engine is None:
        raise RuntimeError("Database not initialized. Set DATABASE_URL in .env")
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_tables():
    """
    Drop all tables (use with caution!).
    
    Useful for development/testing.
    """
    if engine is None:
        raise RuntimeError("Database not initialized. Set DATABASE_URL in .env")
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
