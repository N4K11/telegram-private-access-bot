from __future__ import annotations

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _encode_base36(value: int) -> str:
    if value < 0:
        raise ValueError("Base36 encoder accepts only non-negative integers.")
    if value == 0:
        return "0"

    digits: list[str] = []
    current = value
    while current:
        current, remainder = divmod(current, 36)
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def build_referral_code(telegram_id: int) -> str:
    return f"R{_encode_base36(int(telegram_id))}"


def normalize_referral_code(value: str) -> str:
    code = value.strip()
    if code.lower().startswith("ref_"):
        code = code[4:]
    return code.strip().upper()


def build_referral_payload(referral_code: str) -> str:
    return f"ref_{normalize_referral_code(referral_code)}"
