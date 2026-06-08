import asyncio
import json
from datetime import datetime, timezone

import aiofiles

from plym.db.session import get_session_factory
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository
from plym.settings import settings


def _serialise(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def run_backup_once() -> str:
    factory = get_session_factory()
    async with factory() as session:
        posts = await PostRepository(session).list_all_for_backup()
        for post in posts:
            post["tags"] = await TagRepository(session).list_for_post(post["id"])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "posts": [{k: _serialise(v) for k, v in post.items()} for post in posts],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = settings.backups_dir / f"posts-{stamp}.json"
    async with aiofiles.open(target, "w", encoding="utf-8") as f:
        await f.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return str(target)


class BackupScheduler:
    def __init__(self, frequency_days: int) -> None:
        self._interval_seconds = max(1, frequency_days) * 24 * 3600
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval_seconds)
                await run_backup_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
