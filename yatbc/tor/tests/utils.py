from ..models import Torrent, TorrentFile, TorrentType, AriaDownloadStatus
from ..torboxapi import TORBOX_CLIENT


def create_torrent_file(torrent, aria=None, internal_id="asd1"):
    return TorrentFile.objects.create(
        torrent=torrent,
        aria=aria,
        name="Test",
        short_name="Shor test name",
        size=123,
        hash="hash",
        mime_type="Mime",
        internal_id=internal_id,
    )


def create_torrent(
    torrent_type, client=TORBOX_CLIENT, internal_id="123", local_download=True
):
    return Torrent.objects.create(
        active=True,
        hash="HASH",
        name="FakeName",
        size=123,
        created_at="2000-01-01 00:11",
        download_finished=True,
        download_present=True,
        tracker="",
        total_uploaded=0,
        total_downloaded=0,
        client=client,
        internal_id=internal_id,
        deleted=False,
        magnet=None,
        doubled=False,
        local_download_finished=False,
        local_download=local_download,
        local_download_progress=0.0,
        redownload=False,
        torrent_type=torrent_type,
    )
