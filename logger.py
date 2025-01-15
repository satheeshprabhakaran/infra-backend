"""
Logger Class
"""

import logging
from functools import lru_cache

from app.config import get_settings

settings = get_settings()

"""
Following same signature as python logging (logging.getLogger)
"""


@lru_cache(maxsize=1)
def get_logger():
    """
    Get the logger
    """
    logging.basicConfig(
        format="[%(asctime)s.%(msecs)03dZ] [%(name)s] [%(levelname)s] (%(filename)s:%(lineno)s) %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    log = logging.getLogger("InfrastructureService")
    # add console handler
    if settings.enable_local_log_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(settings.log_level.upper())
        console_handler.setFormatter(logging.Formatter(settings.log_format))
        log.addHandler(console_handler)
    log.setLevel(settings.log_level.upper())
    return log


logger = get_logger()
