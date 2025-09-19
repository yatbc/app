from django.test import TestCase, override_settings
from ..models import (
    Torrent,
    TorrentFile,
    TorrentType,
    TorrentTorBoxSearch,
    TorrentHistory,
    TorrentTorBoxSearchResult,
    TorrentQueue,
)
from ..torboxapi import (
    add_torrent_by_magnet,
    search_torrent,
    update_torrent_list,
    request_dl,
    TORBOX_CLIENT,
)
from ..commondao import prepare_torrent_dir_name
import unittest
import json
from pathlib import Path
from .temp_settings import console_logging_config
import logging
from django.utils import timezone
from .utils import create_torrent, create_torrent_file, create_search
from constance import config
from datetime import timedelta


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class TorboxApiTests(TestCase):
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

        # Act
        request_dl(torrent.id, api=api, aria_api=aria_api)

        # Assert
        aria_api.download_file.assert_called_once_with(
            link=url, target_name=file.short_name, target_folder=path, torrent=torrent
        )
        api.request_download_link.assert_called_once_with(torrent=torrent, file=file)
        torrent = Torrent.objects.get(id=torrent.id)
        self.assertTrue(torrent.local_download)
        file = TorrentFile.objects.get(torrent=torrent)
        self.assertEqual(file.aria.internal_id, aria_internal_id)

    def test_ok_add_torrent(self):
        api = unittest.mock.Mock()
        api.add_torrent.return_value = unittest.mock.Mock(
            hash="fakehash", torrent_id="12345"
        )
        api.get_max_download_slots.return_value = 5

        add_torrent_by_magnet("magnet:?xt=fakehash&dn=test", self.test_type.id, api=api)

        api.add_torrent.assert_called_once_with("magnet:?xt=fakehash&dn=test", None)
        api.get_max_download_slots.assert_called_once_with()
        torrent = Torrent.objects.get(hash="fakehash")
        self.assertEqual(torrent.torrent_type, self.test_type)

    def test_ok_update_torrent_list(self):
        api = unittest.mock.Mock()
        return_value = unittest.mock.Mock(
            active=True,
            hash="fakehash",
            size=123,
            created_at=timezone.now().isoformat(),
            download_finished=False,
            download_present=False,
            id_="123",
            magnet="magnet:?xt=fakehash&dn=test",
            download_speed=12,
            upload_speed=22,
            eta=0,
            peers=1,
            ratio=2,
            seeds=3,
            progress=2,
            updated_at=timezone.now().isoformat(),
            availability=3,
            download_state="downloading",
            _kwargs={
                "tracker": "test_tracker",
                "total_uploaded": 1234,
                "total_downloaded": 1233,
                "cached": False,
                "private": True,
            },
            files=None,
        )
        type(return_value).name = unittest.mock.PropertyMock(
            return_value="Test Torrent"
        )
        api.get_torrent_list.return_value = [return_value]

        update_torrent_list(api=api)

        api.get_torrent_list.assert_called_once()
        torrent = Torrent.objects.get(hash="fakehash")
        self.assertEqual(torrent.name, "Test Torrent")
        self.assertEqual(torrent.size, 123)
        self.assertEqual(torrent.torrent_type, self.no_type)
        self.assertEqual(torrent.internal_id, "123")
        self.assertEqual(torrent.private, True)
        self.assertEqual(torrent.cached, False)
        history = TorrentHistory.objects.get(torrent=torrent)
        self.assertEqual(history.download_speed, 12)

    def test_ok_search_torrent(self):
        api = unittest.mock.Mock()
        hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        api.search_torrent.return_value = json.loads(
            """
            {
                "data": {
                    "torrents": [
                        {
                            "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "raw_title": "Free.Movie",
                            "title": "Free Movie",
                            "title_parsed_data": {
                                "resolution": "2160p",
                                "quality": "Blu-ray",
                                "year": 1234,
                                "codec": "H.265",
                                "audio": "DD Mm 234",
                                "remux": true,
                                "title": "Free Movie",
                                "excess": [
                                    
                                ],
                                "encoder": "Free"
                            },
                            "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=Free.Movie",
                            "torrent": null,
                            "last_known_seeders": 123,
                            "last_known_peers": 342,
                            "size": 123123123,
                            "tracker": "free",
                            "categories": [
                            ],
                            "files": 0,
                            "type": "torrent",
                            "nzb": null,
                            "age": "123d",
                            "user_search": false,
                            "cached": true,
                            "owned": false
                        }
                    ]
                }
            }
            """
        )
        query = "fake_query"
        season = 1
        episode = 1

        search_torrent(query=query, season=season, episode=episode, api=api)

        api.search_torrent.assert_called_once_with(
            query, season=season, episode=episode
        )
        query = TorrentTorBoxSearch.objects.get(query=query)
        TorrentTorBoxSearchResult.objects.get(query=query, hash=hash)

    def test_search_with_old_entries(self):
        api = unittest.mock.Mock()
        hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        api.search_torrent.return_value = json.loads(
            """
            {
                "data": {
                    "torrents": [
                        {
                            "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "raw_title": "Free.Movie",
                            "title": "Free Movie",
                            "title_parsed_data": {
                                "resolution": "2160p",
                                "quality": "Blu-ray",
                                "year": 1234,
                                "codec": "H.265",
                                "audio": "DD Mm 234",
                                "remux": true,
                                "title": "Free Movie",
                                "excess": [
                                    
                                ],
                                "encoder": "Free"
                            },
                            "magnet": "magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&dn=Free.Movie",
                            "torrent": null,
                            "last_known_seeders": 123,
                            "last_known_peers": 342,
                            "size": 123123123,
                            "tracker": "free",
                            "categories": [
                            ],
                            "files": 0,
                            "type": "torrent",
                            "nzb": null,
                            "age": "123d",
                            "user_search": false,
                            "cached": true,
                            "owned": false
                        }
                    ]
                }
            }
            """
        )
        query = "fake_query"
        season = 1
        episode = 1
        query_object = TorrentTorBoxSearch.objects.create(
            query=query,
            season=season,
            episode=episode,
            date=timezone.now() - timedelta(days=1),
        )
        old = create_search(
            query=query,
            season=season,
            episode=episode,
            queue=TorrentQueue.objects.create(
                torrent_type=TorrentType.objects.get_no_type()
            ),
            query_object=query_object,
            title="Free.Movie",
            hash=hash,
        )

        search_torrent(query=query, season=season, episode=episode, api=api)

        api.search_torrent.assert_called_once_with(
            query, season=season, episode=episode
        )
        query = TorrentTorBoxSearch.objects.get(query=query)
        self.assertEqual(query, query_object)
        new = TorrentTorBoxSearchResult.objects.get(query=query, hash=hash)
        self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
