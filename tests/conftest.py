import pytest
from app import app as flask_app


@pytest.fixture
def app():
    """
    Flask-App im TESTING-Modus.
    """
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def client(app):
    """
    Test-Client für Integrationstests.
    """
    return app.test_client()
