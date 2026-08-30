import asyncio
import logging
from pathlib import Path
import yt_dlp
from config import config

logger = logging.getLogger("Downloader")

class VideoDownloader:
    @staticmethod
    async def download(url: str, output_dir: Path) -> Path:
        def _download():
            logger.info(f"Начало скачивания через yt-dlp: {url}")
            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "outtmpl": str(output_dir / "input_video.%(ext)s"),
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
            }
            
            if config.HTTP_PROXY:
                ydl_opts['proxy'] = config.HTTP_PROXY
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                base = Path(filename).with_suffix('.mp4')
                return base if base.exists() else Path(filename)
            
        return await asyncio.to_thread(_download)