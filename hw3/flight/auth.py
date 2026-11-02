import hmac

import grpc


class ApiKeyInterceptor(grpc.aio.ServerInterceptor):
    def __init__(self, api_key: str):
        if not api_key or any(not 33 <= ord(char) <= 126 for char in api_key):
            raise ValueError("FLIGHT_API_KEY must be a non-empty printable ASCII token")
        self._api_key = api_key.encode("ascii")

    async def intercept_service(self, continuation, handler_call_details):
        values = [
            value
            for key, value in (handler_call_details.invocation_metadata or ())
            if key == "x-api-key"
        ]
        if len(values) == 1 and hmac.compare_digest(
            values[0].encode("utf-8"), self._api_key
        ):
            return await continuation(handler_call_details)
        return grpc.unary_unary_rpc_method_handler(self._reject)

    async def _reject(self, request, context):
        await context.abort(
            grpc.StatusCode.UNAUTHENTICATED, "Invalid service credentials"
        )
