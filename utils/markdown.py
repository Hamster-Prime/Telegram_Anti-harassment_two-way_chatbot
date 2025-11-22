def escape_markdown(text: str, version: int = 2) -> str:
    if version == 2:
        escape_chars = r'_*[]()~`>#+-=|{}.!'
    else:
        escape_chars = r'_*`['
    return "".join(f"\\{char}" if char in escape_chars else char for char in text)
