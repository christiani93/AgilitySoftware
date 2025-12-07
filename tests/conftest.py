import os
import sys
import pytest

# Ensure web_app modules are importable
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
WEB_APP_DIR = os.path.join(ROOT_DIR, 'web_app')
if WEB_APP_DIR not in sys.path:
    sys.path.insert(0, WEB_APP_DIR)

from app import app as flask_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate data directory per test run
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('FLASK_ENV', 'testing')

    # Ensure app uses temp data dir
    flask_app.config['DATA_DIR'] = str(data_dir)
    yield flask_app.test_client()
