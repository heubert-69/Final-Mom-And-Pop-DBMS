"""
oracledb 2.x thin mode notes:
- create_pool_async()  → returns pool synchronously (no await)
- pool.acquire()       → async context manager  ✓
- conn.cursor()        → sync, returns AsyncCursor when pool is async
- cursor.execute()     → must be awaited          ✓
- cursor.fetchone/all  → must be awaited          ✓
- cursor.callproc()    → must be awaited          ✓
- cursor.close()       → SYNC, do NOT await       ✓  ← common mistake
- conn.commit()        → must be awaited          ✓
- conn.rollback()      → must be awaited          ✓
"""
import oracledb
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from config import get_settings

settings = get_settings()
_pool: Optional[oracledb.AsyncConnectionPool] = None


def create_pool() -> oracledb.AsyncConnectionPool:
    """Synchronously creates the async connection pool (oracledb 2.x API)."""
    global _pool
    _pool = oracledb.create_pool_async(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
        min=2,
        max=10,
        increment=1,
    )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncGenerator[oracledb.AsyncConnection, None]:
    if _pool is None:
        raise RuntimeError("DB pool not initialised")
    async with _pool.acquire() as conn:
        yield conn


async def get_db():
    """FastAPI dependency — yields an async Oracle connection."""
    async with get_connection() as conn:
        yield conn
