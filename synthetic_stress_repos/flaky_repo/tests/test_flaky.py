import os


def test_flaky_example():
    assert os.getenv('VIKI_FLAKY_MODE', 'stable') == 'stable'
