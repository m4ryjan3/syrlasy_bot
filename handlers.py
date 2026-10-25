from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
)
from answers import texts
from keyboards import *
from databases import get_language, save_language
from aiogram.enums import ParseMode
from aiogram.filters import Command

rt = Router()
@rt.message(CommandStart())
async def start(message: Message):
    lang = get_language(message.from_user.id)
    if lang:
        await message.answer(
            texts[lang]["welcome"],
            reply_markup=greeting_keyboard()
        ),
        return
    await message.answer(
        "🌍 Выберите язык / Тілді таңдаңыз",
        reply_markup=language_keyboard()
    )

@rt.callback_query(F.data.startswith("lang:"))
async def define_language(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    save_language(callback.from_user.id, lang)
    await callback.message.edit_text(texts[lang]["changed_lang"])
    await callback.message.answer(
        texts[lang]["welcome"],
        reply_markup=greeting_keyboard()
    )


@rt.callback_query(F.data == "func:phones")
async def phones(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        texts[lang]["phones"],
        reply_markup=back_keyboard_menu(lang)
    )

@rt.callback_query(F.data == "func:info")
async def info(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["info"],
        reply_markup=info_keyboard(lang)
    )

@rt.callback_query(F.data == "func:chat")
async def chat(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["chat"],
        reply_markup=back_keyboard_menu(lang)
    )

@rt.callback_query(F.data == "func:anon")
async def anon(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["appeal_anon"],
        reply_markup=back_keyboard_menu(lang)
    )

@rt.callback_query(F.data == "func:emo_test")
async def emo_test(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["emotional_test"],
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard_menu(lang)
    )

@rt.callback_query(F.data == "info:methods")
async def methods(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["bulling_info"],
        reply_markup=back_keyboard_info(lang)
    )


@rt.callback_query(F.data == "info:test")
async def test(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["test"],
        parse_mode=ParseMode.HTML,
        reply_markup=back_keyboard_info(lang)
    )

@rt.callback_query(F.data == "info:todo")
async def todo(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["instr"],
        reply_markup=appeal_keyboard(lang)
    )

@rt.callback_query(F.data == "back:menu")
async def back_menu(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["welcome"],
        reply_markup=greeting_keyboard()
    )

@rt.callback_query(F.data == "back:info")
async def back_info(callback: CallbackQuery):
    lang = get_language(callback.from_user.id)
    await callback.message.edit_text(
        text=texts[lang]["info"],
        reply_markup=info_keyboard(lang)
    )

@rt.message(Command("change_language"))
async def change_language(message: Message):
    await message.answer(
        "🌍 Выберите язык / Тілді таңдаңыз",
        reply_markup=language_keyboard()
    )

