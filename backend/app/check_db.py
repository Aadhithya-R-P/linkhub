"""Run from backend with: python -m app.check_db"""

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_engine


def main() -> int:
    try:
        engine = get_engine()
    except ValidationError:
        print("Database configuration is missing or invalid. Check backend/.env.")
        return 1

    try:
        with engine.connect() as connection:
            database, user = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
        print(f"Connected successfully: database={database}, user={user}")
        return 0
    except SQLAlchemyError:
        # Avoid printing connection details that might contain credentials.
        print("Connection failed. Check PostgreSQL is running and your .env credentials are correct.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
