# Запуск и демонстрация

Команды ниже выполняются из корня репозитория. Нужен запущенный Docker Desktop с Docker Compose.

```sh
docker compose -f hw2/compose.yaml up --build -d --wait marketplace-api
docker compose -f hw2/compose.yaml ps
docker compose -f hw2/compose.yaml logs --tail=25 migrate marketplace-api
curl -i http://localhost:8000/health
```

Команда `up` собирает образ, поднимает БД, дожидается Flyway и запускает API в фоне; `--wait` ожидает готовности сервисов. Демонстрационный скрипт также сам кратко ждёт `/health`. Документация: [Swagger UI](http://localhost:8000/docs), [исходный контракт](openapi/openapi.yaml).

PostgreSQL хранит данные в именованном томе. `docker compose -f hw2/compose.yaml down` останавливает проект и сохраняет данные. Повторный `up` не начинает работу с пустой БД: Flyway сверяет уже применённые миграции. Удалять рабочий том для проверки сервиса не требуется.

## Один воспроизводимый сценарий

```sh
docker compose -f hw2/compose.yaml exec -T marketplace-api python - < hw2/scripts/demo.py
```

[scripts/demo.py](scripts/demo.py) запускается внутри работающего API-контейнера. Каждый запуск создаёт уникальные демонстрационные данные: SELLER, двух USER, ADMIN, один товар, один промокод и два заказа. Строки остаются в БД для просмотра; существующие данные не очищаются. Пароли случайные, пароли и токены не печатаются.

ADMIN создаётся через существующую доверенную функцию команды администрирования; остальные пользователи регистрируются через HTTP. Все операции каталога/заказов/промокодов выполняются через HTTP. SELECT идут через отдельное соединение psycopg с autocommit, поэтому видят уже зафиксированные данные. Скрипт не выполняет ручные UPDATE бизнес-таблиц и не подменяет сервисы.

Ожидаемые результаты:

| Момент | Что показать по HTTP и SELECT |
| --- | --- |
| Создание | Товар price=10, stock=10. Корзина 2 штуки с кодом 25%: total=15, discount=5, stock=8, current_uses=1 |
| Обновление | Цена каталога становится 12; старый заказ остаётся со снимком 10. PUT количества 3: тот же UUID позиции, total=22.50, discount=7.50, stock=7, current_uses по-прежнему 1 |
| Отмена | CANCELED, stock=10, current_uses=0. Позиции и история скидки остаются. Повтор cancel→409, второго возврата нет |
| Повторное использование | Другой USER создаёт заказ 1×12: total=9, discount=3, снимок=12, stock=9, current_uses=1 |
| Состояния и удаление | Только ADMIN проводит второй заказ до COMPLETED. Перескок CREATED→PAID и отмена COMPLETED дают 409. DELETE товара→204; SELECT/GET по-прежнему видят ARCHIVED, stock=9 |

Дополнительно видны 400 для price=0, 401 без токена/replay refresh, 403 по роли и владельцу, 429 при повторном создании в интервале. Если частота явно отключена через `ORDER_OPERATION_INTERVAL_MINUTES=0`, вместо 429 срабатывает следующий запрет — 409 ORDER_HAS_ACTIVE. Стандартный интервал — одна минута; скрипт не отключает ограничения и не ждёт минуту.

Каждая HTTP-строка скрипта содержит request_id. Найти соответствующую запись в настоящем журнале:

```sh
docker compose -f hw2/compose.yaml logs --no-log-prefix --tail=100 marketplace-api
```

Сопоставить ID, endpoint, status_code и user_id; у login/register/refresh показать маскирование. Консоль содержит HTTP events и отдельные server events. SQL-вывод скрипта — отдельное доказательство состояния БД, он не является журналом API.

## SELECT вручную

Скрипт выводит UUID товара, заказов и кода. Можно повторить выборку из SQL-клиента:

```sh
docker compose -f hw2/compose.yaml exec db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

В psql подставить UUID из демонстрации:

```sql
\set product_id 'UUID_ТОВАРА'
\set order_id 'UUID_ЗАКАЗА'
\set promo_id 'UUID_ПРОМОКОДА'

SELECT id, price, stock, status, seller_id, created_at, updated_at
FROM products WHERE id = :'product_id'::uuid;

SELECT id, user_id, status, total_amount, discount_amount, promo_code_id
FROM orders WHERE id = :'order_id'::uuid;

SELECT id, product_id, quantity, price_at_order
FROM order_items WHERE order_id = :'order_id'::uuid;

SELECT code, current_uses, max_uses, active, valid_from, valid_until
FROM promo_codes WHERE id = :'promo_id'::uuid;

SELECT operation_type, created_at FROM user_operations
WHERE user_id = (SELECT user_id FROM orders WHERE id = :'order_id'::uuid)
ORDER BY created_at;

SELECT version, description, success FROM flyway_schema_history ORDER BY installed_rank;
SELECT indexdef FROM pg_indexes WHERE tablename = 'products';
```

Для общей выборки без хешей/паролей:

```sh
docker compose -f hw2/compose.yaml exec -T db sh -c 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < hw2/db/inspect.sql
```

Для просмотра истории и проверки миграций:

```sh
docker compose -f hw2/compose.yaml run --rm migrate info
docker compose -f hw2/compose.yaml run --rm migrate validate
```

## Ручная проверка через Swagger

Для самостоятельного запроса удобно Swagger UI: зарегистрировать отдельного SELLER или USER, войти через `/auth/login`, вставить только access token в **Authorize**. Случайные секреты автоматической демонстрации не требуется извлекать. Для отдельного ADMIN:

```sh
docker compose -f hw2/compose.yaml exec marketplace-api python -m app.create_admin --username defense_admin
```

Команда приватно спросит пароль и подтверждение. Она создаёт нового ADMIN, существующего пользователя не повышает. Далее войти этим пользователем через `/auth/login`.

Для ручной проверки можно изменить price/quantity, убрать Bearer, запросить чужой заказ или повторить cancel; сравнить HTTP-статус/error_code и соответствующие записи в БД. Для ошибки INSUFFICIENT_STOCK сначала использовать новую USER-учётную запись без активного заказа и недавней CREATE_ORDER: иначе более ранние проверки закономерно вернут другую ошибку.
