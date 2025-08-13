from transmission_rpc import Client
from .models import Torrent, TorrentFile, TorrentHistory, TorrentType, ErrorLog

from .commondao import update_torrent, mark_deleted_torrents, TRANSMISSION_CLIENT, TORBOX_CLIENT
import logging
from django.forms.models import model_to_dict
from constance import config
def transmission_add_torrent(magnet, torrent_type):
    if not config.USE_TRANSMISSION:
        return
    logger = logging.getLogger("torbox")
    logger.debug(f"Adding torrent with host: {config.TRANSMISSION_HOST}, port: {config.TRANSMISSION_PORT}, user: {config.TRANSMISSION_USER}")
    try:
        client = Client(host=config.TRANSMISSION_HOST, port=config.TRANSMISSION_PORT, username=config.TRANSMISSION_USER, password=config.TRANSMISSION_PASSWORD)
        result = client.add_torrent(torrent=magnet)
        logger.debug(result)
        #todo: add empty torrent, to save torrent_type
    except Exception as e:
        logger.error(f"Could not add torrent: {e}")
        ErrorLog.objects.create(message=f"Could not add torrent with magnet {magnet}: {e}", level="ERROR", source="transmissionapi")
        return None

def transmission_delete_torrent(torrent_id):
    if not config.USE_TRANSMISSION:
        return
    logger = logging.getLogger("torbox")
    torrent = Torrent.objects.get(pk=torrent_id)
    try:
        client = Client(host=config.TRANSMISSION_HOST, port=config.TRANSMISSION_PORT, username=config.TRANSMISSION_USER, password=config.TRANSMISSION_PASSWORD)
        if torrent.download_finished:
            logger.info(f"Requesting removing transmission torrent (completed one, without removing data): {torrent}")
            client.remove_torrent(ids=[int(torrent.internal_id)], delete_data=False)
        else:
            logger.info(f"Requesting removing transmission torrent with removing of data: {torrent}")
            client.remove_torrent(ids=[int(torrent.internal_id)], delete_data=True)
        torrent.deleted = True
        torrent.save()
    except Exception as e:
        torrent.deleted = False
        torrent.save()
        ErrorLog.objects.create(message=f"Could not delete torrent {torrent.name} with id {torrent_id}: {e}", level="ERROR", source="transmissionapi")
        logger.error(f"Could not delete torrent: {e}")


def validate_transmission_api(host, port, user, password):
    logger = logging.getLogger("torbox")
    WRONG_HOST = 2
    
    try:
        client = Client(host=host, port=port, username=user, password=password)
        result = client.get_session()
        logger.debug(f"Result of get_session: {result}")
        return True, "Transmission is working", None
    except Exception as e:    
        logger.error(e)    
        return False, "Could not connect to Transmission, check your host settings", WRONG_HOST   
    


def transmission_status():
    if not config.USE_TRANSMISSION:
        return
    no_type = TorrentType.objects.get(name="No Type")
    logger = logging.getLogger("torbox")
    try:
        client = Client(host=config.TRANSMISSION_HOST, port=config.TRANSMISSION_PORT, username=config.TRANSMISSION_USER, password=config.TRANSMISSION_PASSWORD)

        torrents = client.get_torrents()

        not_deleted = []
        for entry in torrents:
            #logger.debug(f"{entry.fields}")
            trackers = entry.trackers
            tracker = ""
            if trackers:
                tracker = trackers[0].announce
            new_torrent = Torrent(active=entry.eta != None,
                                    hash=entry.hash_string,
                                    name=entry.name,
                                    size=entry.total_size,
                                    created_at=entry.added_date,
                                    download_finished=entry.done_date is not None,
                                    download_present=entry.done_date is not None,
                                    tracker=tracker,
                                    total_uploaded=entry.uploaded_ever,
                                    total_downloaded=entry.downloaded_ever, client=TRANSMISSION_CLIENT,
                                    magnet=entry.magnet_link, internal_id=entry.id, torrent_type=no_type)
            torrent = update_torrent(new_torrent)

            logger.debug(model_to_dict(torrent))
            not_deleted.append(torrent)
            previous_activity = TorrentHistory.objects.filter(torrent=torrent, updated_at=entry.activity_date)
            if len(previous_activity) == 0:
                torrent_history = TorrentHistory(torrent=torrent,
                                                    download_speed=entry.rate_download,
                                                    upload_speed=entry.rate_upload,
                                                    eta=entry.eta.seconds if entry.eta else None,
                                                    peers=entry.peers_getting_from_us,
                                                    ratio=entry.ratio,
                                                    seeds=entry.peers_sending_to_us,
                                                    progress=entry.progress/100.0,
                                                    updated_at=entry.activity_date,
                                                    availability=entry.desired_available,
                                                    state=entry.status.name)
                torrent_history.save()
                logger.debug(model_to_dict(torrent_history))

            else:
                logger.debug("Torrent wasn't updated")
            files = entry.get_files()
            if len(files) and not TorrentFile.objects.filter(torrent=torrent):
                logger.debug(f"Updating files for: {torrent.name}")

                for file in files:
                    logger.debug(file)
                    tor_file = TorrentFile(torrent=torrent, name=file.name,
                                            short_name=None,
                                            size=file.size,
                                            hash=None,
                                            mime_type=None)
                    tor_file.save()
        mark_deleted_torrents(not_deleted, clients=[TORBOX_CLIENT])
    except Exception as e:
        logger.error(f"Could not get torrents: {e}")
        ErrorLog.objects.create(message=f"Could not get torrents: {e}", level="ERROR", source="transmissionapi")
        return None