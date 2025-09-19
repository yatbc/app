import urllib.parse

TORBOX_CLIENT = "TorBox"
TRANSMISSION_CLIENT = "Transmission"


def shorten_torrent_name(torrent):
    if len(torrent.name) > 100:
        torrent.name = torrent.name[0:100] + "..."
    torrent.name = torrent.name.replace(".", " ")  # make it word-wrap friendly
    return torrent


def get_name_from_magnet(magnet):
    name = None
    try:
        parsed = urllib.parse.urlparse(magnet)
        params = urllib.parse.parse_qs(parsed.query)
        if "dn" in params:
            name = params["dn"][0]
    except Exception:
        pass
    return name
