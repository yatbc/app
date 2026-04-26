import re
import logging
from .models import JackettSearchResultAudiobook, Person


def extract_title_author_series(parts: list[str]):
    title = None
    author = None
    series = None
    part = None
    if len(parts) == 0:
        return title, author, series, part
    if len(parts) == 2:
        title = parts[0].strip()
        author = parts[1].strip()
    elif len(parts) == 3:
        series = parts[0].strip()
        title = parts[1].strip()
        author = parts[2].strip()
    elif len(parts) == 1:
        title = parts[0].strip()
    elif len(parts) == 4:
        series = parts[1].strip()
        part = parts[2].strip()
        title = parts[0].strip()
        author = parts[3].strip()
        if part.lower().startswith("book"):
            part = part[4:].strip()

    book_tag = re.compile(r"([\w'\s]+)\,*\s*Book\s*(\d+)", re.IGNORECASE)
    if series:
        series_tag_found = book_tag.search(series)
        if series_tag_found:
            series = series_tag_found.group(1).strip()
            part = series_tag_found.group(2).strip()
    if "#" in title:
        series_tag = re.compile(r"\(([\w'\s]+)\s*#\s*(\d+)\)", re.IGNORECASE)
        series_tag_found = series_tag.search(title)
        if series_tag_found:
            series = series_tag_found.group(1).strip()
            part = series_tag_found.group(2).strip()
            title = title.replace(series_tag_found.group(0), "").strip()
    if part is None and series:
        part_tag = re.compile(r"\d+$")
        part_tag_found = part_tag.search(series)
        if part_tag_found:
            series = series.replace(part_tag_found.group(0), "").strip()
            part = part_tag_found.group(0).strip()
    return title, author, series, part


def have_author(author: str):
    if author is None:
        return False
    return Person.objects.filter(name__icontains=author).exists()


def extract_metadata(
    description: str,
    full_title: str,
    author: str,
    narrator: str,
    skip_author_check=False,
):
    logger = logging.getLogger("torbox")
    title_tag = re.compile(r"Title:\s*([\w'\s\,]+)")
    series_tag = re.compile(r"Series:\s*([\w'\s\,]+)\,\s*Book\s*(\d+)")
    author_by_tag = re.compile(r"By:\s*([\w'\s]+)")
    author_tag = re.compile(r"Author:\s*([\w'\s]+)")
    narrator_tag = re.compile(r"Read By:\s*([\w'\s]+)")
    sample_rate_tag = re.compile(r"(\[\d+\s*Kbps\])|(\[Variable\])")
    series_tag_found = None
    if description:
        series_tag_found = series_tag.search(description)
    series = None
    part = None
    title = full_title.strip()
    sample_rate = None
    sample_rate_found = sample_rate_tag.search(title)
    if sample_rate_found:
        sample_rate = sample_rate_found.group(0)
        title = title.replace(sample_rate, "").strip()
        sample_rate = sample_rate.strip("[]")

    extension = None
    extensions = ["MP3", "M4B", "AAC", "FLAC", "OGG", "OPUS"]
    for ext in extensions:
        ext = f"[{ext}]"
        if ext.lower() in title.lower():
            extension = ext.strip("[]")
            title = re.sub(re.escape(ext), "", title, flags=re.IGNORECASE)
            break
    languages = ["ENG"]
    for lang in languages:
        for ext in extensions:
            lang_ext = f"[{lang}/ {ext.lower()}]"
            if lang_ext in title.lower():
                extension = ext.strip("[]")
                title = title.replace(lang_ext, "").strip()
                break

    if author is None and description:
        author_tag_found = author_by_tag.search(description, re.IGNORECASE)
        if author_tag_found:
            author = author_tag_found.group(1)
    if author is None and description:
        author_tag_found = author_tag.search(description, re.IGNORECASE)
        if author_tag_found:
            author = author_tag_found.group(1)
    if description:
        narrator_tag_found = narrator_tag.search(description, re.IGNORECASE)
        if narrator_tag_found:
            narrator = narrator_tag_found.group(1)
        title_tag_found = title_tag.search(description, re.IGNORECASE)
        if title_tag_found:
            title = title_tag_found.group(1).strip()

    if series_tag_found:
        series = series_tag_found.group(1)
        part = series_tag_found.group(2)

    parts = title.split(" - ")
    extracted_title, extracted_author, extracted_series, extracted_part = (
        extract_title_author_series(parts)
    )
    if extracted_title is None:
        parts = title.split(" by ")  # for files like "Title by Author"
        extracted_title, extracted_author, extracted_series, extracted_part = (
            extract_title_author_series(parts)
        )

    if extracted_title:
        title = extracted_title
    if extracted_author and author is None:
        author = extracted_author
    if extracted_series and series is None:
        series = extracted_series
    if extracted_part and part is None:
        part = extracted_part

    # if author:
    #     title = title.replace(f" - {author}", "")
    #     title = title.replace(f" ({author})", "")
    #     title = title.replace(f" by {author}", "")
    #     title = title.replace(f"{author}", "")
    if part is None:
        # try to extract part from title
        part_search = re.search(r"(Volume|Vol\.|Book)\s*(\d+)", title)
        if part_search:
            part = part_search.group(2)
    if part:
        title = title.replace(f"Volume {part}", "")
        title = title.replace(f"Vol. {part}", "")
        title = title.replace(f"Book {part}", "")
        title = title.strip()
        if title.endswith(f","):
            title = title[:-1]
    title = title.replace(" (REQ)", "")
    title = title.strip()
    if not skip_author_check and have_author(author):
        logger.info(f"Author '{author}' exists in the database.")
    if not skip_author_check and have_author(title):
        logger.error(
            f"Detected title '{title}' as author, which exists in the database. This is likely a parsing error."
        )
        return None, None, None, None, extension, sample_rate, narrator

    return title, author, series, part, extension, sample_rate, narrator
