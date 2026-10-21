from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, FetchedValue, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("char_length(username) >= 3", name="ck_users_username_length"),
        CheckConstraint("char_length(password_hash) > 0", name="ck_users_password_hash_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        ENUM("USER", "SELLER", "ADMIN", name="user_role", create_type=False),
        server_default=text("'USER'"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), server_onupdate=FetchedValue()
    )


class Product(Base):
    __tablename__ = "products"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("char_length(name) > 0", name="ck_products_name_not_empty"),
        CheckConstraint("char_length(category) > 0", name="ck_products_category_not_empty"),
        CheckConstraint("price > 0", name="ck_products_price_positive"),
        CheckConstraint("stock >= 0", name="ck_products_stock_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(4000))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int]
    category: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        ENUM("ACTIVE", "INACTIVE", "ARCHIVED", name="product_status", create_type=False),
        server_default=text("'ACTIVE'"),
        index=True,
    )
    seller_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), server_onupdate=FetchedValue()
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_refresh_sessions_token_hash"),
    )

    jti: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))


class Order(Base):
    __tablename__ = "orders"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_orders_total_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="ck_orders_discount_nonnegative"),
        CheckConstraint("total_amount <> 'NaN'::numeric AND discount_amount <> 'NaN'::numeric", name="ck_orders_money_finite"),
        Index("uq_orders_one_active_per_user", "user_id", unique=True,
              postgresql_where=text("status IN ('CREATED', 'PAYMENT_PENDING')")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(
        ENUM("CREATED", "PAYMENT_PENDING", "PAID", "SHIPPED", "COMPLETED", "CANCELED",
             name="order_status", create_type=False), server_default=text("'CREATED'"),
    )
    promo_code_id: Mapped[UUID | None] = mapped_column(ForeignKey("promo_codes.id", ondelete="RESTRICT"), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), server_onupdate=FetchedValue()
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
        CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_order_items_quantity"),
        CheckConstraint("price_at_order > 0", name="ck_order_items_price_positive"),
        CheckConstraint("price_at_order <> 'NaN'::numeric", name="ck_order_items_price_finite"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int]
    price_at_order: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class PromoCode(Base):
    __tablename__ = "promo_codes"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("code", name="uq_promo_codes_code"),
        CheckConstraint("code ~ '^[A-Z0-9_]{4,20}$'", name="ck_promo_codes_code"),
        CheckConstraint("discount_value > 0", name="ck_promo_codes_discount_positive"),
        CheckConstraint("min_order_amount >= 0", name="ck_promo_codes_minimum_nonnegative"),
        CheckConstraint("discount_value <> 'NaN'::numeric AND min_order_amount <> 'NaN'::numeric",
                        name="ck_promo_codes_money_finite"),
        CheckConstraint("discount_type <> 'PERCENTAGE' OR discount_value <= 100", name="ck_promo_codes_percentage"),
        CheckConstraint("max_uses > 0", name="ck_promo_codes_max_uses"),
        CheckConstraint("current_uses BETWEEN 0 AND max_uses", name="ck_promo_codes_current_uses"),
        CheckConstraint("isfinite(valid_from) AND isfinite(valid_until) AND valid_from < valid_until",
                        name="ck_promo_codes_period"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(20))
    discount_type: Mapped[str] = mapped_column(
        ENUM("PERCENTAGE", "FIXED_AMOUNT", name="discount_type", create_type=False)
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    min_order_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    max_uses: Mapped[int]
    current_uses: Mapped[int] = mapped_column(server_default=text("0"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(server_default=text("true"))


class UserOperation(Base):
    __tablename__ = "user_operations"
    __table_args__ = (
        Index("ix_user_operations_last", "user_id", "operation_type", text("created_at DESC")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    operation_type: Mapped[str] = mapped_column(
        ENUM("CREATE_ORDER", "UPDATE_ORDER", name="user_operation_type", create_type=False)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"))
