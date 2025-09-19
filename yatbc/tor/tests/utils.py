from ..models import (
    Torrent,
    TorrentFile,
    TorrentType,
    TorrentHistory,
    TorrentStatus,
    TorrentTorBoxSearch,
    TorrentTorBoxSearchResult,
)
import shutil
from pathlib import Path
from ..torboxapi import TORBOX_CLIENT
from django.utils import timezone


def create_search(
    query,
    title,
    season,
    episode,
    torrent=None,
    query_object=None,
    raw_title="empty",
    queue=None,
    hash="fake",
) -> TorrentTorBoxSearchResult:
    if query_object is None:
        query_object = TorrentTorBoxSearch.objects.create(
            query=query, date=timezone.now()
        )
    return TorrentTorBoxSearchResult.objects.create(
        query=query_object,
        hash=hash,
        raw_title=raw_title,
        title=title,
        season=season,
        episode=episode,
        magnet="fake",
        age="0",
        cached=False,
        last_known_seeders=1,
        last_known_peers=1,
        size=1,
        torrent=torrent,
        queue=queue,
    )


def create_work_dir(name=None):
    if not name:
        name = "./test/"
    work_dir = Path(name)
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir()
    return work_dir


def create_file(file_name, work_dir=None):
    if not work_dir:
        work_dir = create_work_dir()
    file_path = work_dir / file_name
    with open(file_path, "w") as file:
        file.write("Test line")
    return file_path, work_dir


def create_torrent_file(
    torrent, aria=None, internal_id="asd1", name="Test", short_name="Short test name"
):
    return TorrentFile.objects.create(
        torrent=torrent,
        aria=aria,
        name=name,
        short_name=short_name,
        size=123,
        hash="hash",
        mime_type="Mime",
        internal_id=internal_id,
    )


def create_history(torrent: Torrent, updated_at="2000-01-01 00:11"):
    return TorrentHistory.objects.create(torrent=torrent, updated_at=updated_at)


def create_torrent(
    torrent_type,
    client=TORBOX_CLIENT,
    internal_id="123",
    local_download=True,
    created_at="2000-01-01 00:11",
):
    return Torrent.objects.create(
        active=True,
        hash="HASH",
        name="FakeName",
        size=123,
        created_at=created_at,
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
        local_status=TorrentStatus.objects.get(name="Unknown"),
    )
