TORBOX_CLIENT = "TorBox"
TRANSMISSION_CLIENT = "Transmission"


def shorten_torrent_name(torrent):
    if len(torrent.name) > 100:
        torrent.name = torrent.name[0:100] + "..."
    return torrent
