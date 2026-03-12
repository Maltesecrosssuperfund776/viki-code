from apps.cli.commands import normalize_input


def test_cli_normalize_input() -> None:
    assert normalize_input(" Bob ") == "bob"
