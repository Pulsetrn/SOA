from uuid import UUID

from fastapi import Request
from app.models import User

from marketplace_api.apis.products_api_base import BaseProductsApi
from marketplace_api.models.product_create import ProductCreate
from marketplace_api.models.product_page import ProductPage
from marketplace_api.models.product_response import ProductResponse
from marketplace_api.models.product_status import ProductStatus
from marketplace_api.models.product_update import ProductUpdate

from app.services import products


class ProductsHandler(BaseProductsApi):
    def __init__(self, request: Request, current_user: User) -> None:
        """Retain the authenticated identity and app resources for product operations."""
        self.database = request.app.state.database
        self.current_user = current_user

    async def create_product(self, product_create: ProductCreate) -> ProductResponse:
        """Create a product through a request-local session and explicit transaction."""
        async with self.database.sessions() as session:
            return await products.create_product(product_create, self.current_user, session)

    async def get_product(self, id: UUID) -> ProductResponse:
        """Read a product using the generated response contract and a separate session."""
        async with self.database.sessions() as session:
            return await products.get_product(id, session)

    async def list_products(
        self,
        page: int,
        size: int,
        status: ProductStatus | None,
        category: str | None,
    ) -> ProductPage:
        """Read a stable product page and matching count through a separate session."""
        async with self.database.sessions() as session:
            return await products.list_products(page, size, status, category, session)

    async def update_product(
        self, id: UUID, product_update: ProductUpdate
    ) -> ProductResponse:
        """Replace an authorized product using one transaction and the generated DTO."""
        async with self.database.sessions() as session:
            return await products.update_product(id, product_update, self.current_user, session)

    async def archive_product(self, id: UUID) -> None:
        """Archive an authorized product and return no response body."""
        async with self.database.sessions() as session:
            await products.archive_product(id, self.current_user, session)
