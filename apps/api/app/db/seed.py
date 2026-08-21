"""Idempotent development seed. Refuses to run outside development."""
import asyncio
import secrets

from app.core.config import get_settings
from app.db.rls import lookup_user_id_by_email
from app.db.session import get_sessionmaker
from app.services import auth_service


async def main() -> None:
    s = get_settings()
    if s.app_env != "development":
        raise SystemExit("Seed refuses to run outside APP_ENV=development.")
    email = "demo@nur.local"
    async with get_sessionmaker()() as db:
        async with db.begin():
            exists = await lookup_user_id_by_email(db, email)
        if exists:
            print(f"seed: {email} already present — nothing to do")
            return
        password = secrets.token_urlsafe(12)
        await auth_service.register(db, chosen_name="Demo", email=email, password=password, consent=True)
        print(f"seed: created {email} with one-time password: {password}")


if __name__ == "__main__":
    asyncio.run(main())
