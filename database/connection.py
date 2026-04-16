import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from loguru import logger
from config import settings


def get_connection():
    """Buat koneksi PostgreSQL."""
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        connect_timeout=10
    )


@contextmanager
def get_db():
    """
    Context manager untuk koneksi database.
    Auto commit/rollback dan close koneksi.
    
    Usage:
        with get_db() as db:
            db.execute("SELECT ...")
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield cursor
        conn.commit()
        logger.debug("DB transaction committed.")
    except Exception as e:
        if conn:
            conn.rollback()
            logger.error("DB transaction rolled back: {}", e)
        raise
    finally:
        if conn:
            conn.close()