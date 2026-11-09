"""Plain-text layouts that also work without rich-text support."""


def card(title: str, body: str, footer: str = "") -> str:
    parts = [title.strip(), body.strip()]
    if footer:
        parts.append(footer.strip())
    return "\n\n".join(part for part in parts if part)
