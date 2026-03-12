from apps.api.service import handler


def test_handler():
    assert handler(' Alice ') == 'alice'
