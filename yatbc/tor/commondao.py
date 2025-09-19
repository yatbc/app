from .models import (
    Torrent,
    Level,
    TorrentType,
    ErrorLog,
    TorrentErrorLog,
    TorrentFile,
    TorrentStatus,
    TorrentHistory,
    ArrErrorLog,
)
import math
from django.db.models import Q, OuterRef, Subquery, ExpressionWrapper, fields, F
import re
import logging
from django.db import connection
from django.utils import timezone
import bleach
from .common import TRANSMISSION_CLIENT, TORBOX_CLIENT


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


def add_log(message, level, source=None, torrent=None, local_status=None, arr=None):
    logger = logging.getLogger("torbox")
    log = ErrorLog.objects.create(message=message, level=level, source=source)
    if torrent:
        TorrentErrorLog.objects.create(torrent=torrent, error_log=log)
        if local_status:  # on "Status" screen
            torrent.local_status = local_status
            torrent.save()
    if arr:
        ArrErrorLog.objects.create(arr=arr, error_log=log)
    if level == Level.objects.get_error():
        logger.error(f"Message: {log.message}, source: {log.source}")
    if level == Level.objects.get_warning():
        logger.warning(f"Message: {log.message}, source: {log.source}")
    if level == Level.objects.get_info():
        logger.info(f"Message: {log.message}, source: {log.source}")
    return log


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
            level=Level.objects.get_info(),
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
        cached=entry._kwargs["cached"],
        private=entry._kwargs["private"],
    )


def map_torbox_entry_to_torrent_history(entry, torrent: Torrent):
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


def update_torrent(new_torrent: Torrent):
    from .statusmgr import StatusMgr

    status_mgr = StatusMgr.get_instance()
    logger = logging.getLogger("torbox")
    torrent = get_previous_torrent(new_torrent)
    INFO = Level.objects.get_info()

    if torrent:

        if torrent.deleted:
            torrent.redownload = True
            torrent.deleted = False
            logger.info(f"Redownloading torrent: {torrent}")
            add_log(
                message=f"Marking torrent: {torrent} as redownload",
                level=INFO,
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
        if torrent.private != new_torrent.private:
            torrent.private = new_torrent.private
        if torrent.cached != new_torrent.cached:
            torrent.cached = new_torrent.cached
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
                level=INFO,
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
        if torrent.local_status == status_mgr.client_init:
            status_mgr.remote_client_added_torrent(torrent)
        logger.debug("torrent already existed")
    else:

        status_mgr.remote_client_added_torrent(new_torrent)
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


def get_active_torrents_with_current_history():
    latest_details_subquery = (
        TorrentHistory.objects.filter(torrent_id=OuterRef("pk"))
        .order_by("-updated_at", "-pk")
        .values("pk")[:1]
    )
    return (
        Torrent.objects.filter(deleted=False)
        .annotate(latest_history_id=Subquery(latest_details_subquery))
        .annotate(
            age=ExpressionWrapper(
                timezone.now() - F("created_at"), output_field=fields.DurationField()
            )
        )
        .order_by("client")
    )


def get_history_with_age(history_id):
    return (
        TorrentHistory.objects.filter(id=history_id)
        .annotate(
            ago=ExpressionWrapper(
                timezone.now() - F("updated_at"), output_field=fields.DurationField()
            )
        )
        .first()
    )


def format_age(age_in_seconds: int):
    if age_in_seconds < 60:
        return "<1min"
    elif age_in_seconds < 3600:
        minutes = math.floor(age_in_seconds / 60)
        return f"{minutes}min"
    elif age_in_seconds < 86400:  # 60 * 60 * 24
        hours = math.floor(age_in_seconds / 3600)
        return f"{hours}h"
    else:
        days = math.floor(age_in_seconds / 86400)
        return f"{days}d"


def get_active_torrents_with_formatted_age():
    torrents = get_active_torrents_with_current_history()
    for obj in torrents:
        age_in_seconds = obj.age.total_seconds()
        obj.formatted_age = format_age(age_in_seconds)
    return torrents
