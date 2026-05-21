import re
import pathlib

for svg in pathlib.Path("figures").glob("*.svg"):
    text = svg.read_text(encoding="utf-8")
    # Remove the main title <text> block (font-size="24" font-weight="700")
    cleaned = re.sub(
        r'\n  <text[^>]*font-size="24"[^>]*font-weight="700"[^>]*>.*?</text>',
        "",
        text,
        flags=re.DOTALL,
    )
    svg.write_text(cleaned, encoding="utf-8")
    removed = len(text) != len(cleaned)
    print(f"{'Cleaned' if removed else 'No match'}: {svg.name}")
