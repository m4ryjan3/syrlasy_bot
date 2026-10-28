from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from answers import texts

def language_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇷🇺 Русский",
                    callback_data="lang:ru",
                ),
                InlineKeyboardButton(
                    text="🇰🇿 Қазақша",
                    callback_data="lang:kz"
                )
            ]
        ])


def greeting_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚨",
                    callback_data="func:phones",
                ),
                InlineKeyboardButton(
                    text="❤️",
                    callback_data="func:info",
                ),
                InlineKeyboardButton(
                    text="🧸",
                    callback_data="func:chat",
                ),
                InlineKeyboardButton(
                     text="💬",
                     callback_data="appeal:anon",
                ),
                InlineKeyboardButton(
                     text="🧠",
                     callback_data="func:emo_test",
                ),
            ]
        ])

def info_keyboard(lang: str):
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💌",
                    callback_data="info:methods",
                ),
                InlineKeyboardButton(
                     text="📄",
                     callback_data="info:test",
                ),
                InlineKeyboardButton(
                     text="❓",
                     callback_data="info:todo",
                ),
                InlineKeyboardButton(
                     text=texts[lang]["back_button"],
                     callback_data="back:menu",
                ),
            ]
        ])

def appeal_keyboard(lang: str):
     return InlineKeyboardMarkup(inline_keyboard=[
          [
               InlineKeyboardButton(
                    text=texts[lang]["appeal_not_anon_button"],
                    callback_data="appeal:not_anon"
               ),
               InlineKeyboardButton(
                    text=texts[lang]["back_button"],
                    callback_data="back:info",
               ),
          ]
     ])

def back_keyboard_menu(lang:str):
     return InlineKeyboardMarkup(inline_keyboard=[
          [
               InlineKeyboardButton(
                    text=texts[lang]["back_button"],
                    callback_data="back:menu"
               )
          ]
     ])

def back_keyboard_info(lang:str):
     return InlineKeyboardMarkup(inline_keyboard=[
          [
               InlineKeyboardButton(
                    text=texts[lang]["back_button"],
                    callback_data="back:info"
               )
          ]
     ])