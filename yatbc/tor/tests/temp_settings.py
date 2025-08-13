console_logging_config = {
            'version': 1,
            'disable_existing_loggers': True,
            'formatters': {
                'verbose': {
                    'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
                    'style': '{',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                },
            },
            "loggers": {
                "django": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": True
                },
                "torbox": {
                    "handlers": ["console"],
                    "level": "DEBUG",
                    "propagate": True
                },
            },
}