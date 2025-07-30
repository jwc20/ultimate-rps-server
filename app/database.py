import logging
from typing import Annotated
from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine
from .config import DEV, SQLITE_URL, POSTGRES_URL

logger = logging.getLogger(__name__)

if DEV:
    # SQLite for development
    engine = create_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False}
    )
    logger.info("Using SQLite database for development")
else:
    # PostgreSQL for production
    if not POSTGRES_URL:
        raise ValueError("POSTGRES_URL environment variable is required in production")

    engine = create_engine(POSTGRES_URL)
    logger.info("Using PostgreSQL database for production")


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created")


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]