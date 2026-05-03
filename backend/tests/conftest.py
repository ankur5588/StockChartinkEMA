import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://chartink-auto-order.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TEST_SESSION_TOKEN = "sess_testdash1234"
TEST_USER_ID = "user_testdash1234"


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture
def auth_client():
    s = requests.Session()
    s.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TEST_SESSION_TOKEN}",
    })
    return s
