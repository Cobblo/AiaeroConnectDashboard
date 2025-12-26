# telemetry/duckdb_utils.py
import os
import logging

import duckdb
from django.conf import settings

log = logging.getLogger(__name__)


def get_duckdb_path() -> str:
    """
    Resolve the DuckDB database path.

    Priority:
    1) settings.DUCKDB_PATH
    2) environment variable DUCKDB_PATH
    3) fallback file in BASE_DIR
    """
    path = getattr(settings, "DUCKDB_PATH", None) or os.environ.get("DUCKDB_PATH")

    if not path:
        base_dir = getattr(settings, "BASE_DIR", os.getcwd())
        path = os.path.join(str(base_dir), "aiaero_local.duckdb")

    return path


def get_duckdb_conn():
    """
    Open a DuckDB connection using the resolved path.
    """
    db_path = get_duckdb_path()

    # If DUCKDB_PATH accidentally points to a *folder*,
    # put a default file inside that folder.
    if os.path.isdir(db_path):
        db_path = os.path.join(db_path, "aiaero_connect.duckdb")

    log.debug("Opening DuckDB at %s", db_path)
    return duckdb.connect(db_path, read_only=False)
