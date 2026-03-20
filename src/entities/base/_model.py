from typing import Iterator, Set, Tuple

from sqlalchemy import BigInteger, Column, DateTime, Integer, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BaseModel_(Base):
    __abstract__ = True  # This model should not be instantiated directly
    __table_args__ = {"extend_existing": True}  # Allow table extension
    __hidden_fields__: Set[str] = set()  # Fields excluded from serialisation

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __iter__(self) -> Iterator[Tuple[str, object]]:
        if not self.__hidden_fields__:
            return super().__iter__()
        for c in self.__table__.columns:
            if c.key not in self.__hidden_fields__:
                yield c.key, getattr(self, c.key)
