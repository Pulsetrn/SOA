from fastapi import Request
from marketplace_api.apis.auth_api_base import BaseAuthApi
from marketplace_api.models.login_request import LoginRequest
from marketplace_api.models.register_request import RegisterRequest
from marketplace_api.models.refresh_request import RefreshRequest
from marketplace_api.models.token_pair import TokenPair
from marketplace_api.models.user_response import UserResponse

from app.services import auth
from app.security import decode_access_token


class AuthHandler(BaseAuthApi):
    def __init__(self, request: Request) -> None:
        """Use the request's application resources without global database sessions."""
        self.database = request.app.state.database
        self.settings = request.app.state.auth_settings
        self.request = request

    async def register_user(self, register_request: RegisterRequest) -> UserResponse:
        """Register validated credentials through a request-local database session."""
        async with self.database.sessions() as session:
            return await auth.register_user(register_request, session)

    async def login(self, login_request: LoginRequest) -> TokenPair:
        """Check validated credentials and return an access and refresh token pair."""
        async with self.database.sessions() as session:
            pair = await auth.login(login_request, session, self.settings)
        self.request.state.user_id = decode_access_token(pair.access_token, self.settings)["sub"]
        return pair

    async def refresh_tokens(self, refresh_request: RefreshRequest) -> TokenPair:
        """Rotate a validated refresh token through an independent transaction."""
        async with self.database.sessions() as session:
            pair = await auth.refresh_tokens(refresh_request, session, self.settings)
        self.request.state.user_id = decode_access_token(pair.access_token, self.settings)["sub"]
        return pair
