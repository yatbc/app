from .models import (
    Torrent,
    TorrentTorBoxSearchResult,
    TorrentType,
    ErrorLog,
    TorrentErrorLog,
    TorrentFile,
    TorrentHistory,
)
from django.db.models import Q
import re
import logging
from django.db import connection
import bleach

TORBOX_CLIENT = "TorBox"
TRANSMISSION_CLIENT = "Transmission"


def clean_html(html):
    html = str(html)
    allowed_tags = []
    allowed_attrs = []
    return bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)


def format_log_value(value):
    value = clean_html(str(value))
    return f"<i>'{value}'</i>"


def torrent_to_log(torrent: Torrent):
    if not torrent:
        return "<i>'(No torrent)'</i>"

    name = clean_html(torrent.name)
    if len(name) > 50 + 3:
        name = name[:50] + "..."
    return f"<i>'{name}'(id: {torrent.id})</i><br/>"


def torrent_file_to_log(file: TorrentFile):
    if not file:
        return "<i>'(No file)'</i>"

    name = clean_html(file.name)
    if len(name) > 100 + 3:
        name = name[:100] + "..."
    return f"<i>'{name}'(id: {file.id})</i><br/>"


def add_log(message, level="INFO", source=None, torrent=None, local_status=None):
    logger = logging.getLogger("torbox")
    log = ErrorLog.objects.create(message=message, level=level, source=source)
    if torrent:
        TorrentErrorLog.objects.create(torrent=torrent, error_log=log)
        if local_status:  # on "Status" screen
            torrent.local_status = local_status
            torrent.local_status_level = level
            torrent.save()
    if log.level == "ERROR":
        logger.error(f"Message: {log.message}, source: {log.source}")
    if log.level == "WARNING":
        logger.warning(f"Message: {log.message}, source: {log.source}")
    if log.level == "INFO":
        logger.info(f"Message: {log.message}, source: {log.source}")
    return log


class TorrentLog:
    def __init__(self, message, level, source, torrent=None, local_status=None):
        self.message = message
        self.level = level
        self.source = source
        self.torrent = torrent
        self.local_status = local_status

    def log(self):
        add_log(
            self.message,
            self.level,
            self.source,
            self.torrent,
            local_status=self.local_status,
        )


def log_on_exit(func):
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, TorrentLog):
            result.log()
            return
        return result

    return wrapper


def prepare_torrent_dir_name(torrent_name: str):
    return clean_html(torrent_name)


def get_previous_torrent(new_torrent: Torrent):
    result = Torrent.objects.filter(hash=new_torrent.hash, client=new_torrent.client)
    if result:
        result = result[0]
        return result

    return None


def update_double(torrent):
    logger = logging.getLogger("torbox")
    double = Torrent.objects.exclude(Q(pk=torrent.pk) | Q(deleted=True)).filter(
        hash=torrent.hash
    )
    if torrent.doubled and not double:
        torrent.doubled = False
        torrent.save()
        logger.debug(f"Torrent no longer a double: {torrent}")
        return

    if double:
        double = double[0]
        double.doubled = True
        double.save()
        torrent.double = True
        torrent.save()
        logger.debug(f"Updating double status for: {double} {torrent}")


def update_type(torrent: Torrent):
    logger = logging.getLogger("torbox")
    no_type = TorrentType.objects.get(name="No Type")
    if torrent.torrent_type != no_type:
        logger.debug(f"Torrent {torrent} already had a type, skipping type update")
        return
    movie_series = TorrentType.objects.get(name="Movie Series")
    result = re.search("[sS]\\d{1,2}([eE]\\d{1,2})*", torrent.name)
    if result:
        logger.info(
            f"Found movie series marker, changing type to movie series for torrent: {torrent}"
        )
        torrent.torrent_type = movie_series
        torrent.save()
        add_log(
            message=f"Torrent {torrent.name} with hash: {torrent.hash} was added with season/episode marker, updating as movie series type",
            level="INFO",
            source="torboxapi",
            torrent=torrent,
        )
        return
    logger.info(f"Couldn't determine type for torrent: {torrent}, leaving with No Type")


def map_torbox_entry_to_torrent(entry, no_type):
    return Torrent(
        active=entry.active,
        hash=entry.hash,
        name=entry.name,
        size=entry.size,
        created_at=entry.created_at,
        download_finished=entry.download_finished,
        download_present=entry.download_present,
        tracker=entry._kwargs["tracker"],
        total_uploaded=entry._kwargs["total_uploaded"],
        total_downloaded=entry._kwargs["total_downloaded"],
        client=TORBOX_CLIENT,
        internal_id=entry.id_,
        magnet=entry.magnet,
        torrent_type=no_type,
    )


def map_torbox_entry_to_torrent_history(entry, torrent):
    return TorrentHistory(
        torrent=torrent,
        download_speed=entry.download_speed,
        upload_speed=entry.upload_speed,
        eta=entry.eta,
        peers=entry.peers,
        ratio=entry.ratio,
        seeds=entry.seeds,
        progress=entry.progress,
        updated_at=entry.updated_at,
        availability=entry.availability,
        state=entry.download_state,
    )


def update_torrent(new_torrent):
    logger = logging.getLogger("torbox")
    torrent = get_previous_torrent(new_torrent)

    if torrent:
        if torrent.deleted:
            torrent.redownload = True
            torrent.deleted = False
            logger.info(f"Redownloading torrent: {torrent}")
            add_log(
                message=f"Marking torrent: {torrent} as redownload",
                level="INFO",
                source="torboxapi",
                torrent=torrent,
            )
        if (
            torrent.internal_id
            and new_torrent.internal_id
            and int(torrent.internal_id) != int(new_torrent.internal_id)
        ):
            logger.info(
                f"Updated internal id for torrent: {torrent}, old: {torrent.internal_id}, new: {new_torrent.internal_id}"
            )
        if torrent.name != new_torrent.name:
            torrent.name = new_torrent.name
        if torrent.size != new_torrent.size:
            torrent.size = new_torrent.size
        if (
            new_torrent.torrent_type != torrent.torrent_type
            and torrent.torrent_type.name == "No Type"
        ):
            logger.info(
                f"New torrent: {new_torrent} has different type than previous torrent {torrent}"
            )
            add_log(
                message=f"New torrent: {torrent_to_log(new_torrent)} has type: {format_log_value(new_torrent.torrent_type.name)}, and old torrent: {torrent_to_log(torrent)} has No Type, updating type to the new one",
                level="INFO",
                source="torboxapi",
                torrent=torrent,
            )
            torrent.torrent_type = new_torrent.torrent_type

        torrent.active = new_torrent.active
        torrent.total_uploaded = new_torrent.total_uploaded
        torrent.total_downloaded = new_torrent.total_downloaded
        torrent.download_present = new_torrent.download_present
        torrent.download_finished = new_torrent.download_finished
        torrent.internal_id = new_torrent.internal_id

        torrent.save()
        logger.debug("torrent already existed")
    else:
        new_torrent.save()
        logger.debug(f"adding new torrent: {new_torrent}, {new_torrent.internal_id}")
        add_log(
            message=f"New torrent created: {torrent_to_log(new_torrent)} with hash: <i>'{new_torrent.hash}'</i>",
            level="INFO",
            source="torboxapi",
            torrent=new_torrent,
            local_status="TorBox: added",
        )
        torrent = new_torrent
    update_double(torrent)
    update_type(torrent)

    return torrent


def mark_deleted_torrents(not_deleted, clients):
    logger = logging.getLogger("torbox")
    ids_to_exclude = [obj.pk for obj in not_deleted]
    logger.debug(f"Update delete: {ids_to_exclude}, {clients}")
    Torrent.objects.exclude(Q(pk__in=ids_to_exclude) | Q(client__in=clients)).update(
        deleted=True
    )
