from uuid import uuid4


def _sign_up(client, credentials: dict[str, str]):
    return client.post(
        "/api/v1/auth/sign_up",
        json=credentials,
    )


def _sign_in(client, credentials: dict[str, str], password: str | None = None):
    return client.post(
        "/api/v1/auth/sign_in",
        json={"email": credentials["email"], "password": password or credentials["password"]},
    )


def test_sign_up_success(client, credentials_factory):
    credentials = credentials_factory()
    response = client.post(
        "/api/v1/auth/sign_up",
        json=credentials,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["username"] == credentials["username"]


def test_sign_up_username_taken(client, credentials_factory):
    original = credentials_factory()
    first = _sign_up(client, original)
    assert first.status_code == 201

    duplicate_username = credentials_factory(username=original["username"])
    response = _sign_up(client, duplicate_username)
    assert response.status_code == 409
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "USERNAME_ALREADY_EXISTS"


def test_sign_up_invalid_password_format_returns_validation_error(client, credentials_factory):
    credentials = credentials_factory()
    credentials["password"] = "password123"
    response = _sign_up(client, credentials)

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "password must include uppercase, lowercase, and a number" in body["message"]


def test_sign_in_success(client, credentials_factory):
    credentials = credentials_factory()
    sign_up_response = _sign_up(client, credentials)
    assert sign_up_response.status_code == 201

    response = _sign_in(client, credentials)
    assert response.status_code == 200
    assert response.json()["data"]["access_token"]


def test_sign_in_invalid_credentials(client, credentials_factory):
    credentials = credentials_factory()
    sign_up_response = _sign_up(client, credentials)
    assert sign_up_response.status_code == 201

    wrong_password = f"Aa1{uuid4().hex[:12]}"
    response = _sign_in(client, credentials, password=wrong_password)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_current_user_missing_token(client):
    response = client.get("/api/v1/auth/current_user")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


def test_current_user_success(client, credentials_factory):
    credentials = credentials_factory()
    sign_up_response = _sign_up(client, credentials)
    assert sign_up_response.status_code == 201

    sign_in_response = _sign_in(client, credentials)
    assert sign_in_response.status_code == 200
    access_token = sign_in_response.json()["data"]["access_token"]

    response = client.get(
        "/api/v1/auth/current_user",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == credentials["username"]


def test_log_out_success(client, credentials_factory):
    credentials = credentials_factory()
    sign_up_response = _sign_up(client, credentials)
    assert sign_up_response.status_code == 201

    sign_in_response = _sign_in(client, credentials)
    assert sign_in_response.status_code == 200
    access_token = sign_in_response.json()["data"]["access_token"]

    response = client.post(
        "/api/v1/auth/log_out",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["action"] == "logged_out"


def test_log_out_invalid_token(client):
    response = client.post(
        "/api/v1/auth/log_out",
        headers={"Authorization": f"Bearer invalid-{uuid4().hex}"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "LOG_OUT_FAILED"
