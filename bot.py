import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import asyncio
import logging
import re
import shutil
import signal
import sys
import uuid
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import config
from core.logger import setup_logger
from db.models import UserSettings
from db.repository import SettingsRepository
from db.session import engine, init_db
from services.ai_analyzer import AIAnalyzer
from services.downloader import VideoDownloader
from services.progress import ProgressTracker
from services.transcriber import Transcriber
from services.video_processor import VideoProcessor

setup_logger(level=logging.INFO)
logger = logging.getLogger("Bot")

session = AiohttpSession(proxy=config.HTTP_PROXY) if config.HTTP_PROXY else None
bot = Bot(token=config.BOT_TOKEN, session=session)
dp = Dispatcher()

transcriber = Transcriber()
analyzer = AIAnalyzer()
processor = VideoProcessor()

URL_REGEX = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
VPN_PROMO = "🚀 <i>Быстрый и надежный VPN без ограничений:</i> @hute2proxybot"

class Form(StatesGroup):
    waiting_watermark = State()
    waiting_banner = State()

active_tasks: dict[str, dict] = {}
processing_jobs: set[asyncio.Task] = set()

def get_settings_keyboard(task_id: str, s: UserSettings) -> InlineKeyboardMarkup:
    mode_text = "⚡ 30-60 сек" if s.mode == "short" else "🎬 До 5 минут"
    aspect_text = f"📱 {s.aspect_ratio}" if s.aspect_ratio == "9:16" else (f"🖥 {s.aspect_ratio}" if s.aspect_ratio == "16:9" else f"📺 {s.aspect_ratio}")
    face_text = "✅ Вкл" if s.face_tracking else "❌ Выкл"
    music_text = "✅ Вкл" if s.add_music else "❌ Выкл"
    wm_text = f"✅ {s.watermark_text}" if s.watermark_text else "❌ Выкл"
    desc_text = "✅ Да" if s.gen_description else "❌ Нет"

    banner_labels = {
        "none": "❌ Без рекламы",
        "start": "📍 В начале (5s)",
        "middle": "📍 В середине",
        "end": "📍 В конце",
        "every_30": "🔁 Каждые 30 сек",
    }
    banner_text = banner_labels.get(s.banner_mode, "❌ Без рекламы")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⏱ Длина: {mode_text}", callback_data=f"toggle_mode:{task_id}")],
            [InlineKeyboardButton(text=f"📐 Формат: {aspect_text}", callback_data=f"cycle_aspect:{task_id}")],
            [InlineKeyboardButton(text=f"👤 Трекинг лиц: {face_text}", callback_data=f"toggle_face:{task_id}")],
            [InlineKeyboardButton(text=f"🎵 Музыка: {music_text}", callback_data=f"toggle_music:{task_id}")],
            [InlineKeyboardButton(text=f"🏷 Водяной знак: {wm_text}", callback_data=f"set_wm:{task_id}")],
            [InlineKeyboardButton(text=f"📝 Описание TikTok: {desc_text}", callback_data=f"toggle_desc:{task_id}")],
            [InlineKeyboardButton(text=f"📺 Реклама: {banner_text}", callback_data=f"cycle_banner:{task_id}")],
            [InlineKeyboardButton(text="🚀 НАЧАТЬ ГЕНЕРАЦИЮ", callback_data=f"start_render:{task_id}")],
        ]
    )

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Отправь мне:\n"
        "• Ссылку на видео (VK, YouTube и др.)\n"
        "• <b>Magnet-ссылку</b> на торрент-фильм\n"
        "• Или отправь <b>.torrent файл</b> документом\n\n"
        f"{VPN_PROMO}",
        parse_mode=ParseMode.HTML,
    )

async def _init_task_session(message: Message, source: str | Path):
    task_id = str(uuid.uuid4())[:8]
    settings = await SettingsRepository.get_settings(message.from_user.id)
    active_tasks[task_id] = {
        "source": source,
        "user_id": message.from_user.id,
        "menu_msg_id": None,
    }

    kb = get_settings_keyboard(task_id, settings)
    menu_msg = await message.reply(
        "⚙️ <b>Параметры генерации клипов:</b>\n"
        "<i>Настройки сохраняются автоматически. Нажмите на кнопки для изменения:</i>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    active_tasks[task_id]["menu_msg_id"] = menu_msg.message_id

@dp.message(F.text.regexp(URL_REGEX))
async def handle_video_url(message: Message, state: FSMContext):
    await state.clear()
    await _init_task_session(message, message.text.strip())

@dp.message(F.text.startswith("magnet:?"))
async def handle_magnet_link(message: Message, state: FSMContext):
    await state.clear()
    await _init_task_session(message, message.text.strip())

@dp.message(F.document)
async def handle_torrent_document(message: Message, state: FSMContext):
    await state.clear()
    doc = message.document
    if doc.file_name and doc.file_name.lower().endswith(".torrent"):
        task_id = str(uuid.uuid4())[:8]
        work_dir = config.TEMP_DIR / task_id
        work_dir.mkdir(parents=True, exist_ok=True)
        torrent_path = work_dir / doc.file_name
        await bot.download(doc, destination=torrent_path)
        await _init_task_session(message, torrent_path)

@dp.callback_query(F.data.startswith("toggle_mode:"))
async def cb_toggle_mode(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.get_settings(user_id)
        new_mode = "long" if s.mode == "short" else "short"
        s = await SettingsRepository.update_settings(user_id, mode=new_mode)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("cycle_aspect:"))
async def cb_cycle_aspect(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.get_settings(user_id)
        aspects = ["9:16", "16:9", "4:3"]
        next_aspect = aspects[(aspects.index(s.aspect_ratio) + 1) % len(aspects)]
        s = await SettingsRepository.update_settings(user_id, aspect_ratio=next_aspect)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_face:"))
async def cb_toggle_face(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.get_settings(user_id)
        s = await SettingsRepository.update_settings(user_id, face_tracking=not s.face_tracking)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_music:"))
async def cb_toggle_music(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.get_settings(user_id)
        s = await SettingsRepository.update_settings(user_id, add_music=not s.add_music)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_desc:"))
async def cb_toggle_desc(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.get_settings(user_id)
        s = await SettingsRepository.update_settings(user_id, gen_description=not s.gen_description)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_wm:"))
async def cb_set_wm(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":")[1]
    if task_id not in active_tasks:
        await callback.answer()
        return

    user_id = active_tasks[task_id]["user_id"]
    s = await SettingsRepository.get_settings(user_id)

    if s.watermark_text:
        s = await SettingsRepository.update_settings(user_id, watermark_text=None)
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
        await callback.answer("Водяной знак выключен")
    else:
        await state.update_data(current_task_id=task_id, menu_msg_id=callback.message.message_id)
        await state.set_state(Form.waiting_watermark)
        prompt_msg = await callback.message.answer(
            "✏️ <b>Отправьте текст водяного знака</b> (например: <code>@my_channel</code>):",
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(prompt_msg_id=prompt_msg.message_id)
        await callback.answer()

@dp.message(Form.waiting_watermark, F.text)
async def process_watermark_text(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("current_task_id")
    menu_msg_id = data.get("menu_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")

    if prompt_msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass

    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        s = await SettingsRepository.update_settings(user_id, watermark_text=message.text.strip())
        kb = get_settings_keyboard(task_id, s)
        await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=menu_msg_id, reply_markup=kb)

    await state.clear()

@dp.callback_query(F.data.startswith("cycle_banner:"))
async def cb_cycle_banner(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":")[1]
    if task_id not in active_tasks:
        await callback.answer()
        return

    user_id = active_tasks[task_id]["user_id"]
    s = await SettingsRepository.get_settings(user_id)
    modes = ["none", "start", "middle", "end", "every_30"]
    next_mode = modes[(modes.index(s.banner_mode) + 1) % len(modes)]
    s = await SettingsRepository.update_settings(user_id, banner_mode=next_mode)

    if next_mode != "none" and not s.banner_source_path:
        await state.update_data(current_task_id=task_id, menu_msg_id=callback.message.message_id)
        await state.set_state(Form.waiting_banner)
        prompt_msg = await callback.message.answer(
            "📺 <b>Отправьте рекламное видео или фото</b> для интеграции:",
            parse_mode=ParseMode.HTML,
        )
        await state.update_data(prompt_msg_id=prompt_msg.message_id)
    else:
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))

    await callback.answer()

@dp.message(Form.waiting_banner, F.video | F.photo | F.document)
async def process_banner_media(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("current_task_id")
    menu_msg_id = data.get("menu_msg_id")
    prompt_msg_id = data.get("prompt_msg_id")

    if prompt_msg_id:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=prompt_msg_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass

    if task_id in active_tasks:
        user_id = active_tasks[task_id]["user_id"]
        work_dir = config.TEMP_DIR / task_id
        work_dir.mkdir(parents=True, exist_ok=True)

        if message.video:
            target_path = work_dir / "ad_source.mp4"
            await bot.download(message.video, destination=target_path)
        elif message.photo:
            target_path = work_dir / "ad_source.jpg"
            await bot.download(message.photo[-1], destination=target_path)
        elif message.document:
            ext = Path(message.document.file_name or "file.mp4").suffix
            target_path = work_dir / f"ad_source{ext}"
            await bot.download(message.document, destination=target_path)

        s = await SettingsRepository.update_settings(user_id, banner_source_path=str(target_path))
        kb = get_settings_keyboard(task_id, s)
        await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=menu_msg_id, reply_markup=kb)

    await state.clear()

async def run_video_pipeline(task_id: str, task_info: dict, callback: CallbackQuery):
    user_id = task_info["user_id"]
    s = await SettingsRepository.get_settings(user_id)

    settings_dict = {
        "mode": s.mode,
        "aspect_ratio": s.aspect_ratio,
        "face_tracking": s.face_tracking,
        "add_music": s.add_music,
        "watermark_text": s.watermark_text,
        "gen_description": s.gen_description,
        "banner_mode": s.banner_mode,
        "banner_source_path": s.banner_source_path,
    }

    work_dir = config.TEMP_DIR / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    status_msg = await callback.message.edit_text(
        f"⏳ <b>[1/4] Подготовка к загрузке...</b>\n\n{VPN_PROMO}",
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )
    progress = ProgressTracker(status_msg, VPN_PROMO)

    try:
        video_path = await VideoDownloader.download(
            source=task_info["source"],
            output_dir=work_dir,
            progress_tracker=progress,
        )

        await progress.update(stage_title="🎙 [2/4] Распознавание речи Whisper...", force=True)
        transcript = await transcriber.transcribe(video_path)

        all_words = []
        for segment in transcript:
            all_words.extend(segment.get("words", []))

        await progress.update(stage_title="🧠 [3/4] ИИ анализирует сюжет...", force=True)
        meta = await analyzer.extract_highlights_and_meta(transcript, mode=s.mode)
        highlights = meta.get("highlights", [])

        if not highlights:
            await status_msg.edit_text(
                f"❌ <b>Не удалось выделить интересные моменты из видео.</b>\n\n{VPN_PROMO}",
                parse_mode=ParseMode.HTML,
            )
            return

        total_clips = len(highlights)
        for idx, clip in enumerate(highlights):
            await progress.update(
                stage_title=f"✂️ [4/4] Монтаж клипа {idx + 1} из {total_clips}...",
                force=True,
            )

            output_clip_path = await processor.render_highlight(
                source_video=video_path,
                clip_data=clip,
                all_words=all_words,
                output_dir=work_dir,
                index=idx,
                settings=settings_dict,
                progress_tracker=progress,
                total_clips=total_clips,
            )

            desc_block = ""
            if s.gen_description and meta.get("tiktok_caption"):
                desc_block = f"\n\n📋 <b>TikTok Описание:</b>\n<code>{meta['tiktok_caption']}</code>"

            caption = (
                f"🎬 <b>Хайлайт #{idx + 1}</b>: {clip.get('title', 'Без названия')}\n"
                f"⏱ <b>Таймкод:</b> {clip['start']}s — {clip['end']}s\n"
                f"🍿 <b>Фильм:</b> {meta.get('movie_title', 'Неизвестно')}"
                f"{desc_block}\n\n"
                f"🛡 {VPN_PROMO}"
            )

            await callback.message.answer_video(
                video=FSInputFile(str(output_clip_path)),
                caption=caption,
                parse_mode=ParseMode.HTML,
            )

        await status_msg.delete()

    except asyncio.CancelledError:
        logger.info(f"[{task_id}] Задача отменена из-за остановки сервера.")
        raise
    except Exception as e:
        logger.error(f"[{task_id}] Ошибка обработки: {str(e)}", exc_info=True)
        await callback.message.answer(
            f"❌ <b>Произошла ошибка:</b> {str(e)}\n\n{VPN_PROMO}",
            parse_mode=ParseMode.HTML,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

@dp.callback_query(F.data.startswith("start_render:"))
async def cb_start_render(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    task_id = callback.data.split(":")[1]
    task_info = active_tasks.pop(task_id, None)

    if not task_info:
        await callback.answer("Сессия устарела, отправьте ссылку заново.", show_alert=True)
        return

    await callback.answer()
    job = asyncio.create_task(run_video_pipeline(task_id, task_info, callback))
    processing_jobs.add(job)
    job.add_done_callback(processing_jobs.discard)

async def on_startup(bot: Bot):
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен и готов к работе.")

async def on_shutdown(bot: Bot):
    logger.warning("Инициирован Graceful Shutdown...")

    if processing_jobs:
        logger.info(f"Отмена {len(processing_jobs)} активных фоновых задач...")
        for job in processing_jobs:
            job.cancel()
        await asyncio.gather(*processing_jobs, return_exceptions=True)

    await bot.session.close()
    await engine.dispose()

    shutil.rmtree(config.TEMP_DIR, ignore_errors=True)
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Все ресурсы освобождены. Сервер остановлен корректно.")

async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(dp.stop_polling()))

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass