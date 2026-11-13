"""
Snowflake connection from environment variables (never hard-code secrets).

Locally: copy .env.example to .env and fill it in.
GitHub Actions: the same names are set from repository secrets.

Auth, in this order:
  1. SNOWFLAKE_PRIVATE_KEY        PEM text of the private key (GitHub secret)
  2. SNOWFLAKE_PRIVATE_KEY_PATH   path to a .p8 file (local)
  3. SNOWFLAKE_PASSWORD           password (local only, not for service users)
  4. SNOWFLAKE_AUTHENTICATOR=externalbrowser  (local SSO / MFA)
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _private_key_der() -> bytes | None:
    pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not pem and path:
        pem = Path(path).expanduser().read_text()
    if not pem:
        return None
    from cryptography.hazmat.primitives import serialization
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = serialization.load_pem_private_key(
        pem.encode(), password=passphrase.encode() if passphrase else None)
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())


def database() -> str:
    _load_dotenv()
    return os.getenv("SNOWFLAKE_DATABASE", "S2C_DEV")


def connect(role: str | None = None):
    """Open a connection. `role` overrides SNOWFLAKE_ROLE (e.g. S2C_ADMIN for setup scripts)."""
    _load_dotenv()
    import snowflake.connector

    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": role or os.getenv("SNOWFLAKE_ROLE", "S2C_LOADER"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "S2C_WH"),
        "database": database(),
        "client_session_keep_alive": False,
        "application": "s2c-snowflake-data-source",
    }
    key = _private_key_der()
    if key:
        params["private_key"] = key
    elif os.getenv("SNOWFLAKE_PASSWORD"):
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    elif os.getenv("SNOWFLAKE_AUTHENTICATOR"):
        params["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
    else:
        raise SystemExit("No Snowflake credentials: set SNOWFLAKE_PRIVATE_KEY(_PATH), SNOWFLAKE_PASSWORD "
                         "or SNOWFLAKE_AUTHENTICATOR (see .env.example)")
    return snowflake.connector.connect(**params)
