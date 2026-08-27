# Persian receipt quotes

`persian_quotes.csv` is a byte-for-byte vendored copy of:

`/home/ali/Documents/Shaverma-Chi/Shaverma-Chi_old/persian_quotes/persian_quotes.csv`

The receipt service normalizes Persian characters, removes duplicates, and only
uses entries between 35 and 135 characters so an 80 mm thermal receipt remains
clear and reasonably short. Selection is deterministic per order number, which
keeps reprints consistent.
