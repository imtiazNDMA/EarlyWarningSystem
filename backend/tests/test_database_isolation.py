"""Tests that database state does not leak between tests."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class TestDatabaseIsolation:
    """Both tests create the same table, so leaked state fails the second one."""

    async def create_probe(self, session: AsyncSession) -> int:
        """Create a table, commit a row, and return the row count."""
        await session.execute(text("CREATE TABLE isolation_probe (id int)"))
        await session.execute(text("INSERT INTO isolation_probe VALUES (1)"))
        await session.commit()
        result = await session.execute(text("SELECT count(*) FROM isolation_probe"))
        return int(result.scalar_one())

    async def test_first_writer_sees_only_its_own_row(
        self, db_session: AsyncSession
    ) -> None:
        assert await self.create_probe(db_session) == 1

    async def test_second_writer_sees_only_its_own_row(
        self, db_session: AsyncSession
    ) -> None:
        assert await self.create_probe(db_session) == 1
