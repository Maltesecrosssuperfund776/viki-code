from consumer import total


def test_total() -> None:
    assert total([1, 2, 3]) == 6
