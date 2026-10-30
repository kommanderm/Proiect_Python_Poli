"""Sanitising and validation for everything a client sends: HTTP JSON bodies and Socket.IO payloads.

Text is cleaned, not escaped: HTML stays as typed because every page renders it as text
(Jinja autoescaping, textContent in the browser).
"""

import re
import unicodedata
from typing import Any

NAME_MAX_LENGTH = 32
MESSAGE_MAX_LENGTH = 1000
SQLITE_INTEGER_MAX = 2**63 - 1

LOGIN_ID = re.compile(r"[0-9a-f]{12}")
BLANK_LINES = re.compile(r"\n{3,}")
# a format character, but it glues emoji sequences together, so it is not invisible noise
ZERO_WIDTH_JOINER = "‍"


class ValidationError(ValueError):
    """Invalid client input; the message is safe to send back to the client."""


def clean_text(value: str, *, multiline: bool = False) -> str:
    """Drop control, surrogate and invisible format characters, NFC-normalise and tidy whitespace.

    Single-line text has every run of whitespace collapsed to one space. Multiline text keeps
    its line breaks, loses trailing spaces and keeps at most one blank line in a row.
    """
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    kept = []
    for char in value:
        if char in "\n\t":
            kept.append(char if multiline else " ")
            continue
        category = unicodedata.category(char)
        if category in ("Cc", "Cs") or (category == "Cf" and char != ZERO_WIDTH_JOINER):
            continue
        kept.append(char)
    text = unicodedata.normalize("NFC", "".join(kept))

    if not multiline:
        return " ".join(text.split())
    lines = (line.rstrip() for line in text.split("\n"))
    return BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def text_field(data: Any, field: str, label: str, max_length: int, *, multiline: bool = False) -> str:
    value = data.get(field) if isinstance(data, dict) else None
    if value is None:
        raise ValidationError(f"{label} is required")
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text")
    text = clean_text(value, multiline=multiline)
    if not text:
        raise ValidationError(f"{label} must not be empty")
    if len(text) > max_length:
        raise ValidationError(f"{label} must be at most {max_length} characters")
    return text


def display_name(data: Any) -> str:
    """The `display_name` of a user or a room."""
    return text_field(data, "display_name", "display name", NAME_MAX_LENGTH)


def message_content(data: Any) -> str:
    return text_field(data, "content", "message", MESSAGE_MAX_LENGTH, multiline=True)


def login_id(data: Any) -> str:
    value = data.get("id") if isinstance(data, dict) else None
    if not isinstance(value, str):
        raise ValidationError("login id is required")
    value = value.strip().lower()
    if not LOGIN_ID.fullmatch(value):
        raise ValidationError("login id must be 12 hexadecimal characters")
    return value


def room_id(data: Any) -> int:
    value = data.get("room_id") if isinstance(data, dict) else None
    # bool is an int subclass: True would otherwise mean room 1
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= SQLITE_INTEGER_MAX:
        raise ValidationError("room id must be a positive integer")
    return value
