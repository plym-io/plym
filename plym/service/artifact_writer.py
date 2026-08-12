from pathlib import Path

import aiofiles


async def write_if_changed(target: Path, body: str | None) -> None:
    """Write an artifact only when its bytes move.

    Whatever watches .generated/ purges what it sees change, so rewriting identical
    bytes on every publish would fan out purges for files that did not move.
    """
    if body is None:
        target.unlink(missing_ok=True)
        return
    if target.exists() and target.read_text(encoding="utf-8") == body:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(f"{target.suffix}.tmp")
    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
        await f.write(body)
    tmp.replace(target)
