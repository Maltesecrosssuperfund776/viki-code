from packages.shared.auth import normalize_user


def normalize_input(name: str) -> str:
    return normalize_user(name)
