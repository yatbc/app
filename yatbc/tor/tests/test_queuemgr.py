from django.test import TestCase, override_settings
from ..models import Torrent, TorrentQueue, TorrentType
from ..queuemgr import (
    add_to_queue_by_magnet,
    get_active_queue,
    add_to_queue_by_torrent_file,
    get_queue_folders,
    import_from_queue_folders,
    clean_active_downloads,
    MANUAL_POLICY,
)
from constance import config
from unittest.mock import patch, Mock

from pathlib import Path
from django.utils import timezone
import logging
from .temp_settings import console_logging_config
from .utils import create_file, create_work_dir, create_torrent, create_history
import shutil


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class QueueMgrTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.no_type = TorrentType.objects.get_no_type()

    def test_ok_add_to_queue_by_magnet(self):
        TorrentQueue.objects.all().delete()
        add_to_queue_by_magnet("magnet?test", self.no_type)
        result = [x for x in get_active_queue(1)]
        self.assertTrue(len(result), 1)
        self.assertTrue(result[0].torrent_type, self.no_type)

    def test_ok_add_to_queue_by_torrent_file(self):
        file_path, work_dir = create_file("text.torrent")
        queue = add_to_queue_by_torrent_file(file_path, self.no_type, private=False)
        self.assertEqual(queue.torrent_file_name, file_path.name)
        self.assertEqual(queue.torrent_private, False)
        file_path.unlink()
        work_dir.rmdir()

    def test_ok_get_queue_folders(self):
        config.QUEUE_DIR = "./test/"
        work_dir = create_work_dir(config.QUEUE_DIR)

        result = [x for x in get_queue_folders()]

        expected = (
            TorrentType.objects.all().count() * 2
        )  # public and private for each type
        self.assertEqual(len(result), expected)
        shutil.rmtree(work_dir)

    def test_ok_import_from_queue_folders(self):
        config.QUEUE_DIR = "./test/"
        work_dir = create_work_dir(config.QUEUE_DIR)
        files = []
        for path, type in get_queue_folders():
            file, _ = create_file(type.name.replace(" ", "_") + ".torrent", path)
            files.append(file.name)
        TorrentQueue.objects.all().delete()

        import_from_queue_folders()

        result = [x for x in get_active_queue()]
        expected = (
            TorrentType.objects.all().count() * 2
        )  # public and private for each type
        self.assertEqual(len(result), expected)
        for queue in result:
            self.assertTrue(queue.torrent_file_name in files)
        shutil.rmtree(work_dir)

    def _create_finished(self, private=False, cached=True, finished_at=timezone.now()):
        torrent = create_torrent(self.no_type)
        torrent.local_download_finished = True
        torrent.local_download_progress = 1
        torrent.finished_at = finished_at
        torrent.cached = cached
        torrent.private = private
        torrent.save()
        history = create_history(torrent)
        return torrent

    @patch(target="tor.queuemgr.delete_torrent_with_log")
    def test_auto_cleaning_policy_will_remove_all(self, delete_log: Mock):
        config.CLEAN_ACTIVE_DOWNLOADS_POLICY = MANUAL_POLICY + 1
        expected = 5
        for i in range(0, expected):
            self._create_finished()

        result = clean_active_downloads()
        self.assertEqual(expected, result)
        self.assertEqual(delete_log.call_count, expected)

    @patch(target="tor.queuemgr.delete_torrent_with_log")
    def test_auto_cleaning_policy_will_remove_inactive(self, delete_log: Mock):
        config.CLEAN_ACTIVE_DOWNLOADS_POLICY = MANUAL_POLICY + 1
        expected = 1
        self._create_finished(private=True)
        self._create_finished(finished_at=timezone.now(), cached=False)
        expected_delete = self._create_finished(finished_at="2000-01-01", cached=False)

        result = clean_active_downloads()
        self.assertEqual(expected, result)
        delete_log.assert_called_once_with(expected_delete)
