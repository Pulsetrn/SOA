from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Flight(Base):
    __tablename__ = "flights"
    __table_args__ = (
        CheckConstraint("length(btrim(flight_number)) > 0", name="ck_flights_number"),
        CheckConstraint("length(btrim(airline)) > 0", name="ck_flights_airline"),
        CheckConstraint("origin ~ '^[A-Z]{3}$'", name="ck_flights_origin"),
        CheckConstraint("destination ~ '^[A-Z]{3}$'", name="ck_flights_destination"),
        CheckConstraint("origin <> destination", name="ck_flights_route"),
        CheckConstraint("arrival_time > departure_time", name="ck_flights_times"),
        CheckConstraint("total_seats > 0", name="ck_flights_total_seats"),
        CheckConstraint(
            "available_seats >= 0 AND available_seats <= total_seats",
            name="ck_flights_available_seats",
        ),
        CheckConstraint(
            "price > 0 AND price <> 'NaN'::numeric", name="ck_flights_price"
        ),
        Index(
            "uq_flights_number_departure_date",
            "flight_number",
            text("((departure_time AT TIME ZONE 'UTC')::date)"),
            unique=True,
        ),
        Index(
            "ix_flights_search",
            "origin",
            "destination",
            "status",
            "departure_time",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    flight_number: Mapped[str] = mapped_column(String(16))
    airline: Mapped[str] = mapped_column(String(255))
    origin: Mapped[str] = mapped_column(String(3))
    destination: Mapped[str] = mapped_column(String(3))
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_seats: Mapped[int] = mapped_column(Integer)
    available_seats: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(
        Enum("SCHEDULED", "DEPARTED", "CANCELLED", "COMPLETED", name="flight_status"),
        server_default="SCHEDULED",
    )


class SeatReservation(Base):
    __tablename__ = "seat_reservations"
    __table_args__ = (
        CheckConstraint("seat_count > 0", name="ck_reservations_seat_count"),
        Index("ix_reservations_flight", "flight_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    flight_id: Mapped[UUID] = mapped_column(
        ForeignKey("flights.id", ondelete="RESTRICT")
    )
    booking_id: Mapped[UUID] = mapped_column(unique=True)
    seat_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        Enum("ACTIVE", "RELEASED", "EXPIRED", name="reservation_status"),
        server_default="ACTIVE",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReleasedBooking(Base):
    __tablename__ = "released_booking_ids"

    booking_id: Mapped[UUID] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
