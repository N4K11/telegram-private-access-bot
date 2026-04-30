# Runtime Map

## Entry points

- `app.main` запускает aiogram polling, middleware, workers и bootstrap шаблонов.
- `app.healthcheck` выполняет локальную runtime-проверку базы и backup directory.
- `app.tools.generate_minimal_assets` генерирует runtime PNG-ассеты из минималистичной визуальной системы.

## Routers

- `app.bot.routers.user.start` — `/start`, главное меню, профиль, помощь, получение ссылки.
- `app.bot.routers.user.payments` — Stars, Crypto Pay, тарифы, покупка и `paysupport`.
- `app.bot.routers.user.invites` — выдача и повторная отправка invite links.
- `app.bot.routers.admin.dashboard` — `/admin` и вход в разделы админки.
- `app.bot.routers.admin.diagnostics` — `/admin_channel_check` и live-диагностика каналов.
- `app.bot.routers.admin.channels` — CRUD/refresh каналов.
- `app.bot.routers.admin.tariffs` — CRUD тарифов.
- `app.bot.routers.admin.analytics` — snapshot аналитики и переходы в users.
- `app.bot.routers.admin.users` — каталог пользователей, блокировки, выдачи, direct message.
- `app.bot.routers.admin.texts` — managed text templates.
- `app.bot.routers.admin.broadcasts` — рассылки.
- `app.bot.routers.admin.backups` — manual backups и отправка backup admin'у.

## Background workers

- `app.workers.subscription_expirer` — revoke просроченных подписок.
- `app.workers.payment_reconciler` — reconciliation активных Crypto Pay invoice.
- `app.workers.broadcast_sender` — queue sender рассылок.
- `app.workers.backup_worker` — daily backup и retention.

## Persistent data

- PostgreSQL: `users`, `channels`, `tariffs`, `subscriptions`, `payments`, `invite_links`, `crypto_invoices`, `audit_logs`, `text_templates`, `broadcast_*`, `backup_records`.
- Локальные backup-файлы хранятся в `backups/` или в каталоге из `BACKUP_DIRECTORY`.

## Visual assets

- Runtime banners: `assets/banners/*.png`.
- Bot avatar candidate: `assets/avatar/bot_avatar.png`.
- Source concepts: `design/minimalist-concepts/`.
