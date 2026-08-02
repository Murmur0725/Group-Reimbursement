import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR
from app.db.models import Base


def get_database_path() -> Path:
    return Path(os.getenv("REIMBURSEMENT_DB_PATH", str(DATA_DIR / "reimbursement.db")))


def get_database_url() -> str:
    return f"sqlite:///{get_database_path()}"


def create_session_factory(database_url: str | None = None):
    engine = create_engine(
        database_url or get_database_url(),
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


SessionLocal = create_session_factory()


def init_db(database_url: str | None = None):
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        database_url or get_database_url(),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
