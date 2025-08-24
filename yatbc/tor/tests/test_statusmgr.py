from django.test import TestCase, override_settings
from ..models import Torrent, TorrentFile, TorrentType, AriaDownloadStatus
from ..statusmgr import StatusMgr
import unittest
import shutil
from pathlib import Path
from django.utils import timezone
import logging
from .temp_settings import console_logging_config
from .utils import create_torrent, create_torrent_file, create_file


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class StatusMgrTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.no_type = TorrentType.objects.get(name="No Type")
        self.torrent = create_torrent(self.no_type)

    def _prepare_torrent_done(self):
        file_path, work_dir = create_file("test.txt")

        test_type = TorrentType.objects.create(
            name="Test Type",
            action_on_finish=TorrentType.ACTION_MOVE,
            target_dir=work_dir.as_posix(),
        )
        aria = AriaDownloadStatus.objects.create(
            internal_id="test",
            path=file_path.as_posix(),
            progress=1,
            done=True,
            error="",
            status="complete",
            finished_at=timezone.now(),
        )
        torrent = create_torrent(test_type)
        create_torrent_file(torrent=torrent, aria=aria)
        return torrent, work_dir, file_path

    def test_torrent_done_does_not_remove_non_empty_source_dir(self):
        torrent, work_dir, file_path = self._prepare_torrent_done()

        status_mgr = StatusMgr.get_instance()

        status_mgr.torrent_done(torrent)
        self.assertEqual(torrent.local_status, status_mgr.finish_done)
        self.assertEqual(torrent.finished_at.date(), timezone.now().date())
        self.assertTrue(work_dir.exists())

    def test_torrent_done_does_remove_empty_source_dir(self):
        torrent, work_dir, file_path = self._prepare_torrent_done()
        file_path.unlink()

        status_mgr = StatusMgr.get_instance()

        status_mgr.torrent_done(torrent)
        self.assertEqual(torrent.local_status, status_mgr.finish_done)
        self.assertEqual(torrent.finished_at.date(), timezone.now().date())
        self.assertFalse(work_dir.exists())

    def test_remote_client_done(self):
        torbox_request_torrent_files_mock = unittest.mock.Mock()
        enqueue_mock = unittest.mock.Mock()
        torbox_request_torrent_files_mock.enqueue = enqueue_mock

        status_mgr = StatusMgr.get_instance()
        status_mgr.remote_client_done(self.torrent, torbox_request_torrent_files_mock)
        self.assertEqual(self.torrent.local_status, status_mgr.client_done)
        enqueue_mock.assert_called_once_with(self.torrent.id)

    def test_new_torrent(self):
        status_mgr = StatusMgr.get_instance()
        torrent = status_mgr.new_torrent(
            hash="aaaa",
            magnet="bbbb",
            torrent_type=self.no_type,
            internal_id="abc",
            client="TEST",
        )

        self.assertEqual(torrent.local_status, status_mgr.client_init)
