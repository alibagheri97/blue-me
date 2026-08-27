import csv
import hashlib
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path


QUOTE_FILE = Path(__file__).resolve().parent.parent / "data" / "persian_quotes.csv"
MIN_PRINTABLE_LENGTH = 35
MAX_PRINTABLE_LENGTH = 135
FALLBACK_QUOTE = {
    "body": "هر روز فرصتی تازه برای ساختن یک خاطره خوب است.",
    "author": "ناشناس",
}

_CHARACTER_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ۀ": "ه",
        "ة": "ه",
        "٠": "۰",
        "١": "۱",
        "٢": "۲",
        "٣": "۳",
        "٤": "۴",
        "٥": "۵",
        "٦": "۶",
        "٧": "۷",
        "٨": "۸",
        "٩": "۹",
        "0": "۰",
        "1": "۱",
        "2": "۲",
        "3": "۳",
        "4": "۴",
        "5": "۵",
        "6": "۶",
        "7": "۷",
        "8": "۸",
        "9": "۹",
        ",": "،",
        "\u00a0": " ",
        "\u200e": "",
        "\u200f": "",
        "\ufeff": "",
    }
)


@dataclass(frozen=True)
class PersianQuote:
    body: str
    author: str


def _clean(value: str | None) -> str:
    text = (value or "").translate(_CHARACTER_TRANSLATION)
    text = " ".join(text.split())
    return re.sub(r"\s+([،؛؟.!:])", r"\1", text).strip(' "')


@lru_cache(maxsize=1)
def printable_quotes() -> tuple[PersianQuote, ...]:
    quotes: list[PersianQuote] = []
    seen: set[tuple[str, str]] = set()
    try:
        with QUOTE_FILE.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, skipinitialspace=True):
                body = _clean(row.get("body"))
                author = _clean(row.get("author")) or "ناشناس"
                identity = (body, author)
                if not MIN_PRINTABLE_LENGTH <= len(body) <= MAX_PRINTABLE_LENGTH:
                    continue
                if identity in seen:
                    continue
                seen.add(identity)
                quotes.append(PersianQuote(body=body, author=author))
    except (OSError, csv.Error):
        return (PersianQuote(**FALLBACK_QUOTE),)
    return tuple(quotes) or (PersianQuote(**FALLBACK_QUOTE),)


def quote_for_order(order_number: str) -> dict[str, str]:
    quotes = printable_quotes()
    digest = hashlib.blake2b(order_number.encode("utf-8"), digest_size=8).digest()
    index = int.from_bytes(digest, byteorder="big") % len(quotes)
    return asdict(quotes[index])


def printable_quote_count() -> int:
    return len(printable_quotes())
