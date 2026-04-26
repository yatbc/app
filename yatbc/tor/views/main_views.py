from django.http import HttpResponse
from django.template import loader
from django.shortcuts import redirect
import logging
from constance import config
from tor.models import Torrent, TorrentHistory
from tor.tasks import torbox_search


def index(request):
    if config.SHOW_CONFIG_ON_START:
        return redirect("/config")
    template = loader.get_template("index.html")

    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def configuration(request):
    template = loader.get_template("config.html")
    context = {
        "show_on_start": config.SHOW_CONFIG_ON_START,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))


def error_log(request):
    template = loader.get_template("error_log.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def history(request):
    template = loader.get_template("history.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def torrent_details(request, id):
    torrent = Torrent.objects.get(id=id)
    torrent_history = TorrentHistory.objects.filter(torrent=torrent)
    template = loader.get_template("torrent_details.html")
    context = {
        "torrent_id": torrent.pk,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def add_torrent(request):
    template = loader.get_template("add_torrent.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def queue(request):
    template = loader.get_template("queue.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))


def search_torrent(request, query, season=0, episode=0):
    logger = logging.getLogger("torbox")
    logger.info(f"Searching for: {query} {season} {episode}")
    result = torbox_search.enqueue(query, season, episode)
    template = loader.get_template("torrent_search.html")
    if season != 0:
        query += "/S" + str(season)
    if episode != 0:
        query += "/E" + str(episode)
    context = {
        "query": query,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "task_id": result.id,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def arr(request):
    template = loader.get_template("arr.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))


def advanced_search(request):
    template = loader.get_template("advanced_search.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))
