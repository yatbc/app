from django.test import TestCase, override_settings
from ..models import Torrent, TorrentFile, TorrentType, AriaDownloadStatus
from ..ariaapi import (
    calculate_progress,
    exec_action_on_finish,
    update_status,
)
import unittest
import json
from pathlib import Path
import logging
from .temp_settings import console_logging_config
from .utils import create_torrent, create_torrent_file


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class AriaApiTests(TestCase):
    def _create_aria(self, progress, done=False):
        return AriaDownloadStatus.objects.create(
            internal_id="123",
            path=self.test_file.absolute().as_posix(),
            progress=progress,
            done=done,
            error="",
            status="",
        )

    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.test_data_dir = Path("test_data")
        self.test_data_dir.mkdir(exist_ok=True)
        self.target_dir = self.test_data_dir / "target"
        self.target_dir.mkdir(exist_ok=True)
        self.source_dir = self.test_data_dir / "source"
        self.source_dir.mkdir(exist_ok=True)
        self.test_file = self.source_dir / "test.txt"
        with open(self.test_file, "w") as f:
            f.write("This is a test file for AriaAPI tests.")
        self.test_type = TorrentType.objects.create(
            name="Test",
            action_on_finish=TorrentType.ACTION_COPY,
            target_dir=self.target_dir.absolute().as_posix(),
        )
        self.minimal_progress_torrent = create_torrent(self.test_type)
        self.minimal_progress = [0.1, 0.2, 0.3]
        for progress in self.minimal_progress:
            aria = self._create_aria(progress)
            create_torrent_file(aria=aria, torrent=self.minimal_progress_torrent)

        self.one_done_torrent = create_torrent(self.test_type)
        self.one_done_progress = [0.1, 1, 0.3]
        for progress in self.one_done_progress:
            aria = self._create_aria(progress, done=progress == 1)
            create_torrent_file(aria=aria, torrent=self.one_done_torrent)

        self.all_done_torrent = create_torrent(self.test_type)
        self.all_done_progress = [1, 1, 1]
        for progress in self.all_done_progress:
            aria = self._create_aria(progress, done=progress == 1)
            create_torrent_file(aria=aria, torrent=self.all_done_torrent)

    def test_minimal_progress(self):
        files = TorrentFile.objects.filter(torrent=self.minimal_progress_torrent)
        total, progress, done = calculate_progress(files)
        self.assertEqual(total, len(self.minimal_progress))
        self.assertAlmostEqual(progress, sum(self.minimal_progress, 0))
        self.assertEqual(done, [])

    def test_one_done_progress(self):
        files = TorrentFile.objects.filter(torrent=self.one_done_torrent)
        total, progress, done = calculate_progress(files)
        self.assertEqual(total, len(self.one_done_progress))
        self.assertAlmostEqual(progress, sum(self.one_done_progress, 0))
        self.assertEqual(done, [True])

    def test_all_done_progress(self):
        files = TorrentFile.objects.filter(torrent=self.all_done_torrent)
        total, progress, done = calculate_progress(files)
        self.assertEqual(total, len(self.all_done_progress))
        self.assertAlmostEqual(progress, sum(self.all_done_progress, 0))
        self.assertEqual(done, [True, True, True])
        self.assertEqual(total, len(self.all_done_progress))

    def test_execute_action_on_file(self):
        exec_action_on_finish(self.all_done_torrent)
        self.assertEqual(
            len(
                TorrentFile.objects.filter(
                    torrent=self.all_done_torrent, action_on_finish_done=True
                )
            ),
            len(self.all_done_progress),
        )

    # mock api
    def test_ok_update_status(self):
        aria_id = "12345"
        aria = AriaDownloadStatus.objects.create(
            path="/aria2/a.a",
            progress=0,
            done=False,
            error="",
            status="",
            internal_id=aria_id,
        )

        json_result = json.loads(
            '{"completedLength":"11","dir":"/aria2","downloadSpeed":"0","files":[{"completedLength":"11","index":"1","length":"120","path":"/aria2/a.a","selected":"true"}],"gid":"12345","status":"active","totalLength":"120"}'
        )
        api = unittest.mock.Mock()
        api.tellStatus.return_value = (True, json_result)

        update_status(aria_internal_id=aria_id, api=api)

        api.tellStatus.assert_called_once_with(aria_id)
        aria = AriaDownloadStatus.objects.get(internal_id=aria_id)
        self.assertAlmostEqual(aria.progress, 0.09166666)


if __name__ == "__main__":
    unittest.main()
