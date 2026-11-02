from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(passenger_name)) > 0", name="ck_bookings_passenger_name"
        ),
        CheckConstraint(
            "length(btrim(passenger_email)) > 0", name="ck_bookings_passenger_email"
        ),
        CheckConstraint("seat_count > 0", name="ck_bookings_seat_count"),
        CheckConstraint(
            "total_price > 0 AND total_price <> 'NaN'::numeric",
            name="ck_bookings_total_price",
        ),
        Index("ix_bookings_user", "user_id", "created_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column()
    flight_id: Mapped[UUID] = mapped_column()
    passenger_name: Mapped[str] = mapped_column(String(255))
    passenger_email: Mapped[str] = mapped_column(String(254))
    seat_count: Mapped[int] = mapped_column(Integer)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(
        Enum("CONFIRMED", "CANCELLED", name="booking_status"),
        server_default="CONFIRMED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
