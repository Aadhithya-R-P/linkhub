"""Stable, case-sensitive Base62 codes; these expose IDs, not secrets.

Never change the alphabet: existing codes depend on its ordering.
Decoding rejects leading zeroes, invalid characters, zero and IDs outside
PostgreSQL's positive INTEGER range. Never reset/reuse deleted link IDs.
"""

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
MAX_LINK_ID = 2_147_483_647


def encode_link_id(link_id: int) -> str:
    if not 1 <= link_id <= MAX_LINK_ID:
        raise ValueError("Link ID must be a positive PostgreSQL INTEGER")
    digits = []
    while link_id:
        link_id, remainder = divmod(link_id, len(ALPHABET))
        digits.append(ALPHABET[remainder])
    return "".join(reversed(digits))


def decode_short_code(short_code: str) -> int:
    # A positive PostgreSQL INTEGER needs at most six Base62 characters.
    if not short_code or len(short_code) > 6 or short_code.startswith("0"):
        raise ValueError("Invalid short code")
    link_id = 0
    for character in short_code:
        digit = ALPHABET.find(character)
        if digit == -1:
            raise ValueError("Invalid short code")
        link_id = link_id * len(ALPHABET) + digit
    if link_id > MAX_LINK_ID:
        raise ValueError("Invalid short code")
    return link_id
