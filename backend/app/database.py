from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(raw_url: str) -> URL:
    """
    Parse and normalize database connection URL.
    Ensures driver is postgresql+psycopg, validates/sets sslmode, and preserves all parameters.
    """
    if not raw_url or not str(raw_url).strip():
        raise ValueError("DATABASE_URL must not be empty.")

    try:
        url_obj = make_url(str(raw_url).strip())
    except Exception:
        raise ValueError("Invalid DATABASE_URL format.") from None

    allowed_schemes = ("postgresql", "postgres", "postgresql+psycopg")
    if url_obj.drivername not in allowed_schemes:
        raise ValueError(
            "DATABASE_URL must use postgresql://, postgres://, or postgresql+psycopg:// scheme."
        )

    query_params = dict(url_obj.query)
    sslmode = query_params.get("sslmode")
    if not sslmode:
        query_params["sslmode"] = "require"
    else:
        normalized_ssl = sslmode.lower()
        if normalized_ssl in ("disable", "allow", "prefer"):
            raise ValueError(
                f"Insecure sslmode '{sslmode}' is rejected. Must be 'require', 'verify-ca', or 'verify-full'."
            )
        if normalized_ssl not in ("require", "verify-ca", "verify-full"):
            raise ValueError(
                f"Unsupported sslmode '{sslmode}'. Must be 'require', 'verify-ca', or 'verify-full'."
            )

    normalized_url = url_obj.set(drivername="postgresql+psycopg", query=query_params)
    return normalized_url


def create_app_engine(database_url: URL | str | None = None) -> Engine:
    if database_url is None:
        settings = get_settings()
        url = normalize_database_url(settings.DATABASE_URL.get_secret_value())
    elif isinstance(database_url, str):
        url = normalize_database_url(database_url)
    else:
        url = database_url

    return create_engine(
        url,
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args={"connect_timeout": 10},
    )


engine = create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing a database session, ensuring it is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
