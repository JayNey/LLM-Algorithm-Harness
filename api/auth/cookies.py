"""HttpOnly session cookies. JSON tokens remain for non-browser clients."""

from fastapi import Response

ACCESS_COOKIE = "harness_access_token"
REFRESH_COOKIE = "harness_refresh_token"
PERSIST_COOKIE = "harness_persist"
ACCESS_PATH = "/api"
REFRESH_PATH = "/api/v1/auth"
PERSIST_PATH = "/api"


def set_auth_cookies(
    response: Response,
    tokens: dict[str, object],
    *,
    persistent: bool,
    secure: bool,
    refresh_max_age: int,
) -> None:
    expires_in = tokens["expires_in"]
    access_age: int | None
    if persistent:
        if not isinstance(expires_in, int):
            raise TypeError("expires_in must be int")
        access_age = expires_in
    else:
        access_age = None
    refresh_age = refresh_max_age if persistent else None
    response.set_cookie(
        ACCESS_COOKIE,
        str(tokens["access_token"]),
        max_age=access_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=ACCESS_PATH,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        str(tokens["refresh_token"]),
        max_age=refresh_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=REFRESH_PATH,
    )
    if persistent:
        response.set_cookie(
            PERSIST_COOKIE,
            "1",
            max_age=refresh_age,
            httponly=True,
            secure=secure,
            samesite="lax",
            path=PERSIST_PATH,
        )


def clear_auth_cookies(response: Response, *, secure: bool) -> None:
    response.delete_cookie(
        ACCESS_COOKIE, path=ACCESS_PATH, secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_PATH, secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        PERSIST_COOKIE, path=PERSIST_PATH, secure=secure, httponly=True, samesite="lax"
    )
