CREATE TYPE order_status AS ENUM (
    'CREATED', 'PAYMENT_PENDING', 'PAID', 'SHIPPED', 'COMPLETED', 'CANCELED'
);
CREATE TYPE user_operation_type AS ENUM ('CREATE_ORDER', 'UPDATE_ORDER');

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    status order_status NOT NULL DEFAULT 'CREATED',
    promo_code_id UUID,
    total_amount NUMERIC(12,2) NOT NULL,
    discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_orders_total_nonnegative CHECK (total_amount >= 0),
    CONSTRAINT ck_orders_discount_nonnegative CHECK (discount_amount >= 0),
    CONSTRAINT ck_orders_money_finite CHECK (
        total_amount <> 'NaN'::numeric AND discount_amount <> 'NaN'::numeric
    )
);

CREATE INDEX ix_orders_user_id ON orders(user_id);
CREATE UNIQUE INDEX uq_orders_one_active_per_user
    ON orders(user_id) WHERE status IN ('CREATED', 'PAYMENT_PENDING');

CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL,
    price_at_order NUMERIC(12,2) NOT NULL,
    CONSTRAINT uq_order_items_order_product UNIQUE (order_id, product_id),
    CONSTRAINT ck_order_items_quantity CHECK (quantity BETWEEN 1 AND 999),
    CONSTRAINT ck_order_items_price_positive CHECK (price_at_order > 0),
    CONSTRAINT ck_order_items_price_finite CHECK (price_at_order <> 'NaN'::numeric)
);

CREATE INDEX ix_order_items_product_id ON order_items(product_id);

CREATE TABLE user_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    operation_type user_operation_type NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_user_operations_last
    ON user_operations(user_id, operation_type, created_at DESC);

CREATE TRIGGER orders_set_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
