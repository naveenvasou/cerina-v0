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


# --- Checkpointer (global singleton) ---
checkpointer = None


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


async def init_checkpointer():
    """
    Initialize the LangGraph checkpointer.
    
    Uses PostgresSaver when DATABASE_URL is set, falls back to MemorySaver.
    Call this on application startup AFTER create_tables().
    """
    global checkpointer, _checkpointer_context
    
    if settings.DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        
        # PostgresSaver uses psycopg3, not asyncpg
        db_url = settings.DATABASE_URL
        
        print("🔄 Initializing PostgreSQL checkpointer...")
        
        # from_conn_string returns an async context manager
        # We need to enter it manually and keep it open for the app lifetime
        _checkpointer_context = AsyncPostgresSaver.from_conn_string(db_url)
        checkpointer = await _checkpointer_context.__aenter__()
        
        # Setup creates the checkpoint tables if needed
        await checkpointer.setup()
        print("✅ PostgreSQL checkpointer ready")
    else:
        from langgraph.checkpoint.memory import MemorySaver
        
        print("⚠️ No DATABASE_URL - using in-memory checkpointer (state lost on restart)")
        checkpointer = MemorySaver()
        _checkpointer_context = None


# Store the context manager so we can close it on shutdown
_checkpointer_context = None


async def close_checkpointer():
    """
    Close the checkpointer connection.
    
    Call this on application shutdown.
    """
    global checkpointer, _checkpointer_context
    
    if _checkpointer_context is not None:
        print("🔄 Closing PostgreSQL checkpointer...")
        await _checkpointer_context.__aexit__(None, None, None)
        print("✅ Checkpointer closed")
    
    checkpointer = None
    _checkpointer_context = None


def get_checkpointer():
    """Get the global checkpointer instance."""
    if checkpointer is None:
        # Fallback during early import or no DB
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
    return checkpointer


