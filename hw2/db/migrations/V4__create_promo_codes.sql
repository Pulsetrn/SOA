CREATE TYPE discount_type AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT');

CREATE TABLE promo_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) NOT NULL,
    discount_type discount_type NOT NULL,
    discount_value NUMERIC(12,2) NOT NULL,
    min_order_amount NUMERIC(12,2) NOT NULL,
    max_uses INTEGER NOT NULL,
    current_uses INTEGER NOT NULL DEFAULT 0,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT uq_promo_codes_code UNIQUE (code),
    CONSTRAINT ck_promo_codes_code CHECK (code ~ '^[A-Z0-9_]{4,20}$'),
    CONSTRAINT ck_promo_codes_discount_positive CHECK (discount_value > 0),
    CONSTRAINT ck_promo_codes_minimum_nonnegative CHECK (min_order_amount >= 0),
    CONSTRAINT ck_promo_codes_money_finite CHECK (
        discount_value <> 'NaN'::numeric AND min_order_amount <> 'NaN'::numeric
    ),
    CONSTRAINT ck_promo_codes_percentage CHECK (discount_type <> 'PERCENTAGE' OR discount_value <= 100),
    CONSTRAINT ck_promo_codes_max_uses CHECK (max_uses > 0),
    CONSTRAINT ck_promo_codes_current_uses CHECK (current_uses BETWEEN 0 AND max_uses),
    CONSTRAINT ck_promo_codes_period CHECK (
        isfinite(valid_from) AND isfinite(valid_until) AND valid_from < valid_until
    )
);

ALTER TABLE orders ADD CONSTRAINT fk_orders_promo_code
    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE RESTRICT;
CREATE INDEX ix_orders_promo_code_id ON orders(promo_code_id);
