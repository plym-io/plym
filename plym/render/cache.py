class RAMStore:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        for key in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(key, None)

    def size(self) -> int:
        return len(self._store)


_store: RAMStore | None = None


def get_store() -> RAMStore:
    global _store
    if _store is None:
        _store = RAMStore()
    return _store
