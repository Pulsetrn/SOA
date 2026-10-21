from uuid import UUID

from fastapi import Request
from marketplace_api.apis.orders_api_base import BaseOrdersApi
from marketplace_api.models.order_create import OrderCreate
from marketplace_api.models.order_response import OrderResponse
from marketplace_api.models.order_status_change import OrderStatusChange
from marketplace_api.models.order_update import OrderUpdate

from app.models import User
from app.services import orders


class OrdersHandler(BaseOrdersApi):
    def __init__(self, request: Request, current_user: User) -> None:
        """Retain application resources and the authenticated actor for order operations."""
        self.database = request.app.state.database
        self.current_user = current_user
        self.settings = request.app.state.order_settings

    async def get_order(self, id: UUID) -> OrderResponse:
        """Read an existing order through a separate database session and generated DTOs."""
        async with self.database.sessions() as session:
            return await orders.get_order(id, self.current_user, session)

    async def create_order(self, order_create: OrderCreate) -> OrderResponse:
        """Create an order and reserve its products atomically through a separate session."""
        async with self.database.sessions() as session:
            return await orders.create_order(order_create, self.current_user, session, self.settings)

    async def update_order(self, id: UUID, order_update: OrderUpdate) -> OrderResponse:
        """Replace an authorized CREATED order with an atomic reserve and snapshot recalculation."""
        async with self.database.sessions() as session:
            return await orders.update_order(id, order_update, self.current_user, session, self.settings)

    async def cancel_order(self, id: UUID) -> OrderResponse:
        """Cancel an authorized eligible order and return its reserve exactly once."""
        async with self.database.sessions() as session:
            return await orders.cancel_order(id, self.current_user, session)

    async def change_order_status(self, id: UUID, order_status_change: OrderStatusChange) -> OrderResponse:
        """Advance an order through the ADMIN-only state operation in a separate session."""
        async with self.database.sessions() as session:
            return await orders.change_order_status(id, order_status_change, self.current_user, session)
