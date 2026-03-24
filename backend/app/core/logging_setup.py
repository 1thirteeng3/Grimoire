import logging
from logging.handlers import TimedRotatingFileHandler

from app.config import settings

_HANDLER_NAME = "grimoire-rotating-file"


def configure_file_logging() -> None:
    if not settings.enable_file_logging:
        return

    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "name", "") == _HANDLER_NAME:
            return

    settings.log_file_path.parent.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=str(settings.log_file_path),
        when="midnight",
        interval=1,
        backupCount=max(1, int(settings.log_retention_days)),
        encoding="utf-8",
        utc=True,
    )
    handler.set_name(_HANDLER_NAME)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
