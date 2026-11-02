import asyncio
import logging
import os
import signal

import flight_pb2_grpc
import grpc
from common.database import Database

from flight.auth import ApiKeyInterceptor
from flight.service import FlightService


async def serve():
    interceptor = ApiKeyInterceptor(os.getenv("FLIGHT_API_KEY", ""))
    database = Database()
    server = grpc.aio.server(interceptors=[interceptor])
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await database.check()
        flight_pb2_grpc.add_FlightServiceServicer_to_server(
            FlightService(database), server
        )
        port = server.add_insecure_port(os.getenv("GRPC_LISTEN", "[::]:50051"))
        if not port:
            raise RuntimeError("Cannot bind gRPC server")
        await server.start()
        logging.info("Flight Service listening on %s", port)
        await stopped.wait()
    finally:
        await server.stop(5)
        await database.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(serve())
