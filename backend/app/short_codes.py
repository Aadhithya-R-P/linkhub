"""Stable, case-sensitive Base62 codes; these expose IDs, not secrets.

Never change the alphabet: existing codes depend on its ordering. Future
decoding must reject leading zeroes, invalid characters, zero and IDs outside
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
