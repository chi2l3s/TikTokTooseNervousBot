import asyncio
import time
from aiogram.enums import ParseMode
from aiogram.types import Message


class ProgressTracker:
    def __init__(self, message: Message, promo_text: str):
        self.message = message
        self.promo_text = promo_text
        self.last_update_time = 0.0
        self.update_interval = 2.5
        self.start_time = time.time()
        self._lock = asyncio.Lock()

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        seconds = max(0, int(seconds))
        m, s = divmod(seconds, 60)
        return f'{m:02d}:{s:02d}'

    @staticmethod
    def _create_bar(percent: float, length: int = 10) -> str:
        percent = max(0.0, min(100.0, percent))
        filled = int(round(length * percent / 100))
        return "█" * filled + "░" * (length - filled)

    async def update(
        self,
        stage_title: str,
        percent: float | None = None,
        eta_seconds: float | None = None,
        extra_info: str = "",
        force: bool = False
    ):
        now = time.time()
        if not force and (now - self.last_update_time < self.update_interval):
            return
        
        async with self._lock:
            if not force and (now - self.last_update_time < self.update_interval):
                return
            self.last_update_time = now
            
            elapsed = now - self.start_time
            lines = [f'<b>{stage_title}</b>\n']
            
            if percent is not None:
                bar = self._create_bar(percent)
                lines.append(f'📊 <code>[{bar}] {percent:.1f}%</code>')
                
            timing = f"⏱ <i>Прошло: {self._format_seconds(elapsed)}</i>"
            if eta_seconds is not None and eta_seconds > 0:
                timing += f" | <i>Осталось: ~{self._format_seconds(eta_seconds)}</i>"
            lines.append(timing)
            
            if extra_info:
                lines.append(f"ℹ️ {extra_info}")
                
            lines.append(f'\n{self.promo_text}')
            text = "\n".join(lines)
            
            try:
                await self.message.edit_text(text, parse_mode=ParseMode.HTML)
            except Exception:
                pass
