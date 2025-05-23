import logging
import os
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import CommandStart
from dotenv import load_dotenv

load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

logging.basicConfig(level=logging.INFO)

choice_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отправить текст")],
        [KeyboardButton(text="Загрузить фото")],
        [KeyboardButton(text="Загрузить видео")]
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Выберите тип контента"
)

moderation_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="✅ Опубликовать", callback_data="approve"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_choose_reason")
    ]
])

rejection_reasons_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="❌ Спам/реклама", callback_data="reject_reason_spam"),
        InlineKeyboardButton(text="❌ Некачественный контент", callback_data="reject_reason_low_quality")
    ],
    [
        InlineKeyboardButton(text="❌ Не по теме", callback_data="reject_reason_offtopic"),
        InlineKeyboardButton(text="❌ Другое", callback_data="reject_reason_other")
    ]
])

return_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Назад")]],
    resize_keyboard=True,
    one_time_keyboard=True
)

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

user_state = {}
moderation_queue = {}
pending_hashtags = {}
user_limits = defaultdict(list)

BOT_USERNAME = "LifehackWorld_bot"
HASHTAGS = ["#еда", "#путешествия", "#быт", "#здоровье", "#город", "#другое", "#простоЮмор"]

CONTENT_LIMITS = {
    "text": 2,
    "photo": 2,
    "video": 2
}

CONTENT_TYPES = ["text", "photo", "video"]


def get_hashtag_keyboard():
    buttons = [InlineKeyboardButton(text=tag, callback_data=f"hashtag_{tag[1:]}") for tag in HASHTAGS]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


def check_limit(user_id: int, content_type: str) -> bool:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    if user_id == ADMIN_ID:
        return True  # Админ может всё

    now = datetime.now()
    window = timedelta(hours=12)  # Лимит на 12 часов

    # Убедимся, что у пользователя уже есть список
    if user_id not in user_limits:
        user_limits[user_id] = []

    # Оставим только свежие попытки (за последние 12 часов)
    user_limits[user_id] = [
        ts for ts in user_limits[user_id]
        if now - ts["time"] < window
    ]

    # Считаем, сколько контента такого типа уже было отправлено
    type_count = sum(1 for ts in user_limits[user_id] if ts["type"] == content_type)

    if type_count >= CONTENT_LIMITS[content_type]:
        return False

    # Добавляем новую попытку
    user_limits[user_id].append({"type": content_type, "time": now})
    return True



@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_state[message.from_user.id] = None
    await message.answer(
       "Привет! 👋\n"
       "Ты попал в бот канала «Лайфхаки со всего света» 🌍\n\n"

  "Здесь собираются лучшие трюки, советы и находки от людей со всего мира.\n\n"
  "Хочешь поделиться своим лайфхаком?\n\n"
  "Отправляй:\n"
  "— Короткие видео (до 1 мин) 🎥\n"
  "— Фото с комментарием 📸\n"
  "— Просто текст (если лень снимать) ✍️",
        reply_markup=choice_keyboard
    )


@dp.message(F.text.in_({"Отправить текст", "Загрузить фото", "Загрузить видео"}))
async def handle_choice(message: Message):
    user_id = message.from_user.id
    choice = message.text

    states = {
        "Отправить текст": "waiting_text",
        "Загрузить фото": "waiting_photo",
        "Загрузить видео": "waiting_video"
    }

    content_type = {
        "Отправить текст": "text",
        "Загрузить фото": "photo",
        "Загрузить видео": "video"
    }[choice]

    if not check_limit(user_id, content_type):
        await message.answer("❌ Вы достигли лимита. Разрешено до 2 постов каждого типа (текст, фото, видео) каждые 12 часов.")

        return

    user_state[user_id] = states[choice]

    prompts = {
        "waiting_text": "✍️ Напиши свой лайфхак (до 500 знаков):",
        "waiting_photo": "📸 Отправь фото с комментарием:",
        "waiting_video": "🎥 Отправь короткое видео (до 1 мин):"
    }

    await message.answer(prompts[user_state[user_id]], reply_markup=return_keyboard)


@dp.message(F.text == "⬅️ Назад")
async def go_back(message: Message):
    user_id = message.from_user.id
    user_state[user_id] = None
    pending_hashtags.pop(user_id, None)
    await message.answer(
        "Ты вернулся в главное меню. Выбери, что хочешь отправить:",
        reply_markup=choice_keyboard
    )






@dp.message(F.text)
async def handle_text_input(message: Message):
    user_id = message.from_user.id
    if user_state.get(user_id) == "waiting_text":
        if len(message.text) > 500:
            await message.answer("⚠️ Текст должен быть до 500 знаков. Попробуйте снова.")
            return
        pending_hashtags[user_id] = {
            "type": "text",
            "text": f"Текст от <b>{message.from_user.full_name}</b>:\n\n{message.text}"
        }
        await message.answer("📌 Выберите рубрику для своего лайфхака:", reply_markup=get_hashtag_keyboard())
        user_state[user_id] = None
    elif user_state.get(user_id) in {"waiting_photo", "waiting_video"}:
        await message.answer("⚠️ Это не тот тип контента. Пожалуйста, отправьте правильный.")


# Храним ID уже обработанных альбомов, чтобы не отвечать несколько раз
handled_media_groups = set()

@dp.message(F.photo)
async def handle_photo_input(message: Message):
    user_id = message.from_user.id

    # Проверка: если это альбом (media_group), игнорируем все, кроме первого
    if message.media_group_id:
        if message.media_group_id in handled_media_groups:
            return  # Уже ответили на этот альбом — игнорируем остальные фото
        handled_media_groups.add(message.media_group_id)
        await message.answer("⚠️ Пожалуйста, отправьте только одно фото, а не альбом.")
        return

    if user_state.get(user_id) == "waiting_photo":
        caption = message.caption or "Без подписи"
        pending_hashtags[user_id] = {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": f"Фото от <b>{message.from_user.full_name}</b>:\n\n{caption}"
        }
        await message.answer("📌 Выберите рубрику для фото:", reply_markup=get_hashtag_keyboard())
        user_state[user_id] = None
    elif user_state.get(user_id) in {"waiting_text", "waiting_video"}:
        await message.answer("⚠️ Это не тот тип контента. Пожалуйста, отправьте правильный.")



@dp.message(F.video)
async def handle_video_input(message: Message):
    user_id = message.from_user.id
    if user_state.get(user_id) == "waiting_video":
        caption = message.caption or "Без подписи"
        pending_hashtags[user_id] = {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": f"Видео от <b>{message.from_user.full_name}</b>:\n\n{caption}"
        }
        await message.answer("📌 Выберите рубрику для видео:", reply_markup=get_hashtag_keyboard())
        user_state[user_id] = None
    elif user_state.get(user_id) in {"waiting_text", "waiting_photo"}:
        await message.answer("⚠️ Это не тот тип контента. Пожалуйста, отправьте правильный.")


@dp.callback_query(F.data.startswith("hashtag_"))
async def handle_hashtag_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in pending_hashtags:
        await callback.answer("Сначала отправьте контент.", show_alert=True)
        return

    tag_raw = callback.data.split("_", 1)[1]
    hashtag = f"#{tag_raw}"
    content = pending_hashtags.pop(user_id, None)

    if not content:
        await callback.answer("Контент не найден.", show_alert=True)
        return

    add_link = f'\n\n<a href="https://t.me/{BOT_USERNAME}">Добавить свой лайфхак</a>'

    try:
        if content["type"] == "text":
            full_text = f"{content['text']}\n\n{hashtag}{add_link}"
            sent = await bot.send_message(ADMIN_ID, full_text, reply_markup=moderation_keyboard)
            moderation_queue[sent.message_id] = {
                "type": "text",
                "content": full_text,
                "sender_id": user_id
            }

        elif content["type"] == "photo":
            caption = f"{content['caption']}\n\n{hashtag}{add_link}"
            sent = await bot.send_photo(ADMIN_ID, content["file_id"], caption=caption, reply_markup=moderation_keyboard)
            moderation_queue[sent.message_id] = {
                "type": "photo",
                "file_id": content["file_id"],
                "caption": caption,
                "sender_id": user_id
            }

        elif content["type"] == "video":
            caption = f"{content['caption']}\n\n{hashtag}{add_link}"
            sent = await bot.send_video(ADMIN_ID, content["file_id"], caption=caption, reply_markup=moderation_keyboard)
            moderation_queue[sent.message_id] = {
                "type": "video",
                "file_id": content["file_id"],
                "caption": caption,
                "sender_id": user_id
            }

        await callback.message.answer("✅ Спасибо! Ваш лайфхак уже в пути.", reply_markup=choice_keyboard)
        await callback.answer("Рубрика выбрана.")
    except Exception as e:
        await callback.message.answer("❌ Ошибка при отправке. Попробуйте ещё раз.")
        logging.exception("Ошибка отправки:")


@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    message_id = callback.message.message_id
    data = moderation_queue.get(message_id)

    if not data:
        await callback.answer("Контент не найден или уже обработан.", show_alert=True)
        return

    if callback.data == "approve":
        if data["type"] == "text":
            await bot.send_message(CHANNEL_ID, data["content"])
        elif data["type"] == "photo":
            await bot.send_photo(CHANNEL_ID, data["file_id"], caption=data["caption"])
        elif data["type"] == "video":
            await bot.send_video(CHANNEL_ID, data["file_id"], caption=data["caption"])

        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("✅ Опубликовано в канал.")
        await bot.send_message(data["sender_id"], "✅ Ваш лайфхак опубликован в канале. Спасибо за участие!")

        del moderation_queue[message_id]
        await callback.answer("Опубликовано.")

    elif callback.data == "reject_choose_reason":
        await callback.message.edit_reply_markup(reply_markup=rejection_reasons_keyboard)
        await callback.answer()

    elif callback.data.startswith("reject_reason_"):
        reasons = {
            "reject_reason_spam": "Спам или реклама",
            "reject_reason_low_quality": "Запрещенный контент",
            "reject_reason_offtopic": "Не по теме",
            "reject_reason_other": "Другая причина"
        }
        reason = reasons.get(callback.data, "Причина не указана")
        await bot.send_message(data["sender_id"], f"❌ Ваш лайфхак отклонён. Причина: {reason}")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"❌ Отклонено. Причина: {reason}")
        del moderation_queue[message_id]
        await callback.answer("Отклонено.")


async def main():
    await bot.send_message(ADMIN_ID, "Бот запущен ✅")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
