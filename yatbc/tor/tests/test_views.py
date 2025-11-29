from django.test import TestCase, Client, override_settings
from django.urls import reverse
from ..models import TorrentQueue, TorrentType, ErrorLog, Level, LogSource
from ..commondao import add_log
import json
from .temp_settings import console_logging_config
from .utils import create_torrent, create_torrent_file, create_history


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class ViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.no_type = TorrentType.objects.get_no_type()
        self.torrent = create_torrent(self.no_type)
        self.torrent_hist = create_history(self.torrent)
        self.file1 = create_torrent_file(self.torrent)
        self.torrent2 = create_torrent(self.no_type)
        self.file2 = create_torrent_file(self.torrent2)
        self.info = Level.objects.get_info()

    def test_delete_queue(self):
        queue = TorrentQueue.objects.create(torrent_type=self.no_type)
        post_data = {"command": "single", "queue_id": queue.id}

        response = self.client.post(
            reverse("delete_queue"),
            json.dumps(post_data),
            content_type="application/json",
        )
        result = response.json()

        self.assertTrue("status" in result)

    def test_get_config(self):
        response = self.client.get(reverse("get_config"))
        result = response.json()
        self.assertTrue("configuration" in result)
        self.assertTrue("torrent_types" in result)
        self.assertTrue("QUEUE_DIR" in result["configuration"])
        self.assertEqual(
            len(result["torrent_types"]), TorrentType.objects.all().count()
        )

    def test_get_torrent_log(self):
        add_log(
            message="Test",
            level=self.info,
            source=LogSource.objects.get_aria_api(),
            torrent=self.torrent,
        )
        add_log(
            message="Test2",
            level=self.info,
            source=LogSource.objects.get_torbox_api(),
            torrent=self.torrent2,
        )
        response = self.client.get(reverse("get_torrent_log", args=[self.torrent.id]))
        result = response.json()
        self.assertEqual(
            len(result),
            ErrorLog.objects.filter(torrenterrorlog__torrent=self.torrent).count(),
        )

    def test_get_torrent_details(self):
        response = self.client.get(
            reverse("get_torrent_details", args=[self.torrent.id])
        )
        result = response.json()
        self.assertTrue("torrent" in result)
        self.assertTrue("files" in result)
        self.assertTrue("history" in result)

    def test_get_log_source(self):
        response = self.client.get(reverse("get_log_sources_list", args=[]))
        result = response.json()
        self.assertTrue("log_sources" in result)
        self.assertEqual(
            len(result["log_sources"]), LogSource.objects.all().count() + 1
        )  # +1 for ALL

    def test_force_finish_torrent(self):
        torrent = create_torrent(self.no_type)
        response = self.client.get(reverse("force_finish_torrent", args=[torrent.id]))
        result = response.json()
        print(result)
        self.assertTrue("status" in result)
        self.assertEqual(result["status"], "Ok")
        torrent.refresh_from_db()
        self.assertIsNotNone(torrent.finished_at)
        self.assertTrue(torrent.local_download_finished)
