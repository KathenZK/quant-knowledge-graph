import re


def key(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold())
