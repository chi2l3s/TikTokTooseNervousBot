import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

console = Console()

def setup_logger(level: int = logging.INFO):
    install(show_locals=False, console=console)
    
    logging.basicConfig(
        level=level,
        format="[dim]%(name)s[/] | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                markup=True,
                show_time=True,
                show_path=False,
                enable_link_path=False
            )
        ],
        force=True
    )
    
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.INFO)