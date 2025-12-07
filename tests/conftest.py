import pytest
from app import app as flask_app


@pytest.fixture
def app():
    """
    Stellt die Flask-App im TESTING-Modus bereit.
    """
    flask_app.config.update(TESTING=True)
    yield flask_app


@pytest.fixture
def client(app):
    """
    Flask-Test-Client, mit dem wir HTTP-Requests gegen die App ausführen können.
    """
    return app.test_client()
