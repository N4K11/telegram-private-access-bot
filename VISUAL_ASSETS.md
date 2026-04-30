# Visual Assets

## Runtime assets

- `assets/banners/main.png` — главное меню пользователя.
- `assets/banners/buy.png` — экран покупки доступа.
- `assets/banners/tariffs.png` — обзор тарифов.
- `assets/banners/profile.png` — профиль пользователя.
- `assets/banners/join.png` — получение ссылки.
- `assets/banners/help.png` — помощь.
- `assets/banners/admin.png` — админка.
- `assets/avatar/bot_avatar.png` — кандидат для BotFather.

## Source of truth

- Editable SVG concepts и HTML preview лежат в `design/minimalist-concepts/`.
- PNG runtime-ассеты генерируются скриптом `python -m app.tools.generate_minimal_assets`.

## Runtime behavior

- User/main/admin sections используют banner path только если файл реально существует.
- При отсутствии картинки бот не падает и автоматически переходит в text-only fallback.
- Длинные diagnostic screens не используют photo captions, чтобы не упереться в лимит Telegram на подпись.

## Bot avatar

Аватарка не устанавливается кодом. Её нужно загрузить вручную через BotFather:

`/mybots -> выбрать бота -> Edit Bot -> Edit Botpic`
