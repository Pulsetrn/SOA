import os
from datetime import datetime, time, timezone
from decimal import Decimal

import flight_pb2 as pb
import flight_pb2_grpc as rpc
import grpc

from booking.schemas import FlightResponse


def flight_response(message):
    return FlightResponse(
        id=message.id,
        flight_number=message.flight_number,
        airline=message.airline,
        origin=message.origin,
        destination=message.destination,
        departure_time=message.departure_time.ToDatetime(tzinfo=timezone.utc),
        arrival_time=message.arrival_time.ToDatetime(tzinfo=timezone.utc),
        total_seats=message.total_seats,
        available_seats=message.available_seats,
        price=Decimal(message.price_minor).scaleb(-2),
        status=pb.FlightStatus.Name(message.status).removeprefix("FLIGHT_STATUS_"),
    )


class FlightClient:
    def __init__(self):
        self.timeout = float(os.getenv("GRPC_TIMEOUT_SECONDS", "3"))
        if self.timeout <= 0:
            raise ValueError("GRPC_TIMEOUT_SECONDS must be positive")
        self.channel = grpc.aio.insecure_channel(
            os.getenv("FLIGHT_TARGET", "localhost:50051")
        )
        self.stub = rpc.FlightServiceStub(self.channel)

    async def get(self, flight_id):
        return await self.stub.GetFlight(
            pb.GetFlightRequest(flight_id=str(flight_id)), timeout=self.timeout
        )

    async def search(self, origin, destination, date):
        request = pb.SearchFlightsRequest(origin=origin, destination=destination)
        if date is not None:
            request.departure_date.FromDatetime(
                datetime.combine(date, time.min, tzinfo=timezone.utc)
            )
        return await self.stub.SearchFlights(request, timeout=self.timeout)

    async def reserve(self, flight_id, seat_count, booking_id):
        return await self.stub.ReserveSeats(
            pb.ReserveSeatsRequest(
                flight_id=str(flight_id),
                seat_count=seat_count,
                booking_id=str(booking_id),
            ),
            timeout=self.timeout,
        )

    async def release(self, booking_id):
        return await self.stub.ReleaseReservation(
            pb.ReleaseReservationRequest(booking_id=str(booking_id)),
            timeout=self.timeout,
        )

    async def close(self):
        await self.channel.close()
