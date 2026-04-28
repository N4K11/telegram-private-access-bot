from pydantic import SecretStr

MASK = "***"


def mask_secret(secret: SecretStr | None) -> str:
    if secret is None or not secret.get_secret_value():
        return ""
    return MASK
