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
    LogSource,
    TorrentQueue,
)
from timeit import default_timer as timer
from django.db.models import Max, OuterRef, Subquery
from django.db.models.functions import TruncDate
import math
from django.db.models import Q, OuterRef, Subquery, ExpressionWrapper, fields, F
import re
import logging
from django.db import connection
from django.utils import timezone
import bleach
from datetime import date
from .common import TRANSMISSION_CLIENT, TORBOX_CLIENT
from django.forms.models import model_to_dict
from constance import config


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


def add_log(
    message, level, source=LogSource, torrent=None, local_status=None, arr=None
):
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
        logger.error(f"Message: {log.message}, source: {log.source.name}")
    if level == Level.objects.get_warning():
        logger.warning(f"Message: {log.message}, source: {log.source.name}")
    if level == Level.objects.get_info():
        logger.info(f"Message: {log.message}, source: {log.source.name}")
    return log


def prepare_torrent_dir_name(torrent_name: str):
    logger = logging.getLogger("torbox")
    cleaned = clean_html(torrent_name)
    logger.debug(f"Preparing torrent dir name for: {torrent_name} cleaned: {cleaned}")
    return cleaned


def get_torrent_ides(torrent_map: dict):
    torrent_ids = []
    for _, mapping in torrent_map.items():
        old_torrent = mapping[
            "old"
        ]  # we are only interested in previous torrents, new torrents will newer have history, and double are from different client
        if old_torrent:
            torrent_ids.append(old_torrent.pk)

    return torrent_ids


def get_previous_torrents(torrent_map: dict, client: str):
    start = timer()
    logger = logging.getLogger("torbox")
    # torrent map should contain: [key] => {"new": not saved torrent, "old": None, "double": None}
    result = Torrent.objects.filter(hash__in=torrent_map.keys())
    for torrent in result:
        if torrent.client == client:
            torrent_map[torrent.hash]["old"] = torrent
        elif torrent.client != client and not torrent.deleted:
            torrent_map[torrent.hash]["double"] = torrent
    logger.debug(f"get_previous_torrents took: {timer() - start}")
    return torrent_map


def get_torrents_with_no_history(torrent_ids: list[int]):
    start = timer()
    logger = logging.getLogger("torbox")
    result = Torrent.objects.filter(
        torrenthistory__isnull=True, id__in=torrent_ids
    ).values_list("id", flat=True)
    logger.debug(f"get_torrents_with_no_history took: {timer() - start}")
    return result


def update_double(torrent: Torrent, double: Torrent = None):
    logger = logging.getLogger("torbox")
    # double = Torrent.objects.exclude(Q(pk=torrent.pk) | Q(deleted=True)).filter(
    #     hash=torrent.hash
    # )
    if torrent.doubled and not double:  # this will never update the previous double
        torrent.doubled = False
        torrent.save()
        logger.debug(f"Torrent no longer a double: {torrent}")
        return

    if double and (not double.doubled or not torrent.doubled):
        double.doubled = True
        double.save()
        torrent.doubled = True
        torrent.save()
        logger.debug(f"Updating double status for: {double} {torrent}")


def update_type(torrent: Torrent):
    logger = logging.getLogger("torbox")
    no_type = TorrentType.objects.get_no_type()
    if torrent.torrent_type != no_type:
        logger.debug(f"Torrent {torrent} already had a type, skipping type update")
        return

    movie_series = TorrentType.objects.get_movie_series()
    result = re.search(
        "[sS]\\d{1,2}([eE]\\d{1,2})*", torrent.name
    )  # fixme: use common based on action_mgr
    if result:
        logger.info(
            f"Found movie series marker, changing type to movie series for torrent: {torrent}"
        )
        torrent.torrent_type = movie_series
        torrent.save()
        add_log(
            message=f"Torrent {torrent.name} with hash: {torrent.hash} was added with season/episode marker, updating as movie series type",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_torbox_api(),
            torrent=torrent,
        )
        return

    if torrent.name.lower().endswith(".m4b"):
        add_log(
            message=f"Found m4b marker in {torrent.name} , updating as audiobook type",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_torbox_api(),
            torrent=torrent,
        )
        torrent.torrent_type = TorrentType.objects.get_audiobooks()
        torrent.save()
        return
    if torrent.name.lower().endswith(".epub"):
        add_log(
            message=f"Found epub marker in {torrent.name} , updating as e-book type",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_torbox_api(),
            torrent=torrent,
        )
        torrent.torrent_type = TorrentType.objects.get_ebooks()
        torrent.save()
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


def map_transmission_entry_to_torrent(entry, no_type):
    trackers = entry.trackers
    tracker = ""
    if trackers:
        tracker = trackers[0].announce
    return Torrent(
        active=entry.eta != None,
        hash=entry.hash_string,
        name=entry.name,
        size=entry.total_size,
        created_at=entry.added_date,
        download_finished=entry.seeding or entry.seed_pending,
        download_present=entry.seeding or entry.seed_pending,
        tracker=tracker,
        total_uploaded=entry.uploaded_ever,
        total_downloaded=entry.downloaded_ever,
        client=TRANSMISSION_CLIENT,
        magnet=entry.magnet_link,
        internal_id=entry.id,
        torrent_type=no_type,
        private=entry.is_private,
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


def update_torrent(
    new_torrent: Torrent, old_torrent: Torrent = None, double: Torrent = None
):
    from .statusmgr import StatusMgr

    status_mgr = StatusMgr.get_instance()
    logger = logging.getLogger("torbox")
    torrent = old_torrent  # get_previous_torrent(new_torrent)
    INFO = Level.objects.get_info()
    torrent_updated = False

    if torrent:

        if torrent.deleted:
            torrent_updated = True
            torrent.redownload = True
            torrent.deleted = False
            logger.info(f"Redownloading torrent: {torrent}")
            add_log(
                message=f"Marking torrent: {torrent} as redownload",
                level=INFO,
                source=LogSource.objects.get_torbox_api(),
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
            torrent.internal_id = new_torrent.internal_id
            torrent_updated = True

        if torrent.magnet != new_torrent.magnet:
            torrent.magnet = new_torrent.magnet
            torrent_updated = True
        if torrent.private != new_torrent.private:
            torrent.private = new_torrent.private
            torrent_updated = True
        if (
            torrent.cached != new_torrent.cached
            and torrent.local_status
            == status_mgr.client_init  # only update cached if torrent is in init state to avoid overwriting cached status changed by user
        ):
            torrent.cached = new_torrent.cached
            torrent_updated = True
        if torrent.name != new_torrent.name:
            torrent.name = new_torrent.name
            torrent_updated = True
        if torrent.size != new_torrent.size:
            torrent.size = new_torrent.size
            torrent_updated = True
        if (
            new_torrent.torrent_type != torrent.torrent_type
            and torrent.torrent_type.name == "No Type"
        ):
            torrent_updated = True
            logger.info(
                f"New torrent: {new_torrent} has different type than previous torrent {torrent}"
            )
            add_log(
                message=f"New torrent: {torrent_to_log(new_torrent)} has type: {format_log_value(new_torrent.torrent_type.name)}, and old torrent: {torrent_to_log(torrent)} has No Type, updating type to the new one",
                level=INFO,
                source=LogSource.objects.get_torbox_api(),
                torrent=torrent,
            )
            torrent.torrent_type = new_torrent.torrent_type
        if torrent.tracker != new_torrent.tracker:
            logger.debug(
                f"Updating tracker for: {torrent.name} from {torrent.tracker} to {new_torrent.tracker}"
            )
            torrent_updated = True
            torrent.tracker = new_torrent.tracker
        if torrent.active != new_torrent.active:
            torrent.active = new_torrent.active
            torrent_updated = True
        if torrent.total_uploaded != new_torrent.total_uploaded:
            torrent.total_uploaded = new_torrent.total_uploaded
            torrent_updated = True
        if torrent.total_downloaded != new_torrent.total_downloaded:
            torrent.total_downloaded = new_torrent.total_downloaded
            torrent_updated = True
        if torrent.download_present != new_torrent.download_present:
            torrent.download_present = new_torrent.download_present
            torrent_updated = True
        if torrent.download_finished != new_torrent.download_finished:
            torrent.download_finished = new_torrent.download_finished
            torrent_updated = True

        # logger.debug(f"Saving updated torrent: {model_to_dict(torrent)}")
        if torrent.local_status == status_mgr.client_init:
            status_mgr.remote_client_added_torrent(torrent)
        elif torrent_updated:
            torrent.save()
        logger.debug("torrent already existed")
    else:
        status_mgr.remote_client_added_torrent(new_torrent)
        torrent = new_torrent
    update_double(torrent, double)
    update_type(torrent)
    if (
        config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION
        and torrent.client == TRANSMISSION_CLIENT
        and torrent.local_status != status_mgr.finish_done
    ) or (
        config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX
        and torrent.client == TORBOX_CLIENT
        and torrent.local_status != status_mgr.finish_done
    ):
        status_mgr.force_transition_in_done(torrent)

    return torrent


def mark_deleted_torrents(not_deleted, clients):
    logger = logging.getLogger("torbox")
    ids_to_exclude = [obj.pk for obj in not_deleted]
    logger.debug(f"Update delete: {ids_to_exclude}, {clients}")
    Torrent.objects.exclude(Q(pk__in=ids_to_exclude) | Q(client__in=clients)).update(
        deleted=True
    )


def add_to_queue_by_magnet(magnet, torrent_type):
    entry = TorrentQueue.objects.create(magnet=magnet, torrent_type=torrent_type)
    add_log(
        message=f"Added torrent to queue with id: {format_log_value(entry.id)}",
        level=Level.objects.get_info(),
        source=LogSource.objects.get_queue_mgr(),
    )
    return entry


def get_active_torbox_downloads():
    return Torrent.objects.filter(deleted=False, client=TORBOX_CLIENT).count()


def get_active_transmission_downloads():
    active_statuses = TorrentStatus.objects.get_client_active_statuses()
    return Torrent.objects.filter(
        deleted=False,
        client=TRANSMISSION_CLIENT,
        local_status__in=[status.id for status in active_statuses],
    ).count()


def get_active_torrents_with_current_history(
    current: int = None,
    limit: int = None,
    state_id: int = 0,
    torrent_type_id: int = 0,
    client: str = "",
    private: bool = False,
    tracker: str = "",
    name: str = "",
    statuses: list = None,
):
    latest_details_subquery = (
        TorrentHistory.objects.filter(torrent_id=OuterRef("pk"))
        .order_by("-updated_at", "-pk")
        .values("pk")[:1]
    )
    filter = Torrent.objects.filter(deleted=False)
    if state_id != 0:
        filter = filter.filter(local_status__id=state_id)
    if statuses is not None and len(statuses) > 0:
        filter = filter.filter(local_status__in=[status.id for status in statuses])
    if torrent_type_id != 0:
        filter = filter.filter(torrent_type__id=torrent_type_id)
    if client:
        filter = filter.filter(client=client)
    if private is not None:
        filter = filter.filter(private=private)
    if name:
        filter = filter.filter(name__icontains=name)
    if tracker and tracker != "ALL":
        filter = filter.filter(tracker__icontains=tracker)
    filter = (
        filter.annotate(latest_history_id=Subquery(latest_details_subquery))
        .annotate(
            age=ExpressionWrapper(
                timezone.now() - F("created_at"), output_field=fields.DurationField()
            )
        )
        .order_by("client")
    )
    if current is not None and limit is not None:
        filter = filter[current : current + limit]
    return filter


def get_ratio_stats(torrent: Torrent):
    sq = (
        TorrentHistory.objects.filter(torrent=torrent, updated_at__gte=date(2000, 1, 1))
        .annotate(date=TruncDate("updated_at"))
        .values("date")
        .annotate(latest_ts=Max("updated_at"))
        .values("latest_ts")
    )
    return TorrentHistory.objects.filter(
        torrent=torrent, updated_at__in=Subquery(sq)
    ).order_by("updated_at")


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


def get_active_torrents_with_formatted_age(
    current: int = 0,
    limit: int = 50,
    state_id: int = 0,
    torrent_type_id: int = 0,
    client: str = "",
    private: bool = False,
    tracker: str = "",
    name: str = "",
):
    torrents = get_active_torrents_with_current_history(
        current, limit, state_id, torrent_type_id, client, private, tracker, name
    )
    for obj in torrents:
        age_in_seconds = obj.age.total_seconds()
        obj.formatted_age = format_age(age_in_seconds)
    return torrents
