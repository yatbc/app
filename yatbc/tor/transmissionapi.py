from transmission_rpc import Client
from .models import (
    Torrent,
    TorrentFile,
    TorrentHistory,
    TorrentType,
    LogSource,
    Level,
    TorrentQueue,
    TorrentTorBoxSearchResult,
)
from .statusmgr import StatusMgr
from .common import TRANSMISSION_CLIENT, TORBOX_CLIENT
from .commondao import (
    update_torrent,
    mark_deleted_torrents,
    add_log,
    add_to_queue_by_magnet,
    torrent_file_to_log,
    get_active_transmission_downloads,
)
import logging
from django.forms.models import model_to_dict
from constance import config
from django.utils import timezone
from pathlib import Path


# todo: tests
class TransmissionApi:
    def __init__(
        self,
        transmission_dir=None,
        sftp_user=None,
        sftp_port=None,
        sftp_host=None,
        sftp_password=None,
        host=None,
        user=None,
        password=None,
        port=None,
    ):
        if transmission_dir is None:
            transmission_dir = config.TRANSMISSION_DIR
        if sftp_host is None:
            sftp_host = config.TRANSMISSION_SFTP_HOST
        if sftp_user is None:
            sftp_user = config.TRANSMISSION_SFTP_USER
        if sftp_port is None:
            sftp_port = config.TRANSMISSION_SFTP_PORT
        if sftp_password is None:
            sftp_password = config.TRANSMISSION_SFTP_PASSWORD

        if not Path(transmission_dir).is_absolute():
            transmission_dir = (
                "/" + transmission_dir
            )  # make absolute, and on windows it will fail later anyway

        protocol = "http"
        if host is None:
            host = str(config.TRANSMISSION_HOST)
        if host.startswith("https://"):
            protocol = "https"
            host = host.replace("https://", "")
        host = host.replace("http://", "")
        if port is None:
            port = config.TRANSMISSION_PORT
        if user is None:
            user = config.TRANSMISSION_USER
        if password is None:
            password = config.TRANSMISSION_PASSWORD

        self.transmission_dir = transmission_dir
        self.sftp_host = sftp_host
        self.sftp_user = sftp_user
        self.sftp_port = sftp_port
        self.sftp_password = sftp_password
        self.protocol = protocol
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client = Client(
            protocol=self.protocol,
            host=self.host,
            port=self.port,
            username=self.user,
            password=self.password,
        )
        self.logger = logging.getLogger("torbox")

    def get_session(self):
        try:
            result = self.client.get_session()
            return result
        except Exception as e:
            logger = logging.getLogger("torbox")
            logger.error(f"Could not get session from transmission: {e}")
            return None

    def remove_torrent(self, torrent: Torrent, delete_data: bool):
        try:
            self.client.remove_torrent(
                ids=[int(torrent.internal_id)], delete_data=delete_data
            )
            return True
        except Exception as e:
            self.logger.error(f"Could not remove torrent: {e}")
            add_log(
                message=f"Could not remove torrent from transmission: {e}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_transmission_api(),
                torrent=torrent,
            )
            return False

    def add_torrent(self, data):
        # data can be magnet or torrent file content
        try:
            result = self.client.add_torrent(torrent=data)
            return result
        except Exception as e:
            self.logger.error(f"Could not add torrent: {e}")
            add_log(
                message=f"Could not add torrent with magnet/data: {e}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_transmission_api(),
            )
            return None

    def request_download_link(self, torrent: Torrent, file: TorrentFile):
        # self.transmission_dir always starts with /
        address = f"sftp://{self.sftp_user}:{self.sftp_password}@{self.sftp_host}:{self.sftp_port}{self.transmission_dir}/{file.name}"
        censored_address = f"sftp://{self.sftp_user}:censored@{self.sftp_host}:{self.sftp_port}{self.transmission_dir}/{file.name}"
        add_log(
            message=f"Generated sftp link: {censored_address} for file: {torrent_file_to_log(file)}",
            torrent=torrent,
            source=LogSource.objects.get_transmission_api(),
            level=Level.objects.get_info(),
        )
        return address

    def get_torrents(self):
        try:
            result = self.client.get_torrents()
            return result
        except Exception as e:
            self.logger.error(f"Could not get torrents: {e}")
            add_log(
                message=f"Could not get torrents from transmission: {e}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_transmission_api(),
            )
            return None

    def get_download_slots(self):
        session = self.get_session()
        if not session:
            return 0
        return session.download_queue_size


def add_torrent_by_data(torrent_type, magnet=None, blob=None, private=False, api=None):
    if not config.USE_TRANSMISSION:
        return None
    if api is None:
        api = TransmissionApi()
    logger = logging.getLogger("torbox")
    status_mgr = StatusMgr.get_instance()
    if magnet:
        result = api.add_torrent(data=magnet)
    else:
        result = api.add_torrent(data=blob)
    if not result:
        return None
    logger.debug(result)
    new_torrent = status_mgr.new_torrent(
        hash=result.hash_string,
        client=TRANSMISSION_CLIENT,
        internal_id=result.id,
        magnet=magnet,
        torrent_type=torrent_type,
        private=private,
    )
    TorrentHistory.objects.create(
        torrent=new_torrent, updated_at=timezone.now().isoformat(), state="New"
    )
    return new_torrent


def get_free_transmission_download_slots(api=None):
    if not api:
        api = TransmissionApi()
    max_slots = api.get_download_slots()
    result = max_slots - get_active_transmission_downloads()
    if result > 0:
        return result
    return 0


def transmission_have_free_download_slot(api=None):
    if not api:
        api = TransmissionApi()
    return get_free_transmission_download_slots(api) > 0


def add_torrent_by_magnet(magnet, torrent_type_id, api=None, skip_queue_add=False):
    logger = logging.getLogger("torbox")

    torrent_type = TorrentType.objects.get(pk=torrent_type_id)
    logger.debug(
        f"Adding torrent from magnet: {magnet}, with type: {torrent_type.name}"
    )
    if not api:
        api = TransmissionApi()

    if not transmission_have_free_download_slot(api):
        if not skip_queue_add:
            return None, add_to_queue_by_magnet(
                magnet=magnet, torrent_type=torrent_type
            )
        return None, None
    return (
        add_torrent_by_data(magnet=magnet, torrent_type=torrent_type, api=api),
        None,
    )


# todo: refactor to common queuemgr
def add_torrent_from_queue(queue: TorrentQueue, api=None):
    if not api:
        api = TransmissionApi()

    torrent = add_torrent_by_data(
        magnet=queue.magnet,
        blob=queue.torrent_file,
        api=api,
        torrent_type=queue.torrent_type,
        private=queue.torrent_private,
    )
    search = TorrentTorBoxSearchResult.objects.filter(queue=queue).first()
    if search:
        search.torrent = torrent
        search.save()
    return torrent


def transmission_delete_torrent(torrent_id):
    if not config.USE_TRANSMISSION:
        return True
    logger = logging.getLogger("torbox")
    torrent = Torrent.objects.get(pk=torrent_id)
    api = TransmissionApi()
    if api.remove_torrent(
        torrent=torrent,
        delete_data=torrent.download_finished
        == False,  # todo: add a setting for user to choose
    ):
        torrent.deleted = True
        torrent.save()
        return True
    return False


def delete_torrent(torrent_id):
    return transmission_delete_torrent(torrent_id)


def validate_transmission_api(
    host, port, user, password, dir, sftp_host, sftp_user, sftp_password, sftp_port
):
    logger = logging.getLogger("torbox")
    WRONG_HOST = 2
    WRONG_DIR = 1
    WRONG_SFTP_HOST = 3
    from paramiko import SSHClient, AutoAddPolicy

    api = TransmissionApi(
        host=host,
        port=port,
        user=user,
        password=password,
        sftp_host=sftp_host,
        sftp_user=sftp_user,
        sftp_password=sftp_password,
        sftp_port=sftp_port,
        transmission_dir=dir,
    )
    session = api.get_session()
    if not session:
        return (
            False,
            "Could not connect to Transmission, check your host settings",
            WRONG_HOST,
        )
    try:
        with SSHClient() as client:
            client.set_missing_host_key_policy(AutoAddPolicy)
            client.connect(
                hostname=sftp_host,
                port=sftp_port,
                username=sftp_user,
                password=sftp_password,
            )
            stdin, stdout, stderr = client.exec_command("ls " + api.transmission_dir)
            error = bytes.decode(stderr.read())
            if error:
                logger.error(
                    f"Could not access dir: {api.transmission_dir}, result: {error}"
                )
                return (
                    False,
                    f"Could not access dir: {api.transmission_dir}, result: {error}",
                    WRONG_DIR,
                )
            return True, "Transmission and sftp validated", None
    except Exception as e:
        logger.error(f"Could not connect to sftp remote host: {e}")
        return (
            False,
            f"Could not connect to sftp remote host: {e}",
            WRONG_SFTP_HOST,
        )


def transmission_status(api=None, request_files_task=None):
    if not config.USE_TRANSMISSION:
        return
    no_type = TorrentType.objects.get_no_type()
    logger = logging.getLogger("torbox")
    status_mgr = StatusMgr.get_instance()

    api = TransmissionApi() if api is None else api

    torrents = api.get_torrents()
    if torrents is None:
        return

    not_deleted = []
    for entry in torrents:
        # logger.debug(f"{entry.fields}")
        trackers = entry.trackers
        tracker = ""
        if trackers:
            tracker = trackers[0].announce
        new_torrent = Torrent(
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
        torrent = update_torrent(new_torrent)
        status_mgr.transition_in_client_progress_if_needed(torrent)

        logger.debug(model_to_dict(torrent))
        not_deleted.append(torrent)
        previous_activity = TorrentHistory.objects.filter(
            torrent=torrent, updated_at=entry.activity_date
        )
        if len(previous_activity) == 0:
            torrent_history = TorrentHistory(
                torrent=torrent,
                download_speed=entry.rate_download,
                upload_speed=entry.rate_upload,
                eta=entry.eta.seconds if entry.eta else None,
                peers=entry.peers_getting_from_us,
                ratio=entry.ratio,
                seeds=entry.peers_sending_to_us,
                progress=entry.progress / 100.0,
                updated_at=entry.activity_date,
                availability=entry.desired_available,
                state=entry.status.name,
            )
            torrent_history.save()
            logger.debug(model_to_dict(torrent_history))

        else:
            logger.debug("Torrent wasn't updated")
        torrent_files = entry.get_files()
        files = TorrentFile.objects.filter(torrent=torrent)
        if len(torrent_files) and not files:
            logger.debug(f"Updating files for: {torrent.name}")

            for file in torrent_files:
                logger.debug(file)
                tor_file = TorrentFile(
                    torrent=torrent,
                    name=file.name,
                    short_name=None,
                    size=file.size,
                    hash=None,
                    mime_type=None,
                    internal_id=file.id,
                )
                tor_file.save()

        status_mgr.transition_in_client_done_if_needed(
            torrent,
            files,
            request_torrent_files=request_files_task,
        )
    mark_deleted_torrents(not_deleted, clients=[TORBOX_CLIENT])
    config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION = False
