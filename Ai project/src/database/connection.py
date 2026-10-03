"""
Database connection layer.

Responsible ONLY for opening a safe connection to the project's
MySQL / MariaDB database (the same database used by the Laravel backend).

Nothing in this file knows about devices, consumption, or
predictions — that logic belongs in repository.py.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pymysql is required for MySQL/MariaDB connections. "
        "Install with: pip install pymysql"
    ) from exc


class DatabaseConfigError(RuntimeError):
    """Raised when the database cannot be located or configured."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a connection to the database cannot be opened."""


class DatabaseConfig:
    """
    Reads connection settings from environment variables only.

    Required env vars (Laravel-style):
        DB_HOST
        DB_DATABASE
        DB_USERNAME
        DB_PASSWORD

    Optional:
        DB_PORT          default 3306
        DB_CHARSET       default utf8mb4
        DB_CONNECT_TIMEOUT  default 10 (seconds)
    """

    def __init__(
        self,
        host: str,
        database: str,
        user: str,
        password: str,
        port: int = 3306,
        charset: str = "utf8mb4",
        connect_timeout: int = 10,
    ) -> None:
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.port = port
        self.charset = charset
        self.connect_timeout = connect_timeout

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        try:
            from env_config import apply_db_env
            apply_db_env()
        except Exception:
            pass
        host = os.environ.get("DB_HOST")
        database = os.environ.get("DB_DATABASE")
        user = os.environ.get("DB_USERNAME")
        password = os.environ.get("DB_PASSWORD")

        missing = [
            name
            for name, val in [
                ("DB_HOST", host),
                ("DB_DATABASE", database),
                ("DB_USERNAME", user),
                ("DB_PASSWORD", password),
            ]
            if not val
        ]
        if missing:
            raise DatabaseConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". These must point to the Laravel MySQL/MariaDB database."
            )

        port = int(os.environ.get("DB_PORT", "3306"))
        charset = os.environ.get("DB_CHARSET", "utf8mb4")
        connect_timeout = int(
            os.environ.get("DB_CONNECT_TIMEOUT", "10")
        )

        return cls(
            host=host,
            database=database,
            user=user,
            password=password or "",
            port=port,
            charset=charset,
            connect_timeout=connect_timeout,
        )


class Database:
    """
    Thin wrapper that opens correctly-configured MySQL/MariaDB
    connections via pymysql.

    Connections use DictCursor so repository code can address columns
    by name. Transactions are managed explicitly via the
    `transaction()` context manager.
    """

    def __init__(self, config: DatabaseConfig | None = None) -> None:
        self.config = config or DatabaseConfig.from_env()

    def _open_raw(self) -> Any:
        try:
            conn = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset=self.config.charset,
                connect_timeout=self.config.connect_timeout,
                cursorclass=DictCursor,
                autocommit=False,
            )
        except pymysql.Error as exc:
            raise DatabaseConnectionError(
                f"Could not open database: {exc}"
            ) from exc
        return conn

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """
        Plain connection. Caller is responsible for commit/rollback
        if writes are performed. Prefer `transaction()` for atomic
        multi-statement work.
        """
        conn = self._open_raw()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """
        Atomic transaction. Commits on success, rolls back on any
        exception (used for the nightly clear+replace of predictions).
        """
        conn = self._open_raw()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
