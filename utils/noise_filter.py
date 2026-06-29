NOISE_TERMS = [
    "annual general meeting",
    "e-voting",
    "nsdl",
    "cdsl",
    "proxy form",
    "scrutinizer",
    "director liable to retire",
    "ordinary resolution",
    "special resolution",
    "notice is hereby given",
]


def is_noise_chunk(chunk: str) -> bool:

    chunk_lower = chunk.lower()

    matches = 0

    for term in NOISE_TERMS:

        if term in chunk_lower:
            matches += 1

    return matches >= 2