import logging

# Configure basic logging


def get_logger(log_level: int = logging.INFO):
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger(__name__)
