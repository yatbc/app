from django.test import TestCase, override_settings

from ..arrutils import extract_metadata
import unittest

import logging
from .temp_settings import console_logging_config


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class ArrUtilsTests(TestCase):

    def setUp(self):
        logging.config.dictConfig(console_logging_config)

    def test_series_tag(self):
        desc_series = """
        My Free Book
        By: Open Source
        Narrated by: Volunteer
        Series: The Open Source World, Book 1
        """
        title, author, series, part, extension, sample_rate, narrator = (
            extract_metadata(
                description=desc_series,
                full_title="The Open Source World 1 - My Free Book (REQ) - Open Source",
                author="Open Source",
                narrator=None,
            )
        )
        self.assertEqual(series, "The Open Source World")
        self.assertEqual(part, "1")

    def test_just_title(self):
        title, author, series, part, extension, sample_rate, narrator = (
            extract_metadata(
                description=None,
                full_title="Just title",
                author=None,
                narrator=None,
            )
        )
        self.assertEqual(series, None)
        self.assertEqual(part, None)
        self.assertEqual(title, "Just title")
        self.assertEqual(author, None)
        self.assertEqual(narrator, None)

    def test_series_tag_in_title(self):
        title = "Magical Free Book 1 - Magical Series - Test Author [M4B] [128 Kbps]"
        title, author, series, part, extension, sample_rate, narrator = (
            extract_metadata(
                description=None,
                full_title=title,
                author=None,
                narrator=None,
            )
        )
        self.assertEqual(series, "Magical Free")
        self.assertEqual(part, "1")
        self.assertEqual(sample_rate, "128 Kbps")
        self.assertEqual(extension, "M4B")
        self.assertEqual(author, "Test Author")
        self.assertEqual(title, "Magical Series")
        self.assertEqual(narrator, None)


if __name__ == "__main__":
    unittest.main()
