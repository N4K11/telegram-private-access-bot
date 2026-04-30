# Diagnostics

## Admin commands

- `/admin` — открыть админку.
- `/admin_channel_check` — live-проверка подключённых каналов и прав бота.
- `/admin_health` — runtime health dashboard для админа.
- `/admin_promo_create CODE TYPE VALUE LIMIT [TARIFF_ID|-] [VALID_DAYS|-]` — создать промокод.
- `/admin_promo_disable CODE` — отключить промокод.
- `/admin_promo_stats CODE` — показать статистику промокода.
- `/promo CODE` — применить пользовательский промокод.
- `/paysupport` — пользовательская платёжная поддержка.

## Channel diagnostics

`/admin_channel_check` проверяет:

- что бот отвечает на `getMe`;
- что канал доступен через Telegram API;
- что бот состоит в канале;
- что бот администратор;
- что у бота есть право создавать invite links;
- что у бота есть право restrict/ban пользователей;
- что snapshot прав в БД не расходится с live-состоянием.

Если в отчёте есть mismatch `store/live`, откройте раздел `Каналы` и выполните refresh канала.

## Expiration warnings and grace period

Worker истечения подписок теперь проходит в 4 шага:

- warning за 3 дня, если включён `WARNING_3D_ENABLED`;
- warning за 1 день, если включён `WARNING_1D_ENABLED`;
- expired notice сразу после окончания подписки;
- revoke только после `GRACE_PERIOD_HOURS`.

Если пользователь продлил подписку до revoke, новый доступ создаётся штатно, а старый grace-экземпляр больше не должен быть отозван повторно.
## Runtime health dashboard

`/admin_health` показывает:

- uptime процесса;
- bot username и доступность `getMe`;
- есть ли активные каналы в базе;
- состояние store на чтение и запись;
- количество пользователей;
- количество активных подписок;
- количество платежей за текущий день;
- last update id и тип события, если telemetry уже накопилась;
- last maintenance run от фонового scheduler;
- последнюю Telegram API ошибку, если она была зафиксирована;
- время последнего backup.

Если `Хранилище: запись` упало в `❌`, не перезапускайте сервис вслепую: сначала проверьте доступность БД и права пользователя БД.

Если `Бот подключен` упал в `❌`, сначала перепроверьте `BOT_TOKEN`, доступ в сеть и доступность Telegram API.

## Promo diagnostics

Если пользователь жалуется, что скидка не применилась:

- проверьте `/admin_promo_stats CODE`;
- убедитесь, что промокод не отключён и не истёк;
- проверьте, что тариф совпадает с `TARIFF_ID`, если промокод scoped;
- проверьте, что пользователь оплачивает через Telegram Stars, а не Crypto Pay;
- проверьте audit-события `promo_applied_pending`, `promo_applied_free_days` и `payment_paid_stars`.

## Local checks

```bash
python -m compileall app tests alembic
ruff check .
pytest -q
python -m app.healthcheck
```

## Server checks

```bash
docker compose ps
docker compose logs --tail=100 bot
python -m app.healthcheck
```

## Common failures

- `канал не найден или bot не видит его`:
  проверьте `chat_id`, добавлен ли бот в канал и не был ли он исключён.
- `Бот администратор: нет`:
  выдайте права администратора.
- `Может создавать invite links: нет`:
  включите invite permissions.
- `Может ограничивать пользователей: нет`:
  включите restrict/ban permissions.
- `getMe` не проходит:
  проверьте `BOT_TOKEN`, сеть и доступность Telegram API.
- `Хранилище: запись` не проходит:
  проверьте права пользователя БД, read-only режим БД и состояние транзакций.
- `Последний backup: ещё не создавался`:
  проверьте настройки `BACKUP_*` и выполните ручной backup из админки.
- `Скидка не применилась`:
  проверьте scope промокода, его статус и факт оплаты именно через Stars.

