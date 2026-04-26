from django.http import JsonResponse
from django.forms.models import model_to_dict
from django.db.models import Q
import logging
from tor.common import TORBOX_CLIENT
from tor.models import (
    TorrentType,
    JackettSearch,
    JackettSearchResultAudiobook,
    JackettSearchResultBase,
)
from tor.tasks import get_advanced_search_audiobooks, add_magnet


def get_advanced_search_results_api(
    request,
    current: int,
    limit: int,
    type_id: int,
    query: str = "",
    title: str = "",
    extra_query: str = "",
):
    logger = logging.getLogger("torbox")
    if type_id == 0:
        return JsonResponse({"results": []})
    type = TorrentType.objects.get(pk=type_id)
    logger.info(f"Getting search results for query: {query}, type: {type.name}")
    if query == "None":
        query = ""
    # jackett_query = JackettSearch.objects.filter(torrent_type=type, query=query).last()
    # if not jackett_query:
    #     logger.info(f"No jackett search found for query: {query}, type: {type.name}")
    #     return JsonResponse({"results": []}, safe=False)

    results = []
    if type == TorrentType.objects.get_audiobooks():
        logger.info(
            f"Searching audiobooks for query: {query}, extra: {extra_query}, title: {title}"
        )
        db_result = JackettSearchResultAudiobook.objects.filter(
            query__torrent_type=type
        ).prefetch_related("author", "narrator")
        if query != "":
            db_result = db_result.filter(
                Q(title__icontains=title) | Q(full_title__icontains=title)
            )
        if extra_query and extra_query != "None":
            db_result = db_result.filter(
                Q(author__icontains=extra_query) | Q(narrator__icontains=extra_query)
            )
        if title and title != "None":
            db_result = db_result.filter(
                Q(title__icontains=title) | Q(full_title__icontains=title)
            )

        for item in db_result.order_by("-published_date")[current : current + limit]:
            d = model_to_dict(item)
            d["published_date"] = (
                item.published_date.date().isoformat() if item.published_date else None
            )
            d["extra"] = (
                f"Author: {item.author.name if item.author else None}, Narrator: {item.narrator.name if item.narrator else None}"
            )
            results.append(d)

    return JsonResponse({"results": results}, safe=False)


def start_advanced_search_api(request, type_id: int, query: str = ""):
    logger = logging.getLogger("torbox")
    type = TorrentType.objects.get(pk=type_id)
    logger.info(f"Getting search results for query: {query}, type: {type.name}")
    if type == TorrentType.objects.get_audiobooks():
        result = get_advanced_search_audiobooks.enqueue(query)
        return JsonResponse({"request_id": result.id}, safe=False)

    logger.warning(f"Unknown search type: {type}")
    return JsonResponse({"error": f"Unknown search type: {type}"}, status=400)


def download_file_from_advanced_search(request, id: int):
    logger = logging.getLogger("torbox")

    result = JackettSearchResultBase.objects.filter(pk=id).select_related(
        "query__torrent_type"
    )
    result = result.first()
    if not result:
        return JsonResponse({"error": f"Unknown search result id: {id}"})

    if result.magnet_link:

        result = add_magnet.enqueue(
            magnet=result.magnet_link,
            torrent_type_id=result.query.torrent_type.pk,
            client=TORBOX_CLIENT,
        )
        return JsonResponse({"request_id": result.id}, safe=False)

    logger.error("Downloading by torrent is not implemented")

    return JsonResponse(
        {"error": f"Downloading by torrent is not implemented at the moment"}
    )
