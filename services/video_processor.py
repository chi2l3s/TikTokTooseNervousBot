import asyncio
import logging
import os
import random
import subprocess
import urllib.request
from pathlib import Path
import cv2
from config import config
from services.face_tracker import SmartCropper
from services.subtitle_generator import SubtitleGenerator

logger = logging.getLogger("VideoProcessor")

class VideoProcessor:
    def __init__(self):
        self.cropper = SmartCropper()
        self._ensure_default_font()

    def _ensure_default_font(self) -> Path:
        font_files = list(config.FONTS_DIR.glob("*.ttf")) + list(config.FONTS_DIR.glob("*.otf"))
        if font_files:
            return font_files[0]

        default_font = config.FONTS_DIR / "Montserrat-ExtraBold.ttf"
        if not default_font.exists():
            url = "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
            try:
                urllib.request.urlretrieve(url, default_font)
            except Exception:
                pass
        return default_font

    @staticmethod
    def _to_safe_rel_path(path: Path) -> str:
        try:
            return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except Exception:
            return path.as_posix()

    def _compress_to_telegram_limit(self, input_file: Path, duration: float) -> Path:
        size_mb = input_file.stat().st_size / (1024 * 1024)
        if size_mb <= 48.0:
            return input_file

        target_size_kbits = 44 * 8192
        total_bitrate_kbps = int(target_size_kbits / max(1.0, duration))
        audio_bitrate_kbps = 128
        video_bitrate_kbps = max(350, total_bitrate_kbps - audio_bitrate_kbps)

        compressed_output = input_file.parent / f"compressed_{input_file.name}"

        cmd_compress = [
            "ffmpeg", "-y",
            "-i", str(input_file),
            "-c:v", "libx264",
            "-preset", "fast",
            "-b:v", f"{video_bitrate_kbps}k",
            "-maxrate", f"{int(video_bitrate_kbps * 1.4)}k",
            "-bufsize", f"{int(video_bitrate_kbps * 2.0)}k",
            "-vf", "scale=-2:1280",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate_kbps}k",
            str(compressed_output)
        ]

        subprocess.run(cmd_compress, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        input_file.unlink(missing_ok=True)
        compressed_output.rename(input_file)
        return input_file

    def _prepare_ad_clip(self, ad_source_path: Path, output_ad_clip: Path, aspect_ratio: str = "9:16"):
        is_video = ad_source_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm", ".avi"]
        
        if aspect_ratio == "9:16":
            vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30"
        elif aspect_ratio == "4:3":
            vf = "scale=1440:1080:force_original_aspect_ratio=decrease,pad=1440:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30"
        else:
            vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black,fps=30"

        if is_video:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(ad_source_path),
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-ac", "2",
                "-ar", "48000",
                "-b:a", "192k",
                str(output_ad_clip)
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(ad_source_path),
                "-f", "lavfi",
                "-i", "anullsrc=r=48000:cl=stereo",
                "-t", "3.0",
                "-vf", vf,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-shortest",
                str(output_ad_clip)
            ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @staticmethod
    def _get_ad_insert_timestamps(duration: float, mode: str) -> list[float]:
        if mode == "start":
            return [min(5.0, duration * 0.15)]
        elif mode == "middle":
            return [duration * 0.5]
        elif mode == "end":
            return [max(1.0, duration - 10.0)]
        elif mode == "every_30":
            points = []
            curr = 30.0
            while curr < duration - 10.0:
                points.append(curr)
                curr += 30.0
            return points
        return []

    @staticmethod
    def _splice_ad_into_video(main_video: Path, ad_clip: Path, insert_points: list[float], output_video: Path):
        segments = []
        prev_t = 0.0

        for idx, t in enumerate(insert_points):
            seg_path = main_video.parent / f"main_seg_{idx}.mp4"
            cmd_cut = [
                "ffmpeg", "-y",
                "-ss", str(prev_t),
                "-to", str(t),
                "-i", str(main_video),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-ar", "48000",
                str(seg_path)
            ]
            subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            segments.append(seg_path)
            segments.append(ad_clip)
            prev_t = t

        last_seg_path = main_video.parent / f"main_seg_last.mp4"
        cmd_last = [
            "ffmpeg", "-y",
            "-ss", str(prev_t),
            "-i", str(main_video),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-c:a", "aac",
            "-ar", "48000",
            str(last_seg_path)
        ]
        subprocess.run(cmd_last, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        segments.append(last_seg_path)

        filter_inputs = "".join([f"[{i}:v][{i}:a]" for i in range(len(segments))])
        filter_complex = f"{filter_inputs}concat=n={len(segments)}:v=1:a=1[v][a]"

        cmd_concat = ["ffmpeg", "-y"]
        for s in segments:
            cmd_concat.extend(["-i", str(s)])

        cmd_concat.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_video)
        ])
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        for s in segments:
            if s != ad_clip:
                s.unlink(missing_ok=True)

    async def render_highlight(
        self,
        source_video: Path,
        clip_data: dict,
        all_words: list[dict],
        output_dir: Path,
        index: int,
        settings: dict,
        progress_tracker=None,
        total_clips: int = 1,
    ) -> Path:
        loop = asyncio.get_running_loop()

        def _crop_progress_callback(cur_frame: int, total_frames: int):
            if progress_tracker and total_frames > 0:
                pct = (cur_frame / total_frames) * 100.0
                asyncio.run_coroutine_threadsafe(
                    progress_tracker.update(
                        stage_title=f"✂️ [4/4] Монтаж клипа {index + 1} из {total_clips}...",
                        percent=pct,
                        extra_info=f"Кадр {cur_frame}/{total_frames}",
                    ),
                    loop,
                )

        def _process():
            start = clip_data["start"]
            end = clip_data["end"]
            duration = end - start
            aspect = settings.get("aspect_ratio", "9:16")
            face_track = settings.get("face_tracking", True)

            raw_cut_path = output_dir / f"raw_cut_{index}.mp4"
            cropped_video_path = output_dir / f"temp_cropped_{index}.mp4"
            subtitles_path = output_dir / f"subs_{index}.ass"
            master_rendered_path = output_dir / f"master_rendered_{index}.mp4"
            final_output = output_dir / f"highlight_{index + 1}.mp4"

            cmd_cut = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-to", str(end),
                "-i", str(source_video),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-ac", "2",
                "-c:a", "aac",
                "-b:a", "192k",
                str(raw_cut_path)
            ]
            subprocess.run(cmd_cut, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            self.cropper.crop_video(
                input_video=str(raw_cut_path),
                output_video=str(cropped_video_path),
                aspect_ratio=aspect,
                enable_tracking=face_track,
                progress_callback=_crop_progress_callback,
            )

            has_subs = SubtitleGenerator.generate(
                words=all_words,
                clip_start=start,
                clip_end=end,
                output_path=subtitles_path,
                aspect_ratio=aspect,
            )

            video_filters = []
            if has_subs:
                safe_sub = self._to_safe_rel_path(subtitles_path)
                video_filters.append(f"ass='{safe_sub}'")

            watermark_text = settings.get("watermark_text")
            if watermark_text:
                font_file = self._ensure_default_font()
                font_rel = self._to_safe_rel_path(font_file)
                escaped_wm = watermark_text.replace(":", "\\:").replace("'", "")
                font_arg = f":fontfile='{font_rel}'" if font_file.exists() else ""
                
                pos_y = "140" if aspect == "9:16" else "60"
                font_size = "52" if aspect == "9:16" else "38"
                video_filters.append(
                    f"drawtext=text='{escaped_wm}'{font_arg}:fontcolor=white@0.85:fontsize={font_size}:x=(w-tw)/2:y={pos_y}:shadowcolor=black@0.9:shadowx=4:shadowy=4:borderw=3:bordercolor=black@0.7"
                )

            music_files = [
                p for p in config.MUSIC_DIR.iterdir()
                if p.suffix.lower() in [".mp3", ".wav", ".aac", ".m4a"]
            ]

            filter_complex_parts = []
            if video_filters:
                filter_complex_parts.append(f"[0:v]{','.join(video_filters)}[v]")
                v_map = "[v]"
            else:
                v_map = "0:v"

            filter_complex_parts.append("[1:a]dynaudnorm=f=150:g=15:m=10.0,volume=1.4[voice]")

            if settings.get("add_music", True) and music_files:
                bg_music = random.choice(music_files)
                filter_complex_parts.append("[2:a]volume=0.035[bgm]")
                filter_complex_parts.append("[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]")

                cmd_final = [
                    "ffmpeg", "-y",
                    "-i", str(cropped_video_path),
                    "-i", str(raw_cut_path),
                    "-stream_loop", "-1",
                    "-i", str(bg_music),
                    "-filter_complex", ";".join(filter_complex_parts),
                    "-map", v_map,
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-c:a", "aac",
                    "-ar", "48000",
                    "-b:a", "192k",
                    "-shortest",
                    str(master_rendered_path)
                ]
            else:
                filter_complex_parts.append("[voice]anull[a]")
                cmd_final = [
                    "ffmpeg", "-y",
                    "-i", str(cropped_video_path),
                    "-i", str(raw_cut_path),
                    "-filter_complex", ";".join(filter_complex_parts),
                    "-map", v_map,
                    "-map", "[a]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "22",
                    "-c:a", "aac",
                    "-ar", "48000",
                    "-b:a", "192k",
                    "-shortest",
                    str(master_rendered_path)
                ]

            subprocess.run(cmd_final, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            banner_mode = settings.get("banner_mode", "none")
            banner_source = settings.get("banner_source_path")

            if banner_mode != "none" and banner_source and Path(banner_source).exists():
                insert_points = self._get_ad_insert_timestamps(duration, banner_mode)
                if insert_points:
                    ad_clip_path = output_dir / f"prepared_ad_{index}.mp4"
                    self._prepare_ad_clip(Path(banner_source), ad_clip_path, aspect_ratio=aspect)
                    self._splice_ad_into_video(master_rendered_path, ad_clip_path, insert_points, final_output)
                    ad_clip_path.unlink(missing_ok=True)
                else:
                    master_rendered_path.rename(final_output)
            else:
                master_rendered_path.rename(final_output)

            raw_cut_path.unlink(missing_ok=True)
            cropped_video_path.unlink(missing_ok=True)
            subtitles_path.unlink(missing_ok=True)
            master_rendered_path.unlink(missing_ok=True)

            self._compress_to_telegram_limit(final_output, duration)
            return final_output

        return await asyncio.to_thread(_process)