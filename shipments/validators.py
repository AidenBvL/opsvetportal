import re

from django.core.exceptions import ValidationError

CONTAINER_RE = re.compile(r"^[A-Z]{3}[UJZ]\d{7}$")
_LETTER_VALUES = {}
_value = 10
for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    if _value % 11 == 0:
        _value += 1
    _LETTER_VALUES[_letter] = _value
    _value += 1


def normalize_container_number(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def container_check_digit(first10: str) -> int:
    total = 0
    for i, ch in enumerate(first10):
        v = _LETTER_VALUES[ch] if ch.isalpha() else int(ch)
        total += v * (2**i)
    return total % 11 % 10


def is_valid_container_number(value: str) -> bool:
    value = normalize_container_number(value)
    if not CONTAINER_RE.match(value):
        return False
    return container_check_digit(value[:10]) == int(value[10])


def validate_container_number(value):
    if not is_valid_container_number(value):
        raise ValidationError(
            "%(value)s is geen geldig containernummer (ISO 6346: 4 letters + 7 cijfers, controlecijfer klopt niet).",
            params={"value": value},
        )
