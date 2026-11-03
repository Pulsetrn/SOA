# HW3 - локальный запуск

```sh
cd hw3
export FLIGHT_API_KEY=hw3-local-demo-key
docker compose up --build -d --wait
```

Ключ в примере предназначен для локального запуска. Compose передаёт его обоим сервисам, а миграции применяются автоматически при старте.

Загрузка деморейсов. После прямой записи в БД перезапуск Flight обновит поколение кеша, а `--wait` дождётся готовности сервисов.

```sh
docker compose exec -T flight python -m flight.seed
docker compose restart flight
docker compose up -d --wait
```

Выполните поиск дважды. Ожидаются два рейса SVO → LED, а повторный поиск читает результат из кеша.

```sh
curl -fsS 'http://127.0.0.1:8003/flights?origin=SVO&destination=LED'
curl -fsS 'http://127.0.0.1:8003/flights?origin=SVO&destination=LED'
```

Посмотреть состояние контейнеров, логи сервисов и адрес текущего Redis master можно командами ниже. Flight пишет `cache_miss` и `cache_hit`, Booking пишет `flight_breaker` при смене состояния, а Sentinel пишет `+switch-master` при переключении.

```sh
docker compose ps
docker compose logs --tail 50 flight booking
docker compose logs --tail 30 sentinel-1 sentinel-2 sentinel-3
docker compose exec -T sentinel-1 redis-cli -p 26379 SENTINEL get-master-addr-by-name flight-cache
```

Остановка проекта командой `docker compose down`. Данные PostgreSQL останутся в томах.
