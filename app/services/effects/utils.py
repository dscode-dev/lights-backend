def palette_to_hue(palette: str) -> int:
    return {
        "blue": 160,
        "purple": 200,
        "green": 96,
        "orange": 24,
    }.get(palette, 160)