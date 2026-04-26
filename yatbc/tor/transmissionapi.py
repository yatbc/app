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
    TorrentPeer,
)
from timeit import default_timer as timer
from datetime import timedelta, datetime, timezone as tz
from .statusmgr import StatusMgr
from .common import TRANSMISSION_CLIENT, TORBOX_CLIENT
from .commondao import (
    update_torrent,
    mark_deleted_torrents,
    add_log,
    add_to_queue_by_magnet,
    get_previous_torrents,
    get_active_transmission_downloads,
    torrent_to_log,
    map_transmission_entry_to_torrent as map_entry_to_torrent,
    get_torrents_with_no_history,
    get_torrent_ides,
)
import logging
from django.forms.models import model_to_dict
from constance import config
from django.utils import timezone
from pathlib import Path
from urllib.parse import quote


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
            if delete_data:
                add_log(
                    message=f"Removed torrent and data from transmission: {torrent_to_log(torrent)}",
                    level=Level.objects.get_info(),
                    source=LogSource.objects.get_transmission_api(),
                    torrent=torrent,
                )
            return True
        except Exception as e:
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
            add_log(
                message=f"Could not add torrent with magnet/data: {e}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_transmission_api(),
            )
            return None

    def request_download_link_as_zip(self, file_path) -> str:
        from paramiko import SSHClient, AutoAddPolicy

        try:
            top_level_dir = Path(file_path).parts[0]
            if (
                top_level_dir == "."
                or top_level_dir == ""
                or top_level_dir == Path(self.transmission_dir).name
            ):
                return None  # if there is no top level dir, or it is the same as transmission dir, we can not zip it, because it will include all other files in transmission dir
            with SSHClient() as client:
                client.set_missing_host_key_policy(AutoAddPolicy)
                client.connect(
                    hostname=self.sftp_host,
                    port=self.sftp_port,
                    username=self.sftp_user,
                    password=self.sftp_password,
                )
                zip_name = f"{top_level_dir}.zip"
                cmd = f'cd "{self.transmission_dir}" && zip -0 -r "{zip_name}" "{top_level_dir}"'

                stdin, stdout, stderr = client.exec_command(cmd)
                debug_output = stdout.read()
                self.logger.debug(f"zip of: {cmd}: {debug_output}")

                error = bytes.decode(stderr.read())
                if error:
                    self.logger.error(
                        f"Could not zip dir: {self.transmission_dir +'/' +top_level_dir}, result: {error}"
                    )
                    return None
                return f"sftp://{self.sftp_user}:{self.sftp_password}@{self.sftp_host}:{self.sftp_port}{self.transmission_dir}/{quote(zip_name)}"

        except Exception as e:
            self.logger.error(f"Could not connect to sftp remote host: {e}")
            return None

    def request_download_links(
        self, torrent: Torrent, remove_single_files_for_zip=True
    ) -> list[(str, TorrentFile)]:
        files = TorrentFile.objects.filter(torrent=torrent)
        download_links = []
        if files.count() > 10:
            link = self.request_download_link_as_zip(files.first().name)
            if not link:
                return None
            if remove_single_files_for_zip:
                files.delete()  # remove single files and replace them with zip
                add_log(
                    message=f"Torrent has more then 10 files, will request zip file instead {torrent_to_log(torrent)}",
                    level=Level.objects.get_info(),
                    source=LogSource.objects.get_torbox_api(),
                    torrent=torrent,
                )
            file = TorrentFile.objects.create(
                torrent=torrent,
                name=f"{torrent.name}.zip",
                short_name=f"{torrent.name}.zip",
                size=torrent.size,
                internal_id=None,
            )
            return [(link, file)]
        for file in files:
            # self.transmission_dir always starts with /
            address = f"sftp://{self.sftp_user}:{self.sftp_password}@{self.sftp_host}:{self.sftp_port}{self.transmission_dir}/{quote(file.name)}"
            censored_address = f"sftp://{self.sftp_user}:censored@{self.sftp_host}:{self.sftp_port}{self.transmission_dir}/{quote(file.name)}"
            download_links.append((address, file))
        add_log(
            message=f"Generated sftp links: {len(download_links)} for torrent: {torrent_to_log(torrent)}, last one: {censored_address}",
            torrent=torrent,
            source=LogSource.objects.get_transmission_api(),
            level=Level.objects.get_info(),
        )
        return download_links

    def get_torrents(self):
        try:
            start = timer()
            result = self.client.get_torrents()
            self.logger.debug(f"TransmissionApi.get_torrents took: {timer() - start}")
            return result
        except Exception as e:
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


def transmission_delete_torrent(torrent_id, delete_data=None):
    if not config.USE_TRANSMISSION:
        return True
    torrent = Torrent.objects.get(pk=torrent_id)
    if delete_data is None:
        delete_data = torrent.download_finished == False
    logger = logging.getLogger("torbox")

    api = TransmissionApi()
    if api.remove_torrent(
        torrent=torrent,
        delete_data=delete_data,
    ):
        torrent.deleted = True
        torrent.save()
        return True
    return False


def delete_torrent(torrent_id, delete_data=None):
    return transmission_delete_torrent(torrent_id, delete_data)


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
    start = timer()

    status_mgr = StatusMgr.get_instance()

    api = TransmissionApi() if api is None else api

    data = api.get_torrents()
    if data is None:
        return

    history_array = []
    peers_array = {}

    torrents = {}
    for entry in data:
        logger.debug(
            f"Processing torrent in transmission {entry.name} {entry.hash_string}"
        )
        new_torrent = map_entry_to_torrent(entry, no_type)
        torrents[new_torrent.hash] = {"new": new_torrent, "old": None, "double": None}
    torrents = get_previous_torrents(torrent_map=torrents, client=TRANSMISSION_CLIENT)
    torrent_ids = get_torrent_ides(torrents)
    torrents_with_no_history = get_torrents_with_no_history(torrent_ids)

    not_deleted = []
    for entry in data:
        logger.debug(
            f"Processing torrent in transmission {entry.name} {entry.hash_string}"
        )

        new_torrent, old_torrent, double = (
            torrents[entry.hash_string]["new"],
            torrents[entry.hash_string]["old"],
            torrents[entry.hash_string]["double"],
        )

        torrent = update_torrent(
            new_torrent=new_torrent, old_torrent=old_torrent, double=double
        )
        has_history = torrent.id not in torrents_with_no_history
        status_mgr.transition_in_client_progress_if_needed(
            torrent, has_history=has_history
        )

        # logger.debug(model_to_dict(torrent))
        not_deleted.append(torrent)
        previous_activity = False
        age_change = (
            datetime.now(tz=tz.utc) - entry.activity_date
        )  # transmission entry has utc timezone
        if age_change < timedelta(
            minutes=20
        ):  # check only if change is younger then 20 minutes, otherwise it is probably already in the system, and there is no point in spamming queries
            previous_activity = TorrentHistory.objects.filter(
                torrent=torrent, updated_at=entry.activity_date
            ).exists()

        if not previous_activity:
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
            history_array.append(torrent_history)
            if config.COLLECT_PEER_INFO:
                for peer in entry.peers:
                    torrent_peer = TorrentPeer(
                        address=peer.address,
                        port=peer.port,
                        client=peer.client_name,
                        progress=peer.progress,
                        # downloaded=peer.bytes_to_client, # api does not provide this info
                        # uploaded=peer.bytes_to_peer,
                        client_is_choked=peer.client_is_choked,
                        client_is_interested=peer.client_is_interested,
                        peer_is_choked=peer.peer_is_choked,
                        peer_is_interested=peer.peer_is_interested,
                        flags=peer.flag_str,
                        is_incoming=peer.is_incoming,
                    )
                    if torrent.id in peers_array:
                        peers_array[torrent.id].append(torrent_peer)
                    else:
                        peers_array[torrent.id] = [torrent_peer]

        else:
            logger.debug("Torrent wasn't updated")
        torrent_files = entry.get_files()
        files = TorrentFile.objects.filter(torrent=torrent)
        if len(torrent_files) and not files:
            logger.debug(
                f"Updating files for: {torrent.name} with files: {len(torrent_files)}"
            )
            new_files = []
            for file in torrent_files:
                tor_file = TorrentFile(
                    torrent=torrent,
                    name=file.name,
                    short_name=Path(file.name).name,
                    size=file.size,
                    hash=None,
                    mime_type=None,
                    internal_id=file.id,
                )
                new_files.append(tor_file)
            TorrentFile.objects.bulk_create(new_files)

        status_mgr.transition_in_client_done_if_needed(
            torrent,
            files,
            request_torrent_files=request_files_task,
        )

    history_array = TorrentHistory.objects.bulk_create(history_array)

    if config.COLLECT_PEER_INFO:
        related_peers = []
        for history in history_array:
            if history.torrent.id in peers_array:
                for peer in peers_array[history.torrent.id]:
                    peer.torrent_history = history
                    related_peers.append(peer)
        TorrentPeer.objects.bulk_create(related_peers)

    mark_deleted_torrents(not_deleted, clients=[TORBOX_CLIENT])
    config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION = False
    logger.debug(f"transmission_status took: {timer() - start}")
