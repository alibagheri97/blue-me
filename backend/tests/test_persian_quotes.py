from app.services.persian_quotes import (
    MAX_PRINTABLE_LENGTH,
    MIN_PRINTABLE_LENGTH,
    printable_quote_count,
    printable_quotes,
    quote_for_order,
)


def test_vendored_quote_catalog_is_clean_and_receipt_sized():
    quotes = printable_quotes()

    assert printable_quote_count() == 457
    assert len({(quote.body, quote.author) for quote in quotes}) == len(quotes)
    assert all(
        MIN_PRINTABLE_LENGTH <= len(quote.body) <= MAX_PRINTABLE_LENGTH
        for quote in quotes
    )
    assert all(quote.author for quote in quotes)
    assert all("ي" not in quote.body and "ك" not in quote.body for quote in quotes)


def test_quote_selection_is_stable_for_receipt_reprints():
    first = quote_for_order("BM-260827-TEST01")
    reprint = quote_for_order("BM-260827-TEST01")

    assert reprint == first
    assert set(first) == {"body", "author"}
    assert MIN_PRINTABLE_LENGTH <= len(first["body"]) <= MAX_PRINTABLE_LENGTH
