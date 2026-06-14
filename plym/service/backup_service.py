import asyncio
import json
from datetime import datetime, timezone

import aiofiles

from plym.db.session import get_session_factory
from plym.repository.post_repository import PostRepository
from plym.repository.tag_repository import TagRepository
from plym.settings import settings


_BACKUP_CHUNK = 500


def _serialise(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _encode_post(post: dict) -> str:
    return json.dumps({k: _serialise(v) for k, v in post.items()}, ensure_ascii=False, default=str)


async def run_backup_once() -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = settings.backups_dir / f"posts-{stamp}.json"
    factory = get_session_factory()
    async with factory() as session, aiofiles.open(target, "w", encoding="utf-8") as f:
        posts = PostRepository(session)
        tags = TagRepository(session)
        await f.write('{"generated_at": ' + json.dumps(generated_at) + ', "posts": [')
        first = True
        after = 0
        while True:
            chunk = await posts.list_for_backup_after(after=after, limit=_BACKUP_CHUNK)
            if not chunk:
                break
            tags_by_post = await tags.list_for_posts([p["id"] for p in chunk])
            for post in chunk:
                post["tags"] = tags_by_post.get(post["id"], [])
                await f.write(_encode_post(post) if first else "," + _encode_post(post))
                first = False
            after = chunk[-1]["id"]
            if len(chunk) < _BACKUP_CHUNK:
                break
        await f.write("]}")
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
