from app.security.auth import create_access_token, decode_access_token, hash_password, verify_password


def test_register_login_me_primitives():
    password = "super-secure-123"
    hashed = hash_password(password)
    assert verify_password(password, hashed)

    token = create_access_token("user-1", "user")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "user"