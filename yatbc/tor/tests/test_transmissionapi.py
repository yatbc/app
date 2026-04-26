from django.test import TestCase, override_settings
from ..models import Torrent, TorrentType, TorrentStatus, TorrentHistory
from ..transmissionapi import (
    TransmissionApi,
    TRANSMISSION_CLIENT,
    transmission_have_free_download_slot,
    add_torrent_by_magnet,
    transmission_status,
)
from transmission_rpc import Status
from transmission_rpc.torrent import Peer
from unittest.mock import patch, Mock
import unittest
from .temp_settings import console_logging_config
import logging
from .utils import create_torrent, create_torrent_file
from constance import config
from urllib.parse import quote
import datetime


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

    def test_peers_not_collected_when_disabled(self):
        # Arrange
        torrent = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        api = Mock(spec=TransmissionApi)
        return_value = [
            Mock(
                hash_string=torrent.hash,
                total_size=1024,
                added_date=datetime.datetime.now(tz=datetime.timezone.utc),
                seeding=False,
                seed_pending=False,
                uploaded_ever=0,
                downloaded_ever=512,
                magnet_link="magnet:?xt=fakehash&dn=test",
                is_private=False,
                id=torrent.internal_id,
                trackers=None,
                status=Status.DOWNLOADING,
                activity_date=datetime.datetime.now(tz=datetime.timezone.utc),
                rate_download=12,
                rate_upload=1,
                eta=None,
                peers_getting_from_us=2,
                ratio=0.5,
                peers_sending_to_us=3,
                desired_available=1,
                progress=12,
                peers=[
                    Mock(
                        spec=Peer,
                        address="fakeaddress1",
                        client_name="FakeClient1",
                        progress=0.5,
                        rate_to_client=20,
                        rate_to_peer=10,
                        peer_is_interested=True,
                        flag_str="DL",
                        is_incoming=False,
                    ),
                    Mock(
                        spec=Peer,
                        address="fakeaddress2",
                        client_name="FakeClient2",
                        progress=0.5,
                        rate_to_client=30,
                        rate_to_peer=15,
                        peer_is_interested=False,
                        flag_str="UL",
                        is_incoming=True,
                    ),
                ],
            )
        ]
        return_value[0].get_files.return_value = []
        type(return_value[0]).name = unittest.mock.PropertyMock(
            return_value="Test Torrent"
        )
        api.get_torrents.return_value = return_value
        config.COLLECT_PEER_INFO = False

        # Act
        transmission_status(api=api)

        # Assert
        api.get_torrents.assert_called_once()
        torrent.refresh_from_db()
        history = TorrentHistory.objects.filter(torrent=torrent).latest("updated_at")
        self.assertIsNotNone(history)
        self.assertEqual(history.torrentpeer_set.count(), 0)

    def test_peers_collected(self):
        # Arrange
        torrent = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        api = Mock(spec=TransmissionApi)
        return_value = [
            Mock(
                hash_string=torrent.hash,
                total_size=1024,
                added_date=datetime.datetime.now(tz=datetime.timezone.utc),
                seeding=False,
                seed_pending=False,
                uploaded_ever=0,
                downloaded_ever=512,
                magnet_link="magnet:?xt=fakehash&dn=test",
                is_private=False,
                id=torrent.internal_id,
                trackers=None,
                status=Status.DOWNLOADING,
                activity_date=datetime.datetime.now(tz=datetime.timezone.utc),
                rate_download=12,
                rate_upload=1,
                eta=None,
                peers_getting_from_us=2,
                ratio=0.5,
                peers_sending_to_us=3,
                desired_available=1,
                progress=12,
                peers=[
                    Mock(
                        spec=Peer,
                        address="fakeaddress1",
                        client_name="FakeClient1",
                        progress=0.5,
                        rate_to_client=20,
                        rate_to_peer=10,
                        peer_is_interested=True,
                        flag_str="DL",
                        port=6881,
                        # bytes_to_client=2048,
                        # bytes_to_peer=1024,
                        client_is_choked=False,
                        peer_is_choked=True,
                        client_is_interested=True,
                        is_incoming=False,
                    ),
                    Mock(
                        spec=Peer,
                        address="fakeaddress2",
                        client_name="FakeClient2",
                        progress=0.5,
                        rate_to_client=30,
                        rate_to_peer=15,
                        peer_is_interested=False,
                        flag_str="UL",
                        port=6882,
                        # bytes_to_client=248,
                        # bytes_to_peer=124,
                        client_is_choked=True,
                        peer_is_choked=False,
                        client_is_interested=True,
                        is_incoming=True,
                    ),
                ],
            )
        ]
        return_value[0].get_files.return_value = []
        type(return_value[0]).name = unittest.mock.PropertyMock(
            return_value="Test Torrent"
        )
        api.get_torrents.return_value = return_value
        config.COLLECT_PEER_INFO = True

        # Act
        transmission_status(api=api)

        # Assert
        api.get_torrents.assert_called_once()
        torrent.refresh_from_db()
        history = TorrentHistory.objects.filter(torrent=torrent).latest("updated_at")
        self.assertIsNotNone(history)
        self.assertEqual(history.torrentpeer_set.count(), 2)
        history_peer1 = history.torrentpeer_set.get(address="fakeaddress1")
        self.assertEqual(history_peer1.client, "FakeClient1")
        self.assertEqual(history_peer1.progress, 0.5)
        self.assertEqual(history_peer1.downloaded, 0)
        self.assertEqual(history_peer1.uploaded, 0)
        self.assertTrue(history_peer1.peer_is_interested)
        self.assertEqual(history_peer1.flags, "DL")
        self.assertFalse(history_peer1.is_incoming)
        history_peer2 = history.torrentpeer_set.get(address="fakeaddress2")
        self.assertEqual(history_peer2.client, "FakeClient2")
        self.assertEqual(history_peer2.progress, 0.5)
        self.assertEqual(history_peer2.downloaded, 0)
        self.assertEqual(history_peer2.uploaded, 0)
        self.assertFalse(history_peer2.peer_is_interested)
        self.assertEqual(history_peer2.flags, "UL")
        self.assertTrue(history_peer2.is_incoming)

    def test_have_free_download_slots(self):
        torrent1 = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        torrent1.local_status = TorrentStatus.objects.get_client_in_progress()
        torrent1.save()

        torrent2 = create_torrent(self.no_type, client=TRANSMISSION_CLIENT)
        torrent2.local_status = TorrentStatus.objects.get_client_init()
        torrent2.save()

        api = Mock(spec=TransmissionApi)
        api.get_download_slots.return_value = 2
        self.assertFalse(transmission_have_free_download_slot(api))
        api.get_download_slots.assert_called_once()
        torrent1.local_status = TorrentStatus.objects.get_client_done()
        torrent1.save()
        self.assertTrue(transmission_have_free_download_slot(api))

    @patch(target="tor.transmissionapi.Client")
    def test_ok_request_dl_link(self, mock_client):
        torrent = create_torrent(self.no_type)
        torrent_file = create_torrent_file(
            torrent=torrent, name="encoded# path/file1.txt"
        )
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
        result = api.request_download_links(torrent)
        self.assertIsNotNone(result)
        address, file = result[0]
        self.assertEqual(file, torrent_file)
        self.assertEqual(
            address,
            f"sftp://{expected_user}:{expected_password}@{expected_host}:{expected_port}{expected_dir}/{quote(torrent_file.name)}",
        )


if __name__ == "__main__":
    unittest.main()
