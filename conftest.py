import pytest


def pytest_addoption(parser):
    parser.addoption("--debug_grammar", action='store_true')


@pytest.fixture(scope='session')
def debug_grammar(request):
    return request.config.option.debug_grammar
