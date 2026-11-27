from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from src.config import settings


@contextmanager
def get_conn():
    conn = psycopg.connect(settings.dsn, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_sql_file(filepath: str | Path) -> None:
    sql_text = Path(filepath).read_text(encoding="utf-8")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
