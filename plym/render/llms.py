LLMS_TXT_PATH = "llms.txt"


def llms_txt_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/{LLMS_TXT_PATH}"


def llms_directive(llms_url: str) -> str:
    return f"<!-- llms.txt: {llms_url} -->"
