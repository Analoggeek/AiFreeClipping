"""HTTPS helpers that work on plain macOS/Windows Python installs too.

Bundled Pythons sometimes ship without a CA bundle, which surfaces as
``SSL: CERTIFICATE_VERIFY_FAILED`` while downloading model weights. Prefer
the ``certifi`` bundle when present; fall back to the system store and, only
as a last resort, to an unverified context so the download can still finish.
"""
from __future__ import annotations

import os
import ssl
import urllib.request
from typing import Any


def configure_ca_bundle() -> None:
    """Point requests/httpx-style libraries at a usable CA bundle early."""
    try:
        import certifi  # type: ignore

        bundle = certifi.where()
        os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
        os.environ.setdefault("CURL_CA_BUNDLE", bundle)
        os.environ.setdefault("SSL_CERT_FILE", bundle)
    except Exception:
        pass


def ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return ssl._create_unverified_context()


def urlopen(target: urllib.request.Request | str, timeout: float = 60, **kwargs: Any):
    return urllib.request.urlopen(target, timeout=timeout, context=ssl_context(), **kwargs)
