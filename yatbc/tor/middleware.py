import logging
import time
class RequestTimeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logger = logging.getLogger("torbox")
        start_time = time.time()
        response = self.get_response(request)
        duration = time.time() - start_time
        logger.info(f"Request to {request.path} took {duration:.4f} seconds.")
        return response