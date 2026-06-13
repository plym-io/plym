import io
import sys
import time
import tarfile
import urllib.request

RETRIES = 5
TIMEOUT = 30


def extract(data: bytes, dest: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)


def main() -> int:
    url, dest = sys.argv[1], sys.argv[2]
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            print(f"fetching admin (attempt {attempt}/{RETRIES}): {url}", flush=True)
            with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                data = resp.read()
            extract(data, dest)
            print(f"admin bundle installed ({len(data)} bytes) -> {dest}", flush=True)
            return 0
        except (OSError, tarfile.TarError) as exc:
            last = exc
            print(f"admin fetch failed: {exc}", flush=True)
            if attempt < RETRIES:
                delay = min(2 ** attempt, 20)
                print(f"retrying in {delay}s", flush=True)
                time.sleep(delay)
    print(
        f"ERROR: could not fetch admin bundle from {url} "
        f"after {RETRIES} attempts: {last}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
