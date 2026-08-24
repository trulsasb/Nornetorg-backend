def slugify(text: str) -> str:
    return "-".join(text.strip().lower().split()) or "uten-navn"
