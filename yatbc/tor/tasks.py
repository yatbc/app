from django_tasks import task
from .torboxapi import (
    update_torrent_list,
    request_dl,
    search_torrent,
    add_torrent,
    change_torrent,
    add_torrent_by_magnet,
)
from .transmissionapi import (
    transmission_status,
    transmission_add_torrent,
    transmission_delete_torrent,
)
from .arrmanager import get_next_arrs, process_arr, arrs_to_str
from .ariaapi import check_local_download_status, exec_action_on_finish
import logging
from datetime import timedelta
from django.utils import timezone
from .models import Torrent
from django_tasks.backends.database.models import DBTaskResult, ResultStatus
from .common import TORBOX_CLIENT, TRANSMISSION_CLIENT
from django.db.models import Case, When, Value, IntegerField
from constance import config


@task(priority=-10)
def transmission_status_task():
    logger = logging.getLogger("torbox")
    logger.info("Starting transmission api")
    transmission_status()
    logger.info("Transmission api done")


@task()
def check_local_download_status_task():
    logger = logging.getLogger("torbox")
    logger.info("Starting local download status check")
    check_local_download_status()
    logger.info("Local download status check done")


@task()
def add_magnet(client, magnet, torrent_type):
    logger = logging.getLogger("torbox")
    if client == TRANSMISSION_CLIENT:
        transmission_add_torrent(magnet, torrent_type)
    elif client == TORBOX_CLIENT:
        add_torrent_by_magnet(magnet, torrent_type)
    else:
        logger.error(f"Unknown client: {client}")


@task(priority=-10)
def torbox_status_task():
    logger = logging.getLogger("torbox")
    logger.info("Starting tor api")
    update_torrent_list()
    logger.info("Tor api done")


@task()
def import_form_queue_folders_task():
    from .queuemgr import import_from_queue_folders

    logger = logging.getLogger("torbox")
    logger.info("Starting import from queue folders")
    import_from_queue_folders()
    logger.info("Import from queue folders done")


@task()
def process_queue_task():
    from .queuemgr import add_from_queue

    add_from_queue()


@task()
def torbox_request_torrent_files(torrent_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Requesting torrent files for torrent id: {torrent_id}")
    request_dl(torrent_id)
    logger.info("Request done")


@task()
def torbox_search(query, season, episode):
    logger = logging.getLogger("torbox")
    logger.info(f"Requesting search: {query} {season} {episode}")
    search_torrent(query, season, episode)
    logger.info("Request done")


@task()
def double_torrent_task(torrent_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Requesting doubling torrent")
    torrent = Torrent.objects.get(pk=torrent_id)
    torrent.doubled = True
    torrent.save()
    if not torrent:
        return False
    if torrent.client == TRANSMISSION_CLIENT:
        add_torrent_by_magnet(torrent.magnet)
    elif torrent.client == TORBOX_CLIENT:
        transmission_add_torrent(torrent.magnet)
    else:
        logger.error(f"Unknown client: {torrent.client}")
    logger.info("Request done")


@task()
def change_torrent_task(action, torrent_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Requesting change: {action}, {torrent_id}")
    torrent = Torrent.objects.get(pk=torrent_id)
    if action == "delete" and torrent.client == TRANSMISSION_CLIENT:
        transmission_delete_torrent(torrent_id=torrent_id)
    elif torrent.client == TORBOX_CLIENT:
        change_torrent(torrent_id=torrent_id, action=action)
    else:
        logger.warning("Cant exec torrent change")
    queue_process_queue()
    logger.info("Request done")


@task()
def add_torbox_torrent(query_search_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Adding torrent id: {query_search_id}")
    add_torrent(query_search_id)
    logger.info("Request done")


@task()
def exec_action_on_file_task(torrent_id):
    logger = logging.getLogger("torbox")
    torrent = Torrent.objects.get(pk=torrent_id)
    logger.info(f"Executing action on file task for torrent: {torrent}")
    exec_action_on_finish(torrent=torrent)
    logger.info("Action on file task done")


@task(priority=-1)  # process in free time, to not spam
def process_arr_task(arr_id: int):
    logger = logging.getLogger("torbox")
    logger.info(f"Process arr task will work on: arr_id: {arr_id}")
    _, status = process_arr(arr_id)
    if status:
        logger.info(f"Arr manager found next episode, queueing again")
        start_time = timezone.now() + timedelta(seconds=30)
        next_schedule = process_arr_task.using(
            run_after=start_time
        )  # don't spam it, wait for 30s
        next_schedule.enqueue(arr_id)


@task()
def schedule_arrs_tasks():
    logger = logging.getLogger("torbox")
    arrs = get_next_arrs()
    if not arrs:
        return
    logger.debug(f"Will schedule {len(arrs)} arrs")
    for arr in arrs:
        process_arr_task.enqueue(arr.id)


def check_status():
    result = queue_check_local_download_status()
    result = queue_torbox_status()
    if config.USE_TRANSMISSION:
        result = queue_transmission_status()
    return result


def get_tasks(exclude_tasks_type=[], status=[]):
    query = (
        DBTaskResult.objects.filter(
            status__in=status, enqueued_at__gte=timezone.now() - timedelta(days=1)
        )
        .exclude(task_path__in=exclude_tasks_type)
        .all()
    )
    return query


def get_task(task_type, status):
    query = DBTaskResult.objects.filter(task_path=task_type, status__in=status)[:1]
    if len(query) > 0:
        return query[0]
    return None


def get_task_queued_or_running(task_type):
    return get_task(
        task_type=task_type, status=[ResultStatus.READY, ResultStatus.RUNNING]
    )


not_status_checking = ["tor.tasks.schedule_tasks", "tor.tasks.schedule_arrs_tasks"]


def queue_transmission_status():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.transmission_status_task"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Queuing: {task_type}")
        return transmission_status_task.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_schedule_arrs_tasks():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.schedule_arrs_tasks"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Queuing: {task_type}")
        return schedule_arrs_tasks.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_torbox_status():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.torbox_status_task"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Queuing: {task_type}")
        return torbox_status_task.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_check_local_download_status():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.check_local_download_status_task"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Queuening: {task_type}")
        return check_local_download_status_task.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_scheduler():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.schedule_tasks"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Scheduling task: {task_type}")
        return schedule_tasks.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_import_from_queue_folders():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.import_form_queue_folders_task"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Scheduling task: {task_type}")
        return import_form_queue_folders_task.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


def queue_process_queue():
    logger = logging.getLogger("torbox")
    task_type = "tor.tasks.process_queue_task"
    result = get_task_queued_or_running(task_type)
    if not result:
        logger.info(f"Scheduling task: {task_type}")
        return process_queue_task.enqueue()
    else:
        logger.debug(f"Task {task_type} is already queued or running: {result}")
        return result


@task()
def schedule_tasks():
    start_time = timezone.now()
    start_time += timedelta(minutes=10)
    logger = logging.getLogger("torbox")
    logger.info(f"Scheduling tasks every 10 min")
    check_status()
    queue_import_from_queue_folders()
    queue_process_queue()
    queue_schedule_arrs_tasks()
    next_schedule = schedule_tasks.using(run_after=start_time)
    next_schedule.enqueue()
    logger.info("Scheduling done")
