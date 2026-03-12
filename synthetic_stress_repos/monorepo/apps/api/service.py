from packages.shared.auth import normalize_user


def handler(name: str) -> str:
    return normalize_user(name)
