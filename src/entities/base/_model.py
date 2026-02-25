from sqlalchemy import BigInteger, Column, DateTime, Integer, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BaseModel_(Base):
    __abstract__ = True  # This model should not be instantiated directly
    __table_args__ = {"extend_existing": True}  # Allow table extension

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
