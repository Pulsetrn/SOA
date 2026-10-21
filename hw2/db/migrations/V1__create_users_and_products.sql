CREATE TYPE user_role AS ENUM ('USER', 'SELLER', 'ADMIN');
CREATE TYPE product_status AS ENUM ('ACTIVE', 'INACTIVE', 'ARCHIVED');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL DEFAULT 'USER',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT ck_users_username_length CHECK (char_length(username) >= 3),
    CONSTRAINT ck_users_password_hash_not_empty CHECK (char_length(password_hash) > 0)
);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description VARCHAR(4000),
    price NUMERIC(12,2) NOT NULL,
    stock INTEGER NOT NULL,
    category VARCHAR(100) NOT NULL,
    status product_status NOT NULL DEFAULT 'ACTIVE',
    seller_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_products_seller_id FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT ck_products_name_not_empty CHECK (char_length(name) > 0),
    CONSTRAINT ck_products_category_not_empty CHECK (char_length(category) > 0),
    CONSTRAINT ck_products_price_positive CHECK (price > 0),
    CONSTRAINT ck_products_stock_nonnegative CHECK (stock >= 0)
);

CREATE INDEX ix_products_status ON products(status);

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
