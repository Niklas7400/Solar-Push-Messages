import httpx


class Notifier:
    def __init__(self, ntfy_url: str, topic: str):
        self._url = f"{ntfy_url.rstrip('/')}/{topic}"

    def send(self, title: str, message: str, priority: str = "default", tags: str = "") -> None:
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = tags
        httpx.post(self._url, content=message.encode("utf-8"), headers=headers, timeout=10)
