import asyncio
import os

import flight_pb2
import flight_pb2_grpc
import grpc


async def check():
    async with grpc.aio.insecure_channel(
        os.getenv("FLIGHT_TARGET", "localhost:50051")
    ) as channel:
        stub = flight_pb2_grpc.FlightServiceStub(channel)
        await stub.SearchFlights(
            flight_pb2.SearchFlightsRequest(origin="SVO", destination="LED"), timeout=2
        )


if __name__ == "__main__":
    asyncio.run(check())
