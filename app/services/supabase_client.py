from functools import lru_cache

import httpx
from supabase import Client, ClientOptions, create_client
from app.config import get_settings
from app.exceptions import AppError


@lru_cache
def _get_shared_httpx_client() -> httpx.Client:
    return httpx.Client(timeout=120.0)


def _build_server_client_options() -> ClientOptions:
    return ClientOptions(
        auto_refresh_token=False,
        persist_session=False,
        httpx_client=_get_shared_httpx_client(),
    )


def _build_user_client_options(access_token: str) -> ClientOptions:
    return ClientOptions(
        headers={"Authorization": f"Bearer {access_token}"},
        auto_refresh_token=False,
        persist_session=False,
    )


@lru_cache
def get_default_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_default_key:
        raise AppError(500, "SUPABASE_CONFIG_ERROR", "Missing SUPABASE_URL or SUPABASE_ANON_KEY")
    return create_client(
        settings.supabase_url,
        settings.supabase_default_key,
        options=_build_server_client_options(),
    )


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise AppError(500, "SUPABASE_CONFIG_ERROR", "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=_build_server_client_options(),
    )


def get_user_client(access_token: str) -> Client:
    settings = get_settings()
    options = _build_user_client_options(access_token)
    return create_client(settings.supabase_url, settings.supabase_default_key, options=options)
