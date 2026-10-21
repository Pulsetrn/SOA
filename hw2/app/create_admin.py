import argparse
import asyncio
import getpass
import sys

from marketplace_api.models.register_request import RegisterRequest
from marketplace_api.models.user_response import UserResponse
from pydantic import ValidationError

from app.database import Database
from app.errors import ApiException
from app.services.auth import create_user
from app.settings import DatabaseSettings


async def create_admin(username: str, password: str) -> UserResponse:
    """Create a new administrator without promoting or replacing an existing account."""
    validated = RegisterRequest(username=username, password=password)
    database = Database(DatabaseSettings.from_env())
    try:
        async with database.sessions() as session:
            return await create_user(validated.username, validated.password, "ADMIN", session)
    finally:
        await database.close()


def main(argv: list[str] | None = None) -> int:
    """Read a confirmed password privately and report only a safe command result."""
    parser = argparse.ArgumentParser(description="Create a new marketplace administrator")
    parser.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    try:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match", file=sys.stderr)
            return 1
        user = asyncio.run(create_admin(args.username, password))
    except (EOFError, KeyboardInterrupt):
        print("Administrator creation cancelled", file=sys.stderr)
        return 1
    except ValidationError:
        print("Invalid username or password; check the registration constraints", file=sys.stderr)
        return 1
    except ApiException as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except Exception:
        print("Could not create administrator; check database availability and migrations", file=sys.stderr)
        return 1
    print(f"Administrator created: {user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
