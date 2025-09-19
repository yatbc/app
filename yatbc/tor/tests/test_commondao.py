from django.test import TestCase, override_settings
from ..models import Torrent, TorrentFile, TorrentType, AriaDownloadStatus
from ..commondao import (
    get_active_torrents_with_current_history,
    get_active_torrents_with_formatted_age,
)
from ..common import (
    get_name_from_magnet,
)
import unittest
from django.utils import timezone
from pathlib import Path
import logging
from .temp_settings import console_logging_config
from .utils import create_torrent, create_history


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class CommonDaoTests(TestCase):

    def setUp(self):
        logging.config.dictConfig(console_logging_config)

    def test_get_active_torrents_with_current_history(self):
        Torrent.objects.all().delete()
        for i in range(5):
            torrent = create_torrent(
                TorrentType.objects.get_no_type(), created_at=f"2024-01-0{i+1} 00:00"
            )
            create_history(torrent, updated_at=f"2024-01-0{i+1} 10:00")
        torrent = create_torrent(
            TorrentType.objects.get_no_type(), created_at="2024-01-01 00:00"
        )
        create_history(torrent, updated_at="2024-01-01 10:00")
        result = get_active_torrents_with_current_history()
        self.assertEqual(len(result), 6)

    def test_get_active_torrents_days_ago(self):
        Torrent.objects.all().delete()
        days = timezone.now() - timezone.timedelta(days=5)
        torrent = create_torrent(TorrentType.objects.get_no_type(), created_at=days)
        create_history(torrent, updated_at=days)

        result = get_active_torrents_with_formatted_age()
        self.assertTrue(result[0].formatted_age == "5d")

    def test_get_active_torrents_hours_ago(self):
        Torrent.objects.all().delete()
        ago = timezone.now() - timezone.timedelta(hours=5)
        torrent = create_torrent(TorrentType.objects.get_no_type(), created_at=ago)
        create_history(torrent, updated_at=ago)

        result = get_active_torrents_with_formatted_age()
        self.assertTrue(result[0].formatted_age == "5h")

    def test_get_active_torrents_minutes(self):
        Torrent.objects.all().delete()
        ago = timezone.now() - timezone.timedelta(minutes=5)
        torrent = create_torrent(TorrentType.objects.get_no_type(), created_at=ago)
        create_history(torrent, updated_at=ago)

        result = get_active_torrents_with_formatted_age()
        self.assertTrue(result[0].formatted_age == "5min")

    def test_get_active_torrents_seconds(self):
        Torrent.objects.all().delete()
        ago = timezone.now() - timezone.timedelta(seconds=5)
        torrent = create_torrent(TorrentType.objects.get_no_type(), created_at=ago)
        create_history(torrent, updated_at=ago)

        result = get_active_torrents_with_formatted_age()
        self.assertTrue(result[0].formatted_age == "<1min")

    def test_get_name_from_magnet(self):
        name = get_name_from_magnet(
            "magnet:?xt=urn:btih:abcdef1234567890&dn=Example+Name+Here&tr=udp://tracker.example.com:80/announce"
        )
        self.assertEqual(name, "Example Name Here")

        name = get_name_from_magnet(
            "magnet:?xt=urn:btih:abcdef1234567890&tr=udp://tracker.example.com:80/announce"
        )
        self.assertIsNone(name)

        name = get_name_from_magnet("not a magnet link")
        self.assertIsNone(name)


if __name__ == "__main__":
    unittest.main()
