from __future__ import annotations


class _SafeDict(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


DEFAULT_TEXTS: dict[str, str] = {
    "start": (
        "Hello, {first_name}.\n\n"
        "This bot will manage private channel access, subscriptions and payments."
    ),
    "user_subscription": (
        "Subscription\n\n"
        "The subscription summary screen is connected and will be expanded in the next stage."
    ),
    "user_tariffs": "Tariffs\n\nAvailable plans will appear here.",
    "user_support": "Support\n\nSupport instructions will appear here.",
    "admin_dashboard": (
        "Admin panel\n\n"
        "Core sections are wired and will be expanded in the next implementation stages."
    ),
    "admin_section": "Admin section: {section}",
}


def render_text(key: str, **context: object) -> str:
    template = DEFAULT_TEXTS.get(key, key)
    return template.format_map(_SafeDict(context))