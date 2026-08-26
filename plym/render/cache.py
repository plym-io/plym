from collections import OrderedDict

MAX_ENTRIES = 256


class RAMStore:
    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._store: OrderedDict[str, str] = OrderedDict()
        self._max_entries = max_entries

    def get(self, key: str) -> str | None:
        value = self._store.get(key)
        if value is not None:
            self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

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
