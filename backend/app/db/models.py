"""OrderDesk tables. One Postgres holds everything: rows, trigram text search and vectors.

Read docs/architecture.md alongside this file.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- catalogue

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200), index=True)  # match incoming emails to a customer
    town: Mapped[str | None] = mapped_column(String(80))


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    family: Mapped[str] = mapped_column(String(30), index=True)
    unit: Mapped[str] = mapped_column(String(30))
    pack_qty: Mapped[int] = mapped_column(Integer, default=1)
    list_price_gbp: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(get_settings().EMBED_DIM))

    __table_args__ = (
        # GIN trigram indexes make fuzzy search ("cu elbow 15mm") fast on names and codes
        Index("ix_products_name_trgm", "name", postgresql_using="gin",
              postgresql_ops={"name": "gin_trgm_ops"}),
        Index("ix_products_code_trgm", "code", postgresql_using="gin",
              postgresql_ops={"code": "gin_trgm_ops"}),
    )


class CustomerAlias(Base):
    """A customer's own name or part number for a product. Every reviewer correction adds one."""
    __tablename__ = "customer_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    alias_text: Mapped[str] = mapped_column(String(300))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    created_by: Mapped[str] = mapped_column(String(80), default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("customer_id", "alias_text"),)


class PriceRule(Base):
    """A discount: for a customer on everything (family and product empty), on a family, or on one product."""
    __tablename__ = "price_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    family: Mapped[str | None] = mapped_column(String(30))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)


# ---------------------------------------------------------------- pipeline

class Document(Base):
    """An incoming email or file. The hash stops the same file being processed twice."""
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20))            # email | upload | eval
    filename: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|processing|extracted|failed
    text: Mapped[str | None] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    po_number: Mapped[str | None] = mapped_column(String(60))
    delivery_date: Mapped[date | None] = mapped_column(Date)
    # auto_approved | needs_review | approved | exported | failed
    status: Mapped[str] = mapped_column(String(20), default="needs_review", index=True)
    confidence: Mapped[float | None]
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erp_ref: Mapped[str | None] = mapped_column(String(60))
    # sent with the ERP export, so a retry never creates a second order
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int]
    raw_text: Mapped[str] = mapped_column(Text)
    qty: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit: Mapped[str | None] = mapped_column(String(30))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    match_method: Mapped[str | None] = mapped_column(String(20))   # alias|code|trigram|vector|agent|human
    match_score: Mapped[float | None]
    candidates: Mapped[list | None] = mapped_column(JSONB)          # top-5 [{product_id, score, method}]
    reason: Mapped[str | None] = mapped_column(Text)                # plain-English reason when flagged
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)


class LlmCall(Base):
    """Every LLM call, so any result can be traced to the model and prompt version that made it."""
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    purpose: Mapped[str] = mapped_column(String(30))                # extract | resolve
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_gbp: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None]
    success: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Who changed what, with before/after, for every state change."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int]
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalCase(Base):
    """A labelled test order: the file plus the correct answer."""
    __tablename__ = "eval_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(40), unique=True)   # gen-0001, held-001
    split: Mapped[str] = mapped_column(String(20))                   # generated | held_out
    filename: Mapped[str] = mapped_column(String(300))
    expected: Mapped[dict] = mapped_column(JSONB)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="reviewer")  # reviewer | admin
