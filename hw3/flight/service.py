import re
from datetime import timedelta, timezone
from decimal import Decimal
from uuid import UUID

import flight_pb2 as pb
import flight_pb2_grpc as rpc
import grpc
from google.protobuf.empty_pb2 import Empty
from sqlalchemy import select, text

from flight.models import Flight, ReleasedBooking, SeatReservation


class BusinessError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message


def uuid_value(value):
    try:
        return UUID(value)
    except ValueError:
        raise BusinessError(
            grpc.StatusCode.INVALID_ARGUMENT, "Expected a UUID"
        ) from None


def flight_message(row):
    result = pb.Flight(
        id=str(row.id),
        flight_number=row.flight_number,
        airline=row.airline,
        origin=row.origin,
        destination=row.destination,
        total_seats=row.total_seats,
        available_seats=row.available_seats,
        price_minor=int(row.price * 100),
        status=pb.FlightStatus.Value(f"FLIGHT_STATUS_{row.status}"),
    )
    result.departure_time.FromDatetime(row.departure_time)
    result.arrival_time.FromDatetime(row.arrival_time)
    return result


def reservation_message(row):
    return pb.SeatReservation(
        id=str(row.id),
        flight_id=str(row.flight_id),
        booking_id=str(row.booking_id),
        seat_count=row.seat_count,
        status=pb.ReservationStatus.Value(f"RESERVATION_STATUS_{row.status}"),
    )


async def lock_booking(session, booking_id):
    key = booking_id.int % (2**63)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


class FlightService(rpc.FlightServiceServicer):
    def __init__(self, database, cache):
        self.database = database
        self.cache = cache

    async def SearchFlights(self, request, context):
        if not all(
            re.fullmatch(r"[A-Z]{3}", value)
            for value in (request.origin, request.destination)
        ):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "Expected IATA airport codes"
            )
        if request.origin == request.destination:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "Airports must differ"
            )
        query = select(Flight).where(
            Flight.origin == request.origin,
            Flight.destination == request.destination,
            Flight.status == "SCHEDULED",
        )
        if request.HasField("departure_date"):
            try:
                start = request.departure_date.ToDatetime(tzinfo=timezone.utc)
                if (
                    start.hour
                    or start.minute
                    or start.second
                    or request.departure_date.nanos
                ):
                    raise ValueError
                end = start + timedelta(days=1)
            except (ValueError, OverflowError):
                await context.abort(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "Expected midnight UTC departure date",
                )
            query = query.where(
                Flight.departure_time >= start, Flight.departure_time < end
            )
        date_key = (
            start.date().isoformat() if request.HasField("departure_date") else "all"
        )
        key = self.cache.key(
            f"search:{request.origin}:{request.destination}:{date_key}"
        )
        cached = await self.cache.get(key, pb.SearchFlightsResponse)
        if cached is not None:
            return cached
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(query.order_by(Flight.departure_time, Flight.id))
            ).all()
            result = pb.SearchFlightsResponse(
                flights=[flight_message(row) for row in rows]
            )
        await self.cache.put(key, result)
        return result

    async def GetFlight(self, request, context):
        try:
            flight_id = uuid_value(request.flight_id)
            key = self.cache.key(f"flight:{flight_id}")
            cached = await self.cache.get(key, pb.Flight)
            if cached is not None:
                return cached
            async with self.database.sessions() as session:
                row = await session.get(Flight, flight_id)
                if row is None:
                    raise BusinessError(grpc.StatusCode.NOT_FOUND, "Flight not found")
                result = flight_message(row)
            await self.cache.put(key, result)
            return result
        except BusinessError as error:
            await context.abort(error.code, error.message)

    async def UpdateFlight(self, request, context):
        try:
            flight_id = uuid_value(request.flight_id)
            if not (request.HasField("price_minor") or request.HasField("status")):
                raise BusinessError(
                    grpc.StatusCode.INVALID_ARGUMENT, "Expected price_minor or status"
                )
            if request.HasField("price_minor") and not (
                0 < request.price_minor <= 999999999999
            ):
                raise BusinessError(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "price_minor must be between 1 and 999999999999",
                )
            if request.HasField("status") and request.status not in (
                pb.FLIGHT_STATUS_SCHEDULED,
                pb.FLIGHT_STATUS_DEPARTED,
                pb.FLIGHT_STATUS_CANCELLED,
                pb.FLIGHT_STATUS_COMPLETED,
            ):
                raise BusinessError(
                    grpc.StatusCode.INVALID_ARGUMENT, "Expected a valid flight status"
                )
            async with self.database.sessions() as session, session.begin():
                flight = await session.get(Flight, flight_id, with_for_update=True)
                if flight is None:
                    raise BusinessError(grpc.StatusCode.NOT_FOUND, "Flight not found")
                if request.HasField("price_minor"):
                    flight.price = Decimal(request.price_minor) / 100
                if request.HasField("status"):
                    flight.status = pb.FlightStatus.Name(request.status).removeprefix(
                        "FLIGHT_STATUS_"
                    )
                await session.flush()
                result = flight_message(flight)
            self.cache.invalidate()
            return result
        except BusinessError as error:
            await context.abort(error.code, error.message)

    async def ReserveSeats(self, request, context):
        try:
            flight_id, booking_id = (
                uuid_value(request.flight_id),
                uuid_value(request.booking_id),
            )
            if request.seat_count <= 0:
                raise BusinessError(
                    grpc.StatusCode.INVALID_ARGUMENT, "seat_count must be positive"
                )
            async with self.database.sessions() as session, session.begin():
                await lock_booking(session, booking_id)
                if await session.get(ReleasedBooking, booking_id) is not None:
                    raise BusinessError(
                        grpc.StatusCode.FAILED_PRECONDITION,
                        "Reservation already released",
                    )
                existing = await session.scalar(
                    select(SeatReservation).where(
                        SeatReservation.booking_id == booking_id
                    )
                )
                if existing is not None:
                    if (
                        existing.flight_id != flight_id
                        or existing.seat_count != request.seat_count
                    ):
                        raise BusinessError(
                            grpc.StatusCode.ALREADY_EXISTS,
                            "booking_id has different reservation parameters",
                        )
                    if existing.status != "ACTIVE":
                        raise BusinessError(
                            grpc.StatusCode.FAILED_PRECONDITION,
                            "Reservation is not active",
                        )
                    return reservation_message(existing)
                flight = await session.get(Flight, flight_id, with_for_update=True)
                if flight is None:
                    raise BusinessError(grpc.StatusCode.NOT_FOUND, "Flight not found")
                if flight.status != "SCHEDULED":
                    raise BusinessError(
                        grpc.StatusCode.FAILED_PRECONDITION, "Flight is not scheduled"
                    )
                if flight.available_seats < request.seat_count:
                    raise BusinessError(
                        grpc.StatusCode.RESOURCE_EXHAUSTED, "Insufficient seats"
                    )
                flight.available_seats -= request.seat_count
                reservation = SeatReservation(
                    flight_id=flight_id,
                    booking_id=booking_id,
                    seat_count=request.seat_count,
                    status="ACTIVE",
                )
                session.add(reservation)
                await session.flush()
                result = reservation_message(reservation)
            self.cache.invalidate()
            return result
        except BusinessError as error:
            await context.abort(error.code, error.message)

    async def ReleaseReservation(self, request, context):
        try:
            booking_id = uuid_value(request.booking_id)
            changed = False
            async with self.database.sessions() as session, session.begin():
                await lock_booking(session, booking_id)
                if await session.get(ReleasedBooking, booking_id) is not None:
                    return Empty()
                reservation = await session.scalar(
                    select(SeatReservation).where(
                        SeatReservation.booking_id == booking_id
                    )
                )
                if reservation is not None and reservation.status == "ACTIVE":
                    flight = await session.get(
                        Flight, reservation.flight_id, with_for_update=True
                    )
                    flight.available_seats += reservation.seat_count
                    reservation.status = "RELEASED"
                    changed = True
                session.add(ReleasedBooking(booking_id=booking_id))
            if changed:
                self.cache.invalidate()
            return Empty()
        except BusinessError as error:
            await context.abort(error.code, error.message)
