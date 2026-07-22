# models.py
# SQLAlchemy ORM models — one table per logical entity in the payload.
# Relationships:  Client 1→N Account 1→N Holding

from sqlalchemy import (
    Column, String, Float, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()


class AccountType(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    ROTH_IRA   = "ROTH_IRA"
    TRAD_IRA   = "TRAD_IRA"
    JOINT      = "JOINT"


class AccountStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    INACTIVE = "INACTIVE"
    CLOSED   = "CLOSED"


class AssetClass(str, enum.Enum):
    US_EQUITY     = "US_EQUITY"
    INTL_EQUITY   = "INTL_EQUITY"
    FIXED_INCOME  = "FIXED_INCOME"
    CASH          = "CASH"
    ALTERNATIVE   = "ALTERNATIVE"


class Client(Base):
    __tablename__ = "clients"

    client_id    = Column(String, primary_key=True)   # e.g. "CLT-29481"
    first_name   = Column(String, nullable=False)
    last_name    = Column(String, nullable=False)
    email        = Column(String, nullable=False)
    advisor_id   = Column(String, nullable=True)
    last_updated = Column(DateTime, nullable=True)
    ingested_at  = Column(DateTime, default=datetime.utcnow)

    accounts = relationship(
        "Account",
        back_populates="client",
        cascade="all, delete-orphan",   # delete orphaned accounts on re-ingest
    )

    def __repr__(self):
        return f"<Client {self.client_id} {self.first_name} {self.last_name}>"


class Account(Base):
    __tablename__ = "accounts"

    account_id   = Column(String, primary_key=True)   # e.g. "ACC-10042"
    client_id    = Column(String, ForeignKey("clients.client_id"), nullable=False)
    account_type = Column(String, nullable=False)      # keep as String to handle unknown types
    custodian    = Column(String, nullable=True)
    opened_date  = Column(String, nullable=True)       # stored as ISO string; cast at query time
    status       = Column(String, nullable=False, default="ACTIVE")
    cash_balance = Column(Float, nullable=True, default=0.0)
    total_value  = Column(Float, nullable=True, default=0.0)
    ingested_at  = Column(DateTime, default=datetime.utcnow)

    client   = relationship("Client", back_populates="accounts")
    holdings = relationship(
        "Holding",
        back_populates="account",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Account {self.account_id} [{self.account_type}]>"


class Holding(Base):
    __tablename__ = "holdings"

    # Surrogate PK — a holding is identified by (account_id, ticker/cusip)
    # but we keep an auto id for simplicity.
    id           = Column(String, primary_key=True)    # "{account_id}:{cusip}"
    account_id   = Column(String, ForeignKey("accounts.account_id"), nullable=False)
    ticker       = Column(String, nullable=True)
    cusip        = Column(String, nullable=True)
    description  = Column(Text, nullable=True)
    quantity     = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    cost_basis   = Column(Float, nullable=True)
    price        = Column(Float, nullable=True)
    asset_class  = Column(String, nullable=True)
    ingested_at  = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="holdings")

    def __repr__(self):
        return f"<Holding {self.ticker} qty={self.quantity}>"
