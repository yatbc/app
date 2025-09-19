from .models import (
    TorrentQueue,
    TorrentType,
    TorrentErrorLog,
    TorrentHistory,
    Torrent,
    Level,
)
from constance import config
from pathlib import Path
from django.utils import timezone
from datetime import timedelta, datetime
import logging
from .commondao import (
    add_log,
    format_log_value,
    torrent_to_log,
    get_active_torrents_with_current_history,
)

MANUAL_POLICY = 0


def get_active_queue(limit=None):
    queue = TorrentQueue.objects.all().order_by("-priority", "-added_at")
    if limit:
        return queue[:limit]
    return queue


def get_queue_count():
    return TorrentQueue.objects.all().count()


def add_to_queue_by_magnet(magnet, torrent_type):
    logger = logging.getLogger("torbox")
    entry = TorrentQueue.objects.create(magnet=magnet, torrent_type=torrent_type)
    add_log(
        message=f"Added torrent to queue with id: {format_log_value(entry.id)}",
        level=Level.objects.get_info(),
        source="queuemgr",
    )
    return entry


def add_to_queue_by_torrent_file(path: Path, torrent_type: TorrentType, private):
    logger = logging.getLogger("torbox")
    if path.suffix.lower() != ".torrent":
        logger.error(f"Wrong path given to add to queue by torrent file: {path}")
        return None

    with open(path, "rb") as torrent_file:
        entry = TorrentQueue.objects.create(
            torrent_file=torrent_file.read(),
            torrent_type=torrent_type,
            torrent_file_name=path.name,
            torrent_private=private,
        )
        add_log(
            message=f"Added torrent to queue with id: {format_log_value(entry.id)}, from path: {format_log_value(path.as_posix())}, and marked as private: {format_log_value(private)}",
            level=Level.objects.get_info(),
            source="queuemgr",
        )
        return entry
    return None


def get_queue_folders():
    logger = logging.getLogger("torbox")
    queue_root_dir = Path(config.QUEUE_DIR)
    torrent_types = TorrentType.objects.all()
    for type in torrent_types:
        folder = type.name.replace(" ", "_").lower().strip()
        for sub in ["private", "public"]:
            path = queue_root_dir / folder / sub
            if not path.exists():
                path.mkdir(parents=True)
                add_log(
                    message=f"For type: {format_log_value(type.name)}, queue folder:<br/>{format_log_value(path.as_posix())}<br/> didn't exist. Created.",
                    level=Level.objects.get_info(),
                    source="queuemgr",
                )
            yield path, type


def import_from_queue_folders():

    for folder, type in get_queue_folders():
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() != ".torrent":
                continue
            result = add_to_queue_by_torrent_file(
                entry, type, private=entry.parent.name == "private"
            )
            if result:
                entry.unlink()
                add_log(
                    message=f"Removed torrent file: {format_log_value(entry.as_posix())}, after it was added to queue",
                    level=Level.objects.get_info(),
                    source="queuemgr",
                )


def delete_torrent_with_log(torrent: Torrent):
    from .torboxapi import delete_torrent

    if delete_torrent(torrent_id=torrent.id):
        add_log(
            message=f"Active downloads cleaned torrent: {torrent_to_log(torrent)}",
            level=Level.objects.get_info(),
            source="queuemgr",
            torrent=torrent,
        )


def clean_active_downloads():

    logger = logging.getLogger("torbox")

    BY_RATIO_ONE_HOUR = 1
    if int(config.CLEAN_ACTIVE_DOWNLOADS_POLICY) == MANUAL_POLICY:
        logger.info("Manual cleaning policy, skipping cleaning active downloads")
        return

    active_downloads = get_active_torrents_with_current_history().exclude(  # we can only remove torrents that are done(have finish action done)
        finished_at__isnull=True
    )
    cleaned = 0
    for torrent in active_downloads:
        history = None
        if torrent.latest_history_id:
            history = TorrentHistory.objects.get(id=torrent.latest_history_id)
        if torrent.private:
            logger.debug(f"skipping torrent: {torrent}, it is marked as private")
            continue
        if torrent.cached:
            delete_torrent_with_log(torrent)
            logger.debug(f"Active cleaning removing cached torrent: {torrent.id}")
            cleaned += 1
            continue
        time_delta = timezone.now() - torrent.finished_at
        if time_delta.total_seconds() > 60 * 60:  # hour
            logger.debug(
                f"Active cleaning removing torrent older then one hour: {torrent.id}, age done: {time_delta.total_seconds()}s"
            )
            delete_torrent_with_log(torrent)
            cleaned += 1
    add_log(
        message=f"Active Torrents Cleaning action removed: {cleaned} torrents from remote client",
        level=Level.objects.get_info(),
        source="queuemgr",
    )
    return cleaned


def add_from_queue():
    from .torboxapi import add_torrent_from_queue
    from .torboxapi import get_free_download_slots

    logger = logging.getLogger("torbox")
    queue_count = get_queue_count()
    if queue_count < 1:
        logger.info("Empty queue, skipping")
        return
    count = get_free_download_slots()
    logger.info(f"Processing queue, available slots: {count}")
    if count < 1:
        logger.info("No free slots, trying to clean")
        clean_active_downloads()
    count = get_free_download_slots()
    logger.info(f"Available slots for queue: {count}")
    if count < 1:
        logger.debug(config.SUPPRESS_NO_FREE_SLOTS_IN_QUEUE_MSG)
        if (
            config.SUPPRESS_NO_FREE_SLOTS_IN_QUEUE_MSG
            and datetime.fromisoformat(str(config.SUPPRESS_NO_FREE_SLOTS_IN_QUEUE_MSG))
            < datetime.now()
        ) or not config.SUPPRESS_NO_FREE_SLOTS_IN_QUEUE_MSG:
            add_log(
                message=f"Queue is not empty({queue_count}), but there are no free download slots. Try removing them manually or enable auto-clean. This message will not be repeated today.",
                source="queuemgr",
                level=Level.objects.get_warning(),
            )
            next_notification = datetime.now() + timedelta(days=1)
            config.SUPPRESS_NO_FREE_SLOTS_IN_QUEUE_MSG = next_notification.isoformat()
        return
    for entry in get_active_queue(count):
        new_torrent = add_torrent_from_queue(entry)
        if not new_torrent:
            add_log(
                message=f"While adding torrents from queue, {format_log_value(entry.id)} could not add torrent",
                level=Level.objects.get_error(),
                source="queuemgr",
            )
            return
        entry.delete()
        add_log(
            message=f"Added torrent: {torrent_to_log(new_torrent)} from queue",
            level=Level.objects.get_info(),
            source="queuemgr",
            torrent=new_torrent,
        )
    logger.info(f"Finished processing queue, added: {count} new torrents")
