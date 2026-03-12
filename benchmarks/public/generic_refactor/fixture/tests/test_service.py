from apps.api.service import handler


def test_handler() -> None:
    assert handler(" Alice ") == "alice"
