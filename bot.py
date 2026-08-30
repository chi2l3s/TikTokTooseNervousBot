import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import asyncio
import logging
import re
import shutil
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
from services.ai_analyzer import AIAnalyzer
from services.downloader import VideoDownloader
from services.transcriber import Transcriber
from services.video_processor import VideoProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
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

user_sessions = {}

def get_settings_keyboard(task_id: str, s: dict) -> InlineKeyboardMarkup:
    mode_text = "⚡ 30-60 сек" if s["mode"] == "short" else "🎬 До 5 минут"
    music_text = "✅ Вкл" if s["add_music"] else "❌ Выкл"
    wm_text = f"✅ {s['watermark_text']}" if s["watermark_text"] else "❌ Выкл"
    desc_text = "✅ Да" if s["gen_description"] else "❌ Нет"

    banner_labels = {
        "none": "❌ Без интеграции",
        "start": "📍 В начале (5s)",
        "middle": "📍 В середине",
        "end": "📍 В конце",
        "every_30": "🔁 Каждые 30 сек",
    }
    banner_text = banner_labels.get(s["banner_mode"], "❌ Без интеграции")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⏱ Длина: {mode_text}", callback_data=f"toggle_mode:{task_id}")],
            [InlineKeyboardButton(text=f"🎵 Музыка: {music_text}", callback_data=f"toggle_music:{task_id}")],
            [InlineKeyboardButton(text=f"🏷 Водяной знак: {wm_text}", callback_data=f"set_wm:{task_id}")],
            [InlineKeyboardButton(text=f"📝 Описание TikTok: {desc_text}", callback_data=f"toggle_desc:{task_id}")],
            [InlineKeyboardButton(text=f"📺 Реклама (видео/фото): {banner_text}", callback_data=f"cycle_banner:{task_id}")],
            [InlineKeyboardButton(text="🚀 НАЧАТЬ ГЕНЕРАЦИЮ", callback_data=f"start_render:{task_id}")],
        ]
    )

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Отправь мне ссылку на видео (VK Видео, YouTube и др.), "
        "выбери параметры и получи готовые анимированные клипы для Shorts/Reels.\n\n"
        f"{VPN_PROMO}",
        parse_mode=ParseMode.HTML,
    )

@dp.message(F.text.regexp(URL_REGEX))
async def handle_video_url(message: Message, state: FSMContext):
    await state.clear()
    url = message.text.strip()
    task_id = str(uuid.uuid4())[:8]

    user_sessions[task_id] = {
        "url": url,
        "mode": "short",
        "add_music": True,
        "watermark_text": None,
        "gen_description": True,
        "banner_mode": "none",
        "banner_source_path": None,
        "chat_id": message.chat.id,
        "menu_msg_id": None,
    }

    kb = get_settings_keyboard(task_id, user_sessions[task_id])
    menu_msg = await message.reply(
        "⚙️ <b>Настройки генерации клипов:</b>\n"
        "Нажмите на нужные кнопки для изменения параметров:",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )
    user_sessions[task_id]["menu_msg_id"] = menu_msg.message_id

@dp.callback_query(F.data.startswith("toggle_mode:"))
async def cb_toggle_mode(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in user_sessions:
        s = user_sessions[task_id]
        s["mode"] = "long" if s["mode"] == "short" else "short"
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_music:"))
async def cb_toggle_music(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in user_sessions:
        s = user_sessions[task_id]
        s["add_music"] = not s["add_music"]
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_desc:"))
async def cb_toggle_desc(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]
    if task_id in user_sessions:
        s = user_sessions[task_id]
        s["gen_description"] = not s["gen_description"]
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
    await callback.answer()

@dp.callback_query(F.data.startswith("set_wm:"))
async def cb_set_wm(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":")[1]
    if task_id not in user_sessions:
        await callback.answer()
        return

    s = user_sessions[task_id]
    if s["watermark_text"]:
        s["watermark_text"] = None
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(task_id, s))
        await callback.answer("Водяной знак выключен")
    else:
        await state.update_data(current_task_id=task_id, menu_msg_id=callback.message.message_id)
        await state.set_state(Form.waiting_watermark)
        prompt_msg = await callback.message.answer("✏️ <b>Отправьте текст водяного знака</b> (например: <code>@my_channel</code>):", parse_mode=ParseMode.HTML)
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

    if task_id in user_sessions:
        user_sessions[task_id]["watermark_text"] = message.text.strip()
        kb = get_settings_keyboard(task_id, user_sessions[task_id])
        await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=menu_msg_id, reply_markup=kb)

    await state.clear()

@dp.callback_query(F.data.startswith("cycle_banner:"))
async def cb_cycle_banner(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":")[1]
    if task_id not in user_sessions:
        await callback.answer()
        return

    s = user_sessions[task_id]
    modes = ["none", "start", "middle", "end", "every_30"]
    curr_idx = modes.index(s["banner_mode"])
    next_mode = modes[(curr_idx + 1) % len(modes)]
    s["banner_mode"] = next_mode

    if next_mode != "none" and not s.get("banner_source_path"):
        await state.update_data(current_task_id=task_id, menu_msg_id=callback.message.message_id)
        await state.set_state(Form.waiting_banner)
        prompt_msg = await callback.message.answer("📺 <b>Отправьте рекламное видео или фото</b> для интеграции:", parse_mode=ParseMode.HTML)
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

    if task_id in user_sessions:
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

        user_sessions[task_id]["banner_source_path"] = str(target_path)
        kb = get_settings_keyboard(task_id, user_sessions[task_id])
        await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=menu_msg_id, reply_markup=kb)

    await state.clear()

@dp.callback_query(F.data.startswith("start_render:"))
async def cb_start_render(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    task_id = callback.data.split(":")[1]
    s = user_sessions.pop(task_id, None)

    if not s:
        await callback.answer("Сессия устарела, отправьте ссылку заново.", show_alert=True)
        return

    await callback.answer()
    work_dir = config.TEMP_DIR / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    status_msg = await callback.message.edit_text(
        f"⏳ <b>[1/4] Скачивание видео...</b>\n"
        f"⏱ <i>Примерное время: ~4-6 мин</i>\n\n"
        f"{VPN_PROMO}",
        parse_mode=ParseMode.HTML,
        reply_markup=None,
    )

    try:
        video_path = await VideoDownloader.download(s["url"], work_dir)

        await status_msg.edit_text(
            f"🎙 <b>[2/4] Распознавание речи и таймкодов...</b>\n"
            f"⏱ <i>Примерное время: ~2-3 мин</i>\n\n"
            f"{VPN_PROMO}",
            parse_mode=ParseMode.HTML,
        )
        transcript = await transcriber.transcribe(video_path)

        all_words = []
        for segment in transcript:
            all_words.extend(segment.get("words", []))

        await status_msg.edit_text(
            f"🧠 <b>[3/4] ИИ анализирует сюжет и создает описание...</b>\n"
            f"⏱ <i>Примерное время: ~1 мин</i>\n\n"
            f"{VPN_PROMO}",
            parse_mode=ParseMode.HTML,
        )
        meta = await analyzer.extract_highlights_and_meta(transcript, mode=s["mode"])
        highlights = meta.get("highlights", [])

        if not highlights:
            await status_msg.edit_text(
                f"❌ <b>Не удалось выделить интересные моменты из видео.</b>\n\n{VPN_PROMO}",
                parse_mode=ParseMode.HTML,
            )
            return

        total_clips = len(highlights)
        for idx, clip in enumerate(highlights):
            remaining_mins = max(1, total_clips - idx)
            await status_msg.edit_text(
                f"✂️ <b>[4/4] Монтаж клипа {idx + 1} из {total_clips} (Караоке + Интеграции)...</b>\n"
                f"⏱ <i>Осталось: ~{remaining_mins} мин</i>\n\n"
                f"{VPN_PROMO}",
                parse_mode=ParseMode.HTML,
            )

            output_clip_path = await processor.render_highlight(
                source_video=video_path,
                clip_data=clip,
                all_words=all_words,
                output_dir=work_dir,
                index=idx,
                settings=s,
            )

            desc_block = ""
            if s["gen_description"] and meta.get("tiktok_caption"):
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

    except Exception as e:
        logger.error(f"[{task_id}] Ошибка: {str(e)}", exc_info=True)
        await callback.message.answer(
            f"❌ <b>Произошла ошибка:</b> {str(e)}\n\n{VPN_PROMO}",
            parse_mode=ParseMode.HTML,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())