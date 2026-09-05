from pathlib import Path
import sys

from bs4 import BeautifulSoup


def clean(text):
    return " ".join(text.split())


def inspect(path):
    html = Path(path).read_text(
        encoding="utf-8",
        errors="ignore",
    )

    soup = BeautifulSoup(html, "html.parser")

    print("=" * 100)
    print(path)
    print("=" * 100)

    print()
    print("HTML TITLE:")
    print(
        clean(soup.title.get_text(" ", strip=True))
        if soup.title else ""
    )

    print()
    print("H1:")
    for tag in soup.find_all("h1"):
        text = clean(tag.get_text(" ", strip=True))
        if text:
            print("-", text)

    print()
    print("HEADINGS:")

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        text = clean(tag.get_text(" ", strip=True))

        if text:
            print(
                f"{tag.name.upper():>3}  {text}"
            )


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        inspect(arg)
