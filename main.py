gemini_token = 'AIza'
bot_token = '-'
allowed_users = []
 
# Больше ничего редактировать не нужно
 
import asyncio
from aiogram import Router, Bot, Dispatcher, F, types
import logging
from io import BytesIO
from pydub import AudioSegment
import google.generativeai as gemini
from google.api_core.exceptions import InternalServerError
from google.api_core.exceptions import ResourceExhausted
from ssl import SSLError
from os import remove
from asyncio import sleep
 
bot = None
router = Router(name=__name__)
lock = asyncio.Lock()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
 
gemini.configure(api_key=gemini_token)
 
async def telegram_voice_gemini_tts(file_id: str, format: str, message_id: int) -> str:
    wav_io = BytesIO()
    AudioSegment.from_file((await bot.download_file((await bot.get_file(file_id)).file_path)), format=format).export(wav_io, format='wav')
    wav_io.seek(0)
    with open(f'vm{message_id}.wav', 'wb') as f: f.write(wav_io.getvalue())
    audio_file = gemini.upload_file(f'vm{message_id}.wav', mime_type='audio/wav')
    try:
        return gemini.GenerativeModel(model_name='gemini-1.5-flash').generate_content([f'Перескажи голосовое сообщение на русском языке. Сообщи об эмоциях автора. В случае, если ты услышал речь, начни свой ответ со слов "В {"голосовом сообщении" if format == "ogg" else "видеосообщении"} говорится". В случае, если ты не услышал в записи речь, сообщи о том, что в {"голосовом сообщении" if format == "ogg" else "видеосообщении"} нет речи.', audio_file], safety_settings=[{"category": "HARM_CATEGORY_HARASSMENT","threshold": "BLOCK_NONE",},{"category": "HARM_CATEGORY_HATE_SPEECH","threshold": "BLOCK_NONE",},{"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE",},{"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_NONE"}]).text
    finally:
        remove(f'vm{message_id}.wav')
 
@router.business_message(F.voice | F.video_note)
async def handle_message(message: types.Message):
    async with lock:
        if not (await bot.get_business_connection(message.business_connection_id)).user.id in allowed_users: return
        logger.info(f'Received voice message from {message.from_user.id}')
        recognition_message = await bot.send_message(message.from_user.id, '✨ Gemini слушает голосовое сообщение' if message.voice else '✨ Gemini смотрит видеосообщение', business_connection_id=message.business_connection_id, reply_to_message_id=message.message_id, parse_mode='HTML')
        await bot.send_chat_action(message.from_user.id, 'typing', business_connection_id=message.business_connection_id)
        while True:
            try:
                tts_result = await telegram_voice_gemini_tts(message.voice.file_id if message.voice else message.video_note.file_id, 'ogg' if message.voice else 'mp4', message.message_id)
                return await bot.edit_message_text(chat_id=message.from_user.id, message_id=recognition_message.message_id, text='✨ Gemini: ' + tts_result, business_connection_id=message.business_connection_id, parse_mode='HTML')
            except ValueError:
                return await bot.edit_message_text(chat_id=message.from_user.id, message_id=recognition_message.message_id, text='Gemini посчитал этот запрос небезопасным.', business_connection_id=message.business_connection_id, parse_mode='HTML')
            except (InternalServerError, SSLError):
                await sleep(3)
            except ResourceExhausted:
                return await bot.edit_message_text(chat_id=message.from_user.id, message_id=recognition_message.message_id, text='Достигнут лимит запросов к Gemini :(', business_connection_id=message.business_connection_id, parse_mode='HTML')
            except Exception as e:
                logger.error(e)
                await bot.send_message(allowed_users[0], str(e))
 
# @router.message()
# async def echo(message: types.Message):
#     print(message.html_text)
 
@router.message(F.chat.type == 'private', F.text)
async def handle_message(message: types.Message):
    async with lock:
        if not message.from_user.id in allowed_users: return
        await bot.send_chat_action(message.chat.id, 'typing')
        response = gemini.GenerativeModel(model_name='gemini-1.5-pro').generate_content(message.text+'\n\nОтвечай ОБЯЗАТЕЛЬНО на языке текста выше')
        await message.reply(response.text, parse_mode='MarkdownV2')
 
@router.message(F.voice | F.video_note)
async def handle_message(message: types.Message):
    async with lock:
        if not message.chat.id in allowed_users: return
        logger.info(f'Received voice message from {message.from_user.id}')
        recognition_message = await message.reply('✨ Gemini распознаёт голосовое сообщение...' if message.voice else '✨ Gemini распознаёт видеосообщение...')
        await bot.send_chat_action(message.chat.id, 'upload_voice' if message.voice else 'upload_video_note')
        while True:
            try:
                tts_result = await telegram_voice_gemini_tts(message.voice.file_id if message.voice else message.video_note.file_id, 'ogg' if message.voice else 'mp4', message.message_id)
                return await bot.edit_message_text(chat_id=recognition_message.chat.id, message_id=recognition_message.message_id, text='✨ Gemini: ' + tts_result, parse_mode='HTML')
            except ValueError:
                return await bot.edit_message_text(chat_id=recognition_message.chat.id, message_id=recognition_message.message_id, text='Gemini посчитал этот запрос небезопасным.', parse_mode='HTML')
            except (InternalServerError, SSLError):
                await sleep(3)
            except ResourceExhausted:
                return await bot.edit_message_text(chat_id=recognition_message.chat.id, message_id=recognition_message.message_id, text='Достигнут лимит запросов к Gemini :(')
            except Exception as e:
                logger.error(e)
                await bot.send_message(allowed_users[0], str(e))
                await sleep(10)
 
async def main():
    global bot
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
 
 
asyncio.run(main())
