from django.test import TestCase, override_settings
from ..models import (
    Torrent,
    TorrentType,
)
from ..transmissionapi import (
    TransmissionApi,
    TRANSMISSION_CLIENT,
    transmission_have_free_download_slot,
    add_torrent_by_magnet,
)

from unittest.mock import patch, Mock
import unittest
from .temp_settings import console_logging_config
import logging
from .utils import create_torrent, create_torrent_file
from constance import config


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class TransmissionApiTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.no_type = TorrentType.objects.get(name="No Type")
        config.USE_TRANSMISSION = True

    def test_ok_add_torrent(self):
        api = unittest.mock.Mock(spec=TransmissionApi)
        api.add_torrent.return_value = unittest.mock.Mock(
            hash_string="fakehash", id="12345"
        )
        api.get_download_slots.return_value = 5

        add_torrent_by_magnet("magnet:?xt=fakehash&dn=test", self.no_type.id, api=api)

        api.add_torrent.assert_called_once_with(data="magnet:?xt=fakehash&dn=test")
        api.get_download_slots.assert_called_once_with()
        torrent = Torrent.objects.get(hash="fakehash")
        self.assertEqual(torrent.torrent_type, self.no_type)

    def test_have_free_download_slots(self):
        torrent1 = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        torrent1.download_finished = False
        torrent1.save()

        torrent2 = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        torrent2.download_finished = False
        torrent2.save()

        api = Mock(spec=TransmissionApi)
        api.get_download_slots.return_value = 2
        self.assertFalse(transmission_have_free_download_slot(api))
        api.get_download_slots.assert_called_once()
        torrent1.download_finished = True
        torrent1.save()
        self.assertTrue(transmission_have_free_download_slot(api))

    @patch(target="tor.transmissionapi.Client")
    def test_ok_request_dl_link(self, mock_client):
        torrent = create_torrent(self.no_type)
        torrent_file = create_torrent_file(torrent=torrent)
        expected_dir = "/fake/dir"
        expected_user = "test_user"
        expected_port = 1234
        expected_host = "my.test.host"
        expected_password = "secret"
        api = TransmissionApi(
            transmission_dir=expected_dir,
            sftp_user=expected_user,
            sftp_port=expected_port,
            sftp_host=expected_host,
            sftp_password=expected_password,
        )
        address = api.request_download_link(torrent, torrent_file)
        self.assertEqual(
            address,
            f"sftp://{expected_user}:{expected_password}@{expected_host}:{expected_port}{expected_dir}/{torrent_file.name}",
        )


if __name__ == "__main__":
    unittest.main()
