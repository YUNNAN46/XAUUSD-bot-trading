import logging
import sys

def setup_logger(log_file: str = "bot.log"):
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
    )
    # Redam spam INFO dari polling Telegram (httpx getUpdates tiap ~10 dtk).
    # Error koneksi tetap terlihat karena di-set ke WARNING, bukan ERROR.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
