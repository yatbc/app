from django.test import TestCase, override_settings
import unittest
from django.utils import timezone
import logging
from .temp_settings import console_logging_config
from ..tasks import (
    queue_check_local_download_status,
    queue_import_from_queue_folders,
    queue_process_queue,
    queue_schedule_arrs_tasks,
    queue_scheduler,
    queue_torbox_status,
    queue_transmission_status,
)


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class TasksTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)

    def test_queue_tasks(self):
        self.assertIsNotNone(queue_transmission_status())
        self.assertIsNotNone(queue_torbox_status())
        self.assertIsNotNone(queue_scheduler())

        self.assertIsNotNone(queue_schedule_arrs_tasks())
        self.assertIsNotNone(queue_process_queue())
        self.assertIsNotNone(queue_import_from_queue_folders())

        self.assertIsNotNone(queue_check_local_download_status())
