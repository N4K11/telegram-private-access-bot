# Diagnostics

## Admin commands

- `/admin` — открыть админку.
- `/admin_channel_check` — live-проверка подключённых каналов и прав бота.
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
