import asyncio
import os

import grpc

from booking.circuit_breaker import CircuitBreaker

RETRYABLE_CODES = (
    grpc.StatusCode.UNAVAILABLE,
    grpc.StatusCode.DEADLINE_EXCEEDED,
)


class FlightInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    def __init__(self):
        self.breaker = CircuitBreaker(
            threshold=int(os.getenv("FLIGHT_BREAKER_THRESHOLD", "5")),
            cooldown=float(os.getenv("FLIGHT_BREAKER_COOLDOWN_SECONDS", "15")),
            window=float(os.getenv("FLIGHT_BREAKER_WINDOW_SECONDS", "60")),
        )

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        permit = self.breaker.acquire()
        if permit is None:
            raise grpc.aio.AioRpcError(
                grpc.StatusCode.UNAVAILABLE,
                grpc.aio.Metadata(),
                grpc.aio.Metadata(),
                details="Flight Service circuit breaker is open or checking recovery",
            )

        try:
            response = await self._call(
                continuation,
                client_call_details,
                request,
                attempts=1 if permit.probe else 3,
            )
        except grpc.aio.AioRpcError as error:
            self.breaker.complete(permit, failed=error.code() in RETRYABLE_CODES)
            raise
        except BaseException:
            if permit.probe:
                self.breaker.complete(permit, failed=True)
            raise
        else:
            self.breaker.complete(permit, failed=False)
            return response

    async def _call(self, continuation, details, request, attempts):
        for attempt in range(attempts):
            try:
                call = await continuation(details, request)
                return await call
            except grpc.aio.AioRpcError as error:
                if attempt == attempts - 1 or error.code() not in RETRYABLE_CODES:
                    raise
                await asyncio.sleep(0.1 * 2**attempt)
