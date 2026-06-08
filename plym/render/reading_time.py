import re
from math import ceil


class ReadingTimeCalculator:
    def __init__(self, words_per_minute: int) -> None:
        self._wpm = max(1, words_per_minute)

    def minutes(self, content: str) -> int:
        words = len(re.findall(r"\w+", content))
        return max(1, ceil(words / self._wpm))
