import asyncio
from pathlib import Path

import psycopg

from plym.settings import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _apply_sync() -> list[str]:
    dsn = (
        f"host={settings.db_host} port={settings.db_port} dbname={settings.db_name} "
        f"user={settings.db_user} password={settings.db_password}"
    )
    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.pl_schema_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("SELECT name FROM public.pl_schema_migrations")
            existing = {row[0] for row in cur.fetchall()}

            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if migration.name in existing:
                    continue
                sql = migration.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO public.pl_schema_migrations (name) VALUES (%s)",
                    (migration.name,),
                )
                applied.append(migration.name)
        conn.commit()
    return applied


async def apply_migrations() -> list[str]:
    return await asyncio.to_thread(_apply_sync)
