from .commondao import (
    add_log,
    torrent_file_to_log,
    torrent_to_log,
    prepare_torrent_dir_name,
    format_log_value,
)
from .models import Torrent, Level, TorrentFile, AriaDownloadStatus, LogSource
from .ariaapi import AriaApi
from .statusmgr import StatusMgr
import logging


def get_torrent_ready_to_download(torrent_id, client, source):
    try:
        torrent = Torrent.objects.get(
            pk=torrent_id, client=client, download_finished=True
        )
        if not torrent.internal_id:
            add_log(
                message=f"Torrent have no internal id: {torrent_to_log(torrent)}",
                level=Level.objects.get_error(),
                source=source,
                torrent=torrent,
            )
            return None
        return torrent
    except Exception as e:
        add_log(
            message=f"Can not find torrent to download: {torrent_id} for {client} and finished download",
            level=Level.objects.get_warning(),
            source=source,
        )
        return None


def get_files_ready_to_download(torrent_files: list[TorrentFile], source: LogSource):
    result = []
    for file in torrent_files:
        if not file.internal_id:
            add_log(
                message=f"Torrent file: {torrent_file_to_log(file)} has no internal id",
                level=Level.objects.get_error(),
                source=source,
                torrent=file.torrent,
            )
            return []
        if file.aria:
            add_log(
                message=f"Torrent file: {torrent_file_to_log(file)} already has aria id",
                level=Level.objects.get_info(),
                source=source,
                torrent=file.torrent,
            )
            continue
        result.append(file)
    return result


def request_dl_link(
    torrent_id: int,
    api,
    aria_api: AriaApi,
    status_mgr: StatusMgr,
    aria_dir: str,
    client: str,
    source: LogSource,
):
    logger = logging.getLogger("torbox")
    torrent = get_torrent_ready_to_download(
        torrent_id=torrent_id,
        client=client,
        source=source,
    )
    if not torrent:
        return
    logger.info(f"Torrent to local download: {torrent}")
    torrent_files = TorrentFile.objects.filter(torrent=torrent)
    if len(torrent_files) == 0:
        add_log(
            message="No torrent files found to download",
            level=Level.objects.get_warning(),
            source=source,
            torrent=torrent,
        )
        return
    files = get_files_ready_to_download(torrent_files=torrent_files, source=source)
    if not files:
        return
    if not api:
        raise Exception("No client api given")

    if not aria_api:
        raise Exception("No aria api given")

    request_data = []
    for file in files:
        result = api.request_download_link(torrent=torrent, file=file)
        if not result:
            logger.warning(
                f"Requesting link for torrent id: {torrent.id} failed, trying again"
            )
            result = api.request_download_link(torrent=torrent, file=file)
            if not result:
                status_mgr.remote_client_error(torrent)
                return
        request_data.append(
            {
                "url": result,
                "path": f"{aria_dir}/{prepare_torrent_dir_name(torrent.name)}",
                "file": file,
            }
        )

    # fixme: in case of an error, do we want to do something about files that already were requested? Aria is probably down, so not here.
    for request in request_data:
        url = request["url"]
        path = request["path"]
        file = request["file"]
        ok, aria_id = aria_api.download_file(
            link=url, target_name=file.short_name, target_folder=path, torrent=torrent
        )
        if not ok:
            logger.error(f"Could not request Aria to download file: {url}, stopping")
            return
        aria_download_status = AriaDownloadStatus.objects.create(
            internal_id=aria_id, path=path
        )
        file.aria = aria_download_status
        file.save()
        add_log(
            message=f"Torrent file: {torrent_file_to_log(file)} for torrent: {torrent_to_log(torrent)} send to Aria for download with id: {format_log_value(aria_id)} and path: {format_log_value(path)}",
            level=Level.objects.get_info(),
            source=source,
            torrent=torrent,
        )
    status_mgr.aria_new(torrent)
