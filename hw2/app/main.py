from pathlib import Path
from typing import Any

import yaml
from marketplace_api.apis.auth_api import router as auth_router
from marketplace_api.apis.health_api import router as health_router
from marketplace_api.apis.products_api import router as products_router
from marketplace_api.apis.orders_api import router as orders_router
from marketplace_api.apis.promo_codes_api import router as promo_codes_router

from app.errors import register_error_handlers
from app.database import database_lifespan
from app.request_logging import LoggedFastAPI, configure_logging

configure_logging()
app = LoggedFastAPI(title="Marketplace API", version="0.13.0", lifespan=database_lifespan)
register_error_handlers(app)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(promo_codes_router)


def contract_openapi() -> dict[str, Any]:
    """Serve the authored contract as the single source for API documentation."""
    if app.openapi_schema is None:
        path = Path(__file__).resolve().parent.parent / "openapi/openapi.yaml"
        app.openapi_schema = yaml.safe_load(path.read_text(encoding="utf-8"))
    return app.openapi_schema


app.openapi = contract_openapi
