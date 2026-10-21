from marketplace_api.apis.health_api_base import BaseHealthApi
from marketplace_api.models.health_response import HealthResponse


class HealthHandler(BaseHealthApi):
    async def get_health(self) -> HealthResponse:
        """Report API process availability using the generated response model."""
        return HealthResponse(status="ok")
