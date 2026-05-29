from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.project import Base

DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(DATABASE_URL, future=True, echo=True)
async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_async_session():
    """
    Dependency to get a database session.

    Yields:
        AsyncSession: The database session.
    """
    async with async_session_local() as session:
        yield session

async def init_db():
    """
    Initialize the database by creating all tables.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
