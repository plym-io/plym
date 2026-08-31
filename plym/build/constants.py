import aiohttp

BASE_URL = "https://fonts.googleapis.com/css2"
METADATA_URL = "https://fonts.google.com/metadata/fonts/{family}"
TEXT = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Safari/605.1.15"
)

PRISM_VERSION = "1.30.0"
PRISM_TARBALL_URL = f"https://registry.npmjs.org/prismjs/-/prismjs-{PRISM_VERSION}.tgz"
PRISM_TARBALL_NPM_INTEGRITY = "sha512-" + (
    "DEvV2ZF2r2/63V+tK8hQvrR2ZGn10srHbXviTlcv7Kpzw8jWiNTqbVgjO3IY8RxrrOUF8VPMQQFysYYYv0YZxw=="
)
PRISM_PACKAGE_ROOT = "package"

HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=5, sock_connect=5, sock_read=10)
PRISM_TIMEOUT = aiohttp.ClientTimeout(total=45, connect=5, sock_connect=5, sock_read=15)
BUILD_STEP_TIMEOUT_S = 60.0
