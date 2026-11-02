import logging
from contextlib import asynccontextmanager
from datetime import date as Date
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import grpc
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from booking.client import FlightClient, flight_response
from booking.models import Booking
from booking.schemas import BookingCreate, BookingResponse, FlightResponse
from common.database import Database

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status = status
        self.code = code
        self.message = message


@asynccontextmanager
async def lifespan(app):
    database = Database()
    client = FlightClient()
    app.state.database = database
    app.state.flights = client
    try:
        await database.check()
        yield
    finally:
        await client.close()
        await database.close()


app = FastAPI(title="Flight Booking", version="0.1.0", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error(request, error):
    return JSONResponse(
        status_code=error.status,
        content={"error_code": error.code, "message": error.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    details = [
        {"field": ".".join(map(str, item["loc"])), "message": item["msg"]}
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "INVALID_ARGUMENT",
            "message": "Invalid request",
            "details": details,
        },
    )


@app.exception_handler(grpc.aio.AioRpcError)
async def grpc_error(request, error):
    statuses = {
        grpc.StatusCode.INVALID_ARGUMENT: 400,
        grpc.StatusCode.NOT_FOUND: 404,
        grpc.StatusCode.RESOURCE_EXHAUSTED: 409,
        grpc.StatusCode.FAILED_PRECONDITION: 409,
        grpc.StatusCode.ALREADY_EXISTS: 409,
        grpc.StatusCode.UNAVAILABLE: 503,
        grpc.StatusCode.DEADLINE_EXCEEDED: 504,
        grpc.StatusCode.UNAUTHENTICATED: 503,
    }
    return JSONResponse(
        status_code=statuses.get(error.code(), 502),
        content={
            "error_code": error.code().name,
            "message": error.details() or "Flight Service error",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logger.error("Booking database operation failed", exc_info=error)
    return JSONResponse(
        status_code=503,
        content={
            "error_code": "DATABASE_UNAVAILABLE",
            "message": "Booking database operation failed",
        },
    )


@app.get("/health")
async def health(request: Request):
    await request.app.state.database.check()
    return {"status": "ok"}


@app.get("/flights", response_model=list[FlightResponse])
async def search_flights(
    request: Request,
    origin: Annotated[str, Query(pattern=r"^[A-Z]{3}$")],
    destination: Annotated[str, Query(pattern=r"^[A-Z]{3}$")],
    date: Date | None = None,
):
    result = await request.app.state.flights.search(origin, destination, date)
    return [flight_response(item) for item in result.flights]


@app.get("/flights/{flight_id}", response_model=FlightResponse)
async def get_flight(flight_id: UUID, request: Request):
    return flight_response(await request.app.state.flights.get(flight_id))


async def compensate(client, booking_id):
    try:
        await client.release(booking_id)
    except grpc.aio.AioRpcError:
        logger.exception("Reservation cleanup failed for booking_id=%s", booking_id)


@app.post("/bookings", response_model=BookingResponse, status_code=201)
async def create_booking(data: BookingCreate, request: Request):
    database, client = request.app.state.database, request.app.state.flights
    flight = await client.get(data.flight_id)
    total = Decimal(flight.price_minor * data.seat_count).scaleb(-2)
    if total <= 0 or total > Decimal("9999999999.99"):
        raise ApiError(
            400, "INVALID_ARGUMENT", "Booking total exceeds supported price range"
        )
    booking_id = uuid4()
    try:
        await client.reserve(data.flight_id, data.seat_count, booking_id)
    except grpc.aio.AioRpcError:
        await compensate(client, booking_id)
        raise
    try:
        async with database.sessions() as session, session.begin():
            row = Booking(
                id=booking_id,
                user_id=data.user_id,
                flight_id=data.flight_id,
                passenger_name=data.passenger_name,
                passenger_email=str(data.passenger_email),
                seat_count=data.seat_count,
                total_price=total,
                status="CONFIRMED",
            )
            session.add(row)
            await session.flush()
            result = BookingResponse.model_validate(row)
        return result
    except SQLAlchemyError:
        try:
            async with database.sessions() as session:
                saved = await session.get(Booking, booking_id)
                if saved is not None:
                    return BookingResponse.model_validate(saved)
        except SQLAlchemyError:
            logger.exception(
                "Cannot resolve booking commit outcome for booking_id=%s", booking_id
            )
            raise
        await compensate(client, booking_id)
        raise


@app.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: UUID, request: Request):
    async with request.app.state.database.sessions() as session:
        row = await session.get(Booking, booking_id)
        if row is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "Booking not found")
        return BookingResponse.model_validate(row)


@app.get("/bookings", response_model=list[BookingResponse])
async def list_bookings(user_id: UUID, request: Request):
    async with request.app.state.database.sessions() as session:
        rows = await session.scalars(
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.created_at, Booking.id)
        )
        return [BookingResponse.model_validate(row) for row in rows]


@app.post("/bookings/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(booking_id: UUID, request: Request):
    async with request.app.state.database.sessions() as session, session.begin():
        row = await session.get(Booking, booking_id, with_for_update=True)
        if row is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "Booking not found")
        if row.status == "CANCELLED":
            return BookingResponse.model_validate(row)
        await request.app.state.flights.release(booking_id)
        row.status = "CANCELLED"
        await session.flush()
        result = BookingResponse.model_validate(row)
    return result
