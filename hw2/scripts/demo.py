"""Demonstrate the running HTTP API and verify its effects through independent SQL SELECTs."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.create_admin import create_admin
from app.json_codec import dump_json, load_json
from app.settings import OrderSettings


BASE_URL = "http://127.0.0.1:8000"


def call(method, path, expected=200, *, token=None, body=None, error=None):
    """Send a real HTTP request and print its status and correlation ID without credentials."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(BASE_URL + path, method=method, headers=headers,
                      data=None if body is None else dump_json(body).encode("utf-8"))
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read()
        data = load_json(raw) if raw else None
        request_id = response.headers["X-Request-Id"]
        UUID(request_id)
        assert response.status == expected, (method, path, response.status, expected)
        if error:
            assert data["error_code"] == error, (method, path, data.get("error_code"), error)
        suffix = f" {error}" if error else ""
        print(f"HTTP {method} {path} -> {response.status}{suffix}; request_id={request_id}", flush=True)
        return data


def wait_for_api():
    """Wait briefly for startup so a freshly launched container can run the same demonstration."""
    for _ in range(60):
        try:
            with urlopen(BASE_URL + "/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            time.sleep(0.5)
    raise RuntimeError("API did not become ready")


def snapshot(connection, users, product_id, promo_id, label):
    """Read demonstration rows through a separate SQL connection and display only non-secret fields."""
    queries = {
        "products": ("SELECT id, price, stock, status FROM products WHERE id = %s", (UUID(product_id),)),
        "orders": ("SELECT id, user_id, status, total_amount, discount_amount, promo_code_id "
                   "FROM orders WHERE user_id = ANY(%s) ORDER BY created_at, id", (users,)),
        "order_items": ("SELECT i.id, i.order_id, i.product_id, i.quantity, i.price_at_order "
                        "FROM order_items i JOIN orders o ON o.id = i.order_id "
                        "WHERE o.user_id = ANY(%s) ORDER BY o.created_at, i.id", (users,)),
        "promo_codes": ("SELECT id, code, current_uses, max_uses FROM promo_codes WHERE id = %s", (UUID(promo_id),)),
        "user_operations": ("SELECT user_id, operation_type FROM user_operations "
                            "WHERE user_id = ANY(%s) ORDER BY created_at, id", (users,)),
    }
    result = {name: connection.execute(sql, args).fetchall() for name, (sql, args) in queries.items()}
    print(f"\nSQL SELECT — {label}", flush=True)
    for name, rows in result.items():
        print(f"{name}: {dump_json(rows)}", flush=True)
    print(flush=True)
    return result


def main():
    """Run a short product, promo, order, authorization and state workflow with observable SQL results."""
    wait_for_api()
    run_id = uuid4().hex[:10]
    password = secrets.token_urlsafe(24)
    users, tokens = {}, {}
    print(f"Demo run: {run_id}. Created rows remain available for inspection; secrets are not printed.", flush=True)
    for role, label in [("SELLER", "seller"), ("USER", "buyer"), ("USER", "other")]:
        username = f"demo_{run_id}_{label}"
        user = call("POST", "/auth/register", 201, body={"username": username, "password": password, "role": role})
        users[label] = UUID(user["id"])
        pair = call("POST", "/auth/login", body={"username": username, "password": password})
        tokens[label] = pair["access_token"]
        if label == "buyer":
            refresh = pair["refresh_token"]
            tokens[label] = call("POST", "/auth/refresh", body={"refresh_token": refresh})["access_token"]
            call("POST", "/auth/refresh", 401, body={"refresh_token": refresh}, error="REFRESH_TOKEN_INVALID")

    admin_name = f"demo_{run_id}_admin"
    admin = asyncio.run(create_admin(admin_name, password))
    users["admin"] = admin.id
    tokens["admin"] = call("POST", "/auth/login", body={"username": admin_name, "password": password})["access_token"]
    print("Admin created through the existing trusted management function; business operations below use HTTP.", flush=True)

    payload = {"name": f"Demo {run_id}", "description": "Defense demonstration", "price": Decimal("10.00"),
               "stock": 10, "category": f"demo_{run_id}", "status": "ACTIVE"}
    call("GET", "/products", 401, error="TOKEN_INVALID")
    call("POST", "/products", 403, token=tokens["buyer"], body=payload, error="ACCESS_DENIED")
    call("POST", "/products", 400, token=tokens["seller"], body={**payload, "price": 0}, error="VALIDATION_ERROR")
    product = call("POST", "/products", 201, token=tokens["seller"], body=payload)
    product_id = product["id"]
    call("GET", f"/products/{product_id}", token=tokens["buyer"])
    page = call("GET", f"/products?category=demo_{run_id}&status=ACTIVE&page=0&size=1", token=tokens["buyer"])
    assert page["totalElements"] == 1 and len(page["content"]) == 1

    now = datetime.now(timezone.utc)
    promo = call("POST", "/promo-codes", 201, token=tokens["seller"], body={
        "code": f"DEMO_{run_id.upper()}", "discount_type": "PERCENTAGE", "discount_value": 25,
        "min_order_amount": 10, "max_uses": 1,
        "valid_from": (now - timedelta(days=1)).isoformat(), "valid_until": (now + timedelta(days=1)).isoformat(),
    })
    basket = {"items": [{"product_id": product_id, "quantity": 2}], "promo_code": promo["code"]}
    order = call("POST", "/orders", 201, token=tokens["buyer"], body=basket)
    order_id = order["id"]
    assert order["total_amount"] == 15 and order["discount_amount"] == 5
    item_id = order["items"][0]["id"]
    interval = OrderSettings.from_env().interval_minutes
    call("POST", "/orders", 429 if interval else 409, token=tokens["buyer"], body=basket,
         error="ORDER_LIMIT_EXCEEDED" if interval else "ORDER_HAS_ACTIVE")
    call("GET", f"/orders/{order_id}", 403, token=tokens["other"], error="ORDER_OWNERSHIP_VIOLATION")

    with psycopg.connect(host=os.environ["DB_HOST"], port=os.environ.get("DB_PORT", "5432"),
                         dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                         autocommit=True, row_factory=dict_row) as connection:
        print("Flyway:", dump_json(connection.execute(
            "SELECT version, success FROM flyway_schema_history ORDER BY installed_rank").fetchall()), flush=True)
        rows = snapshot(connection, list(users.values()), product_id, promo["id"], "created: stock 8, total 15, discount 5, uses 1")
        assert rows["products"][0]["stock"] == 8 and rows["promo_codes"][0]["current_uses"] == 1
        call("PUT", f"/products/{product_id}", token=tokens["seller"], body={**payload, "price": 12, "stock": 8})
        saved = call("GET", f"/orders/{order_id}", token=tokens["buyer"])
        assert saved["items"][0]["price_at_order"] == 10 and saved["total_amount"] == 15
        updated = call("PUT", f"/orders/{order_id}", token=tokens["buyer"], body={"items": [{"product_id": product_id, "quantity": 3}]})
        assert updated["total_amount"] == Decimal("22.50") and updated["discount_amount"] == Decimal("7.50")
        assert updated["items"][0]["id"] == item_id and updated["items"][0]["price_at_order"] == 10
        rows = snapshot(connection, list(users.values()), product_id, promo["id"], "updated: catalog price 12, snapshot 10, stock 7, total 22.50, uses 1")
        assert rows["products"][0]["stock"] == 7 and rows["promo_codes"][0]["current_uses"] == 1
        call("POST", f"/orders/{order_id}/cancel", token=tokens["buyer"])
        call("POST", f"/orders/{order_id}/cancel", 409, token=tokens["buyer"], error="INVALID_STATE_TRANSITION")
        rows = snapshot(connection, list(users.values()), product_id, promo["id"], "canceled: stock 10, uses 0, order history retained")
        assert rows["products"][0]["stock"] == 10 and rows["promo_codes"][0]["current_uses"] == 0
        assert rows["orders"][0]["status"] == "CANCELED" and len(rows["user_operations"]) == 2

        second = call("POST", "/orders", 201, token=tokens["other"], body={**basket, "items": [{"product_id": product_id, "quantity": 1}]})
        assert second["total_amount"] == 9 and second["items"][0]["price_at_order"] == 12
        path = f"/orders/{second['id']}/status"
        call("POST", path, 403, token=tokens["other"], body={"status": "PAYMENT_PENDING"}, error="ACCESS_DENIED")
        call("POST", path, 409, token=tokens["admin"], body={"status": "PAID"}, error="INVALID_STATE_TRANSITION")
        for status in ["PAYMENT_PENDING", "PAID", "SHIPPED", "COMPLETED"]:
            changed = call("POST", path, token=tokens["admin"], body={"status": status})
            assert changed["status"] == status
        call("POST", f"/orders/{second['id']}/cancel", 409, token=tokens["other"], error="INVALID_STATE_TRANSITION")
        call("DELETE", f"/products/{product_id}", 204, token=tokens["seller"])
        archived = call("GET", f"/products/{product_id}", token=tokens["buyer"])
        assert archived["status"] == "ARCHIVED"
        rows = snapshot(connection, list(users.values()), product_id, promo["id"], "final: ARCHIVED stock 9, CANCELED + COMPLETED, uses 1")
        assert rows["products"][0]["stock"] == 9 and rows["products"][0]["status"] == "ARCHIVED"
        assert {row["status"] for row in rows["orders"]} == {"CANCELED", "COMPLETED"}
        assert rows["promo_codes"][0]["current_uses"] == 1 and len(rows["user_operations"]) == 3
    print("DEMO PASSED. IDs and SQL rows above can be inspected again. No existing rows were deleted.", flush=True)


if __name__ == "__main__":
    main()
