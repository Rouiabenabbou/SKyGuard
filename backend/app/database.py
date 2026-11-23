"""
Database setup with SQLAlchemy + SQLite.

* `engine`       - the connection to the database file
* `SessionLocal` - creates a short-lived "session" for a group of queries
* `Base`         - parent class of every table in models.py
* `init_db()`    - creates the file, the tables and the starting data
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config

config.DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# SQLite (a file on your PC) or, v1.3, PostgreSQL (e.g. Huawei Cloud RDS, see docs/CLOUD_DEPLOY.md).
if config.DATABASE_URL.startswith("sqlite"):
    # check_same_thread=False lets FastAPI use the connection from different threads.
    engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: gives an endpoint a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (if missing) and insert the devices and the network topology."""
    from app import models  # noqa: F401  (importing registers the tables)
    from app.auth import seed_users
    from app.seed import seed_companies, seed_devices, seed_network, seed_profiles

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_devices(db)
        seed_network(db)
        seed_profiles(db)  # v1.1: real coordinates + motion sensors
        seed_users(db)  # v1.1: default accounts on the first start
        seed_companies(db)  # v1.2: demo companies (multi-tenant)
    from app import tenancy
    tenancy.refresh()
