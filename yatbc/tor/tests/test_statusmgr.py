from django.test import TestCase, override_settings
from ..models import Torrent, TorrentFile, TorrentType, AriaDownloadStatus, LogSource
from ..statusmgr import StatusMgr
import unittest
import shutil
from pathlib import Path
from django.utils import timezone
import logging
from .temp_settings import console_logging_config
from .utils import create_torrent, create_torrent_file, create_file
from constance import config
from ..requestdllinkmgr import (
    get_files_ready_to_download,
)


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class StatusMgrTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.no_type = TorrentType.objects.get_no_type()
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

    def test_transition_in_client_done_if_needed_skip_first(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        torrent.local_status = status_mgr.client_progress
        files = [create_torrent_file(torrent=torrent)]
        config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX = True
        status_mgr.transition_in_client_done_if_needed(
            torrent=torrent, files=files, request_torrent_files=unittest.mock.Mock()
        )
        self.assertEqual(torrent.local_status, status_mgr.finish_done)

    def test_transition_in_client_done_if_needed_ok(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        torrent.local_status = status_mgr.client_progress
        files = [create_torrent_file(torrent=torrent)]
        config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX = False
        request_files_task = unittest.mock.Mock()
        status_mgr.transition_in_client_done_if_needed(
            torrent=torrent, files=files, request_torrent_files=request_files_task
        )
        self.assertEqual(torrent.local_status, status_mgr.client_done)
        request_files_task.enqueue.assert_called_once_with(torrent.id)

    def test_transition_in_client_done_if_needed_statuses_check(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        torrent.local_status = status_mgr.client_done
        torrent.save()
        files = [create_torrent_file(torrent=torrent)]
        config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX = False
        request_files_task = unittest.mock.Mock()
        status_mgr.transition_in_client_done_if_needed(
            torrent=torrent, files=files, request_torrent_files=request_files_task
        )
        request_files_task.enqueue.assert_not_called()
        self.assertEqual(torrent.local_status, status_mgr.client_done)

        torrent.local_status = status_mgr.finish_done
        torrent.save()

        status_mgr.transition_in_client_done_if_needed(
            torrent=torrent, files=files, request_torrent_files=request_files_task
        )
        request_files_task.enqueue.assert_not_called()
        self.assertEqual(torrent.local_status, status_mgr.finish_done)

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

    def test_remote_client_error(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        status_mgr.remote_client_error(torrent)
        torrent.refresh_from_db()

        self.assertEqual(torrent.local_status, status_mgr.client_error)

    def test_no_transition_in_client_done_no_files(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        torrent.local_status = status_mgr.client_progress
        status_mgr.transition_in_client_done_if_needed(
            torrent=torrent, files=[], request_torrent_files=unittest.mock.Mock()
        )
        self.assertEqual(torrent.local_status, status_mgr.client_progress)

    def test_force_transition_in_done(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        torrent.local_status = status_mgr.client_progress
        status_mgr.force_transition_in_done(torrent)
        self.assertEqual(torrent.local_status, status_mgr.finish_done)
        self.assertIsNotNone(torrent.finished_at)
        self.assertTrue(torrent.local_download_finished)

    def test_force_transition_in_client_progress(self):
        status_mgr = StatusMgr.get_instance()
        torrent = create_torrent(torrent_type=self.no_type)
        aria = AriaDownloadStatus.objects.create(
            internal_id="test",
            path="/tmp/test",
            progress=1,
            done=True,
        )
        file = create_torrent_file(torrent=torrent, aria=aria)
        status_mgr.torrent_done(torrent, skipped_download=True)
        self.assertEqual(torrent.local_status, status_mgr.finish_done)
        self.assertEqual(
            get_files_ready_to_download(
                torrent_files=[file], source=LogSource.objects.get_status_mgr()
            ),
            [],
        )
        status_mgr.force_transition_in_client_progress(torrent)

        self.assertEqual(TorrentFile.objects.filter(torrent=torrent).count(), 0)
        self.assertEqual(torrent.local_status, status_mgr.client_progress)
