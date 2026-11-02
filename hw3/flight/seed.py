import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from common.database import Database
from sqlalchemy.dialects.postgresql import insert

from flight.models import Flight


async def seed():
    database = Database()
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    try:
        async with database.sessions() as session, session.begin():
            for number, seats, status in [
                (1, 20, "SCHEDULED"),
                (2, 2, "SCHEDULED"),
                (3, 10, "CANCELLED"),
            ]:
                statement = (
                    insert(Flight)
                    .values(
                        id=UUID(f"00000000-0000-4000-8000-{number:012d}"),
                        flight_number=f"SU100{number}",
                        airline="Aeroflot",
                        origin="SVO",
                        destination="LED",
                        departure_time=tomorrow + timedelta(hours=number),
                        arrival_time=tomorrow + timedelta(hours=number + 2),
                        total_seats=seats,
                        available_seats=seats,
                        price=Decimal("1250.50"),
                        status=status,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(statement)
        print("Demo flights available: SVO -> LED; IDs end with 001, 002, 003")
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed())
