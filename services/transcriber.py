import asyncio
import logging
import os
import subprocess
from pathlib import Path
from faster_whisper import WhisperModel
from config import config

logger = logging.getLogger("Transcriber")

class Transcriber:
    def __init__(self):
        threads = os.cpu_count() or 4
        logger.info(f"Запуск Whisper ({config.WHISPER_MODEL}, {config.WHISPER_DEVICE}, {threads} потоков)...")
        self.model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            cpu_threads=threads,
            num_workers=2,
        )

    async def transcribe(self, video_path: Path) -> list[dict]:
        def _transcribe():
            wav_path = video_path.parent / "temp_whisper_audio.wav"
            
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-af", "highpass=f=100,lowpass=f=4000,dynaudnorm=f=100:g=11",
                "-c:a", "pcm_s16le",
                str(wav_path)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            segments, info = self.model.transcribe(
                str(wav_path),
                beam_size=3,
                best_of=3,
                temperature=[0.0, 0.2, 0.4],
                initial_prompt="Разговорная русская речь, диалоги и реплики из фильма, правильная пунктуация, имена собственные.",
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=250),
                condition_on_previous_text=False,
            )
            
            results = []
            for s in segments:
                results.append({
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text.strip(),
                    "words": [
                        {
                            "word": w.word.strip(),
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                        }
                        for w in s.words
                    ],
                })
                
            wav_path.unlink(missing_ok=True)
            return results

        return await asyncio.to_thread(_transcribe)