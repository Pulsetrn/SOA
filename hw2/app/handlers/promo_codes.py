from fastapi import Request
from marketplace_api.apis.promo_codes_api_base import BasePromoCodesApi
from marketplace_api.models.promo_code_create import PromoCodeCreate
from marketplace_api.models.promo_code_response import PromoCodeResponse

from app.models import User
from app.services import promo_codes


class PromoCodesHandler(BasePromoCodesApi):
    def __init__(self, request: Request, current_user: User) -> None:
        """Retain application resources and the authenticated promo-code creator."""
        self.database = request.app.state.database
        self.current_user = current_user

    async def create_promo_code(self, promo_code_create: PromoCodeCreate) -> PromoCodeResponse:
        """Create a promo code in a separate session through the generated request and response DTOs."""
        async with self.database.sessions() as session:
            return await promo_codes.create_promo_code(promo_code_create, self.current_user, session)
