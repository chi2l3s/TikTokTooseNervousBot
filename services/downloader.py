import asyncio
import re
import shutil
from pathlib import Path
import yt_dlp
from config import config

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".ts", ".m4v"}

class VideoDownloader:
    @staticmethod
    def _parse_aria2_eta(eta_str: str) -> float | None:
        try:
            total = 0.0
            h = re.search(r"(\d+)h", eta_str)
            m = re.search(r"(\d+)m", eta_str)
            s = re.search(r"(\d+)s", eta_str)
            if h:
                total += int(h.group(1)) * 3600
            if m:
                total += int(m.group(1)) * 60
            if s:
                total += int(s.group(1))
            return total if total > 0 else None
        except Exception:
            return None

    @classmethod
    async def _download_torrent(cls, source: str | Path, output_dir: Path, progress_tracker=None) -> Path:
        cmd = [
            "aria2c",
            "--seed-time=0",
            "--summary-interval=2",
            "--max-connection-per-server=16",
            "--bt-stop-timeout=600",
            "--dir", str(output_dir),
            str(source),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        loop = asyncio.get_running_loop()

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="ignore").strip()

            if progress_tracker and "(" in decoded and "%" in decoded:
                match = re.search(
                    r"\((?P<pct>\d+)%\).*?CN:(?P<cn>\d+).*?SD:(?P<sd>\d+).*?DL:(?P<speed>[^\s]+)(?:.*?ETA:(?P<eta>[^\s\]]+))?",
                    decoded,
                )
                if match:
                    pct = float(match.group("pct"))
                    speed = match.group("speed")
                    cn = match.group("cn")
                    sd = match.group("sd")
                    eta_str = match.group("eta") or ""
                    eta_sec = cls._parse_aria2_eta(eta_str) if eta_str else None

                    extra = f"⚡ {speed} | Пиры: {cn} | Сиды: {sd}"
                    asyncio.run_coroutine_threadsafe(
                        progress_tracker.update(
                            stage_title="⏳ [1/4] Загрузка с Торрента...",
                            percent=pct,
                            eta_seconds=eta_sec,
                            extra_info=extra,
                        ),
                        loop,
                    )

        await proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Ошибка aria2c при загрузке торрента (код {proc.returncode})")

        video_files = [
            p for p in output_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]

        if not video_files:
            raise FileNotFoundError("В загруженном торренте не найдено поддерживаемых видеофайлов.")

        return max(video_files, key=lambda f: f.stat().st_size)

    @classmethod
    async def download(cls, source: str | Path, output_dir: Path, progress_tracker=None) -> Path:
        source_str = str(source).strip()

        if source_str.startswith("magnet:?") or (isinstance(source, Path) and source.suffix.lower() == ".torrent"):
            return await cls._download_torrent(source, output_dir, progress_tracker)

        loop = asyncio.get_running_loop()

        def _hook(d):
            if progress_tracker and d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                speed = d.get("speed") or 0
                eta = d.get("eta")

                percent = (downloaded / total * 100.0) if total > 0 else 0.0
                speed_mb = speed / (1024 * 1024)
                extra = f"⚡ Скорость: {speed_mb:.1f} MB/s" if speed_mb > 0 else ""

                asyncio.run_coroutine_threadsafe(
                    progress_tracker.update(
                        stage_title="⏳ [1/4] Скачивание видео...",
                        percent=percent,
                        eta_seconds=eta,
                        extra_info=extra,
                    ),
                    loop,
                )

        def _download_ytdlp():
            ydl_opts = {
                "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
                "outtmpl": str(output_dir / "input_video.%(ext)s"),
                "merge_output_format": "mp4",
                "quiet": True,
                "no_warnings": True,
                "concurrent_fragment_downloads": 8,
                "buffersize": 1024 * 64,
                "progress_hooks": [_hook],
                "extractor_args": {
                    "youtube": {
                        "player_client": ["ios", "android", "web"]
                    }
                },
            }

            if config.HTTP_PROXY:
                ydl_opts["proxy"] = config.HTTP_PROXY

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_str, download=True)
                filename = ydl.prepare_filename(info)
                base = Path(filename).with_suffix(".mp4")
                return base if base.exists() else Path(filename)

        return await asyncio.to_thread(_download_ytdlp)