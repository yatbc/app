from constance import config
import requests
import logging
import json


class StashApi:
    def __init__(self, host=None, port=None, secret=None, stash_root_dir=None):
        self.logger = logging.getLogger("torbox")
        if not host:
            host = config.STASH_HOST
        if not port:
            port = config.STASH_PORT
        if not secret:
            secret = config.STASH_SECRET
        if not stash_root_dir:
            stash_root_dir = config.STASH_ROOT_DIR
        self.host = host
        self.port = port
        self.secret = secret
        self.stash_root_dir = stash_root_dir
        self.stash = f"http://{self.host}:{self.port}/graphql"

    def _log_query(self, query):
        censored = query
        if self.secret:
            censored = query.replace(self.secret, "***")
        self.logger.debug(f"Stash query: {censored}")

    def rescan_stash(self, folder):
        try:
            self.logger.debug(f"Updating stash")
            query = {
                "operationName": "MetadataScan",
                "variables": {
                    "input": {
                        "rescan": True,
                        "scanGenerateClipPreviews": True,
                        "scanGenerateCovers": True,
                        "scanGenerateImagePreviews": True,
                        "scanGeneratePhashes": True,
                        "scanGeneratePreviews": True,
                        "scanGenerateSprites": True,
                        "scanGenerateThumbnails": True,
                        "paths": [f"{self.stash_root_dir}/{folder}"],
                    }
                },
                "query": "mutation MetadataScan($input: ScanMetadataInput!) {\n  metadataScan(input: $input)\n}",
            }

            self._log_query(query)
            result = requests.post(self.stash, json=query)

            if result.ok:
                json_result = json.loads(result.content)
                self.logger.debug(f"Stash result: {json_result}")
                return True
            else:
                self.logger.error(f"Could not start scan on Stash: {result.content}")
                return False
        except Exception as e:
            self.logger.error("Couldn't send to Stash: " + str(e))
            return None


def validate_stash_api(host, port, password, dir, api=None):
    if not api:
        api = StashApi(host=host, port=port, secret=password, stash_root_dir=dir)

    logger = logging.getLogger("torbox")
    logger.debug(
        f"Validating Stash api with host: {host}, port: {port} and password (hidden)"
    )

    status = api.rescan_stash(folder="")  # just checking connection
    logger.debug(f"Stash result: {status}")
    if status:
        return True, "Ok"
    else:
        return False, "Stash is not reachable"
