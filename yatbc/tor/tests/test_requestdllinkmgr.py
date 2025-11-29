from django.test import TestCase, override_settings
from ..models import (
    Torrent,
    TorrentFile,
    TorrentType,
    LogSource,
)
from ..requestdllinkmgr import request_dl_link
from ..torboxapi import (
    TORBOX_CLIENT,
)
from ..commondao import prepare_torrent_dir_name
import unittest

from .temp_settings import console_logging_config
import logging
from ..statusmgr import StatusMgr
from .utils import create_torrent, create_torrent_file
from constance import config


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class RequestDlLinkMgrTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.test_type = TorrentType.objects.create(
            name="Test",
            action_on_finish=TorrentType.ACTION_COPY,
            target_dir="Fake/Path/To/Target",
        )
        self.no_type = TorrentType.objects.get(name="No Type")

    def test_ok_request_dl(self):
        # Arrange
        aria_api = unittest.mock.Mock()
        aria_internal_id = "fake_aria_id"
        aria_api.download_file.return_value = (True, aria_internal_id)

        api = unittest.mock.Mock()
        url = "http://test"
        api.request_download_link.return_value = url

        torrent = create_torrent(self.no_type, local_download=False)
        path = f"{config.ARIA2_DIR}/{prepare_torrent_dir_name(torrent.name)}"
        file = create_torrent_file(torrent=torrent)

        status_mgr = StatusMgr.get_instance()

        # Act
        request_dl_link(
            torrent.id,
            api=api,
            aria_api=aria_api,
            status_mgr=status_mgr,
            aria_dir=config.ARIA2_DIR,
            client=TORBOX_CLIENT,
            source=LogSource.objects.get_torbox_api(),
        )

        # Assert
        aria_api.download_file.assert_called_once_with(
            link=url, target_name=file.short_name, target_folder=path, torrent=torrent
        )
        api.request_download_link.assert_called_once_with(torrent=torrent, file=file)
        torrent = Torrent.objects.get(id=torrent.id)
        self.assertTrue(torrent.local_download)
        file = TorrentFile.objects.get(torrent=torrent)
        self.assertEqual(file.aria.internal_id, aria_internal_id)


if __name__ == "__main__":
    unittest.main()
