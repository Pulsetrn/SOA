SELECT installed_rank, version, description, script, checksum, success
FROM flyway_schema_history
ORDER BY installed_rank;

SELECT id, username, role, created_at, updated_at
FROM users
ORDER BY created_at, id;

SELECT id, name, price, stock, category, status, seller_id, created_at, updated_at
FROM products
ORDER BY created_at, id;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public' AND tablename = 'products'
ORDER BY indexname;

SELECT jti, user_id, expires_at, revoked_at, created_at
FROM refresh_sessions
ORDER BY created_at, jti;

SELECT id, user_id, status, promo_code_id, total_amount, discount_amount, created_at, updated_at
FROM orders
ORDER BY created_at, id;

SELECT id, order_id, product_id, quantity, price_at_order
FROM order_items
ORDER BY order_id, id;

SELECT id, user_id, operation_type, created_at
FROM user_operations
ORDER BY user_id, created_at, id;

SELECT id, code, discount_type, discount_value, min_order_amount, max_uses, current_uses,
       valid_from, valid_until, active
FROM promo_codes
ORDER BY code;
