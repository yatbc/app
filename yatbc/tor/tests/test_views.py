from django.test import TestCase, Client, override_settings
from django.urls import reverse
from ..models import TorrentQueue, TorrentType
import json
from .temp_settings import console_logging_config


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class MyViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.no_type = TorrentType.objects.get(name="No Type")

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
