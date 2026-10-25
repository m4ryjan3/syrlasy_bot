import asyncio
import logging
import sqlite3

from pathlib import Path
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from answers import texts
from databases import *
from keyboards import back_keyboard_menu, back_keyboard_info

ADMIN_CHAT_ID = -5571000368
PROJECT_DIR = Path(__file__).resolve().parent
DB_PATH = PROJECT_DIR / "bot.db"

router = Router()
log = logging.getLogger(__name__)


def _save_link_appeal(admin_message_id: int, user_id: int, user_message_id: int, status: str = "anon"):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO support_messages "
            "(admin_message_id, user_id, user_message_id, status) VALUES (?, ?, ?, ?)",
            (admin_message_id, user_id, user_message_id, status),
        )


def _get_link_sync(admin_message_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT user_id, user_message_id FROM support_messages "
            "WHERE admin_message_id = ?",
            (admin_message_id,),
        ).fetchone()


async def save_link(admin_message_id: int, user_id: int, user_message_id: int, status: str = "anon"):
    await asyncio.to_thread(_save_link_appeal, admin_message_id, user_id, user_message_id, status)


async def get_link(admin_message_id: int):
    return await asyncio.to_thread(_get_link_sync, admin_message_id)


# ---------- общая логика отправки обращения в админ-чат ----------

async def relay_to_admin(message: Message, bot: Bot, caption: str, status: str) -> bool:
    """Копирует сообщение пользователя в админ-чат, добавляет подпись реплаем
    и сохраняет связки в БД. Возвращает True, если всё отправилось."""
    try:
        forwarded = await bot.copy_message(
            chat_id=ADMIN_CHAT_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
    except TelegramAPIError as e:
        log.error("Не удалось переслать сообщение в админ-чат: %s", e)
        await message.answer("Сейчас не получается передать сообщение, попробуйте позже.")
        return False

    await save_link(forwarded.message_id, message.from_user.id, message.message_id, status)

    info = await bot.send_message(
        ADMIN_CHAT_ID, caption,
        reply_to_message_id=forwarded.message_id,
        parse_mode=None,
    )
    # на подпись тоже можно отвечать
    await save_link(info.message_id, message.from_user.id, message.message_id, status)
    return True

SUPPORT_CALLBACK_DATA = "appeal:anon"


class SupportState(StatesGroup):
    waiting_message = State()


@router.callback_query(F.data == SUPPORT_CALLBACK_DATA)
async def support_button(callback: CallbackQuery, state: FSMContext):
    lang = get_language(callback.from_user.id)
    await state.set_state(SupportState.waiting_message)
    await callback.message.edit_text(texts[lang]["appeal_anon"], reply_markup=back_keyboard_menu(lang))
    await callback.answer()


@router.message(SupportState.waiting_message, F.chat.type == "private")
async def user_message(message: Message, bot: Bot, state: FSMContext):
    caption = "📩 Новое анонимное обращение!"
    if await relay_to_admin(message, bot, caption, status="anon"):
        await state.clear()
        await message.answer(texts[get_language(message.from_user.id)]["appeal_send"])

NAMED_CALLBACK_DATA = "appeal:not_anon"


class NamedState(StatesGroup):
    waiting_message = State()


@router.callback_query(F.data == NAMED_CALLBACK_DATA)
async def named_button(callback: CallbackQuery, state: FSMContext):
    lang = get_language(callback.from_user.id)
    await state.set_state(NamedState.waiting_message)
    await callback.message.edit_text(texts[lang]["appeal_not_anon"], reply_markup=back_keyboard_info(lang))
    await callback.answer()


@router.message(NamedState.waiting_message, F.chat.type == "private")
async def named_message(message: Message, bot: Bot, state: FSMContext):
    user = message.from_user
    caption = f"📩 Новое обращение от {user.full_name}"
    if user.username:
        caption += f" (@{user.username})"
    caption += f"\nID: {user.id}"

    if await relay_to_admin(message, bot, caption, status="named"):
        await state.clear()
        await message.answer(texts[get_language(user.id)]["appeal_send"])

@router.message(F.chat.id == ADMIN_CHAT_ID, F.reply_to_message)
async def admin_reply(message: Message, bot: Bot):
    link = await get_link(message.reply_to_message.message_id)
    if link is None:
        await message.reply("Не нашёл, какому пользователю это адресовано. "
                            "Отвечайте реплаем на пересланное сообщение клиента.")
        return

    user_id, user_message_id = link
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_to_message_id=user_message_id,
            allow_sending_without_reply=True,
        )
    except TelegramAPIError as e:
        log.warning("Не удалось доставить ответ пользователю %s: %s", user_id, e)
        await message.reply(f"Не удалось доставить ответ: {e}")