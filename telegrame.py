import requests
try:
    from commands import *
except ImportError:
    from bootstrapping_module import * 
try:
    import telebot
except ImportError:
    from commands.pip9 import Pip
    Pip.install("pytelegrambotapi")
    import telebot

__version__ = "0.3.1"


def safe_start_bot(bot_func, skipped_exceptions=(requests.exceptions.ReadTimeout,
                                                 requests.exceptions.ConnectionError,
                                                 requests.exceptions.ChunkedEncodingError)):
    ended = False
    while not ended:
        try:
            bot_func()
            ended = True
        except skipped_exceptions as e:
            print(f"{e} {e.args} {e.with_traceback(e.__traceback__)}... {Time.dotted()}")
            Time.sleep(5)


def very_safe_start_bot(bot_func):
    safe_start_bot(bot_func=bot_func, skipped_exceptions=(requests.exceptions.ReadTimeout,
                                                          requests.exceptions.ConnectionError,
                                                          requests.exceptions.ChunkedEncodingError,
                                                          telebot.apihelper.ApiException))


def download_file(telegram_api, telegram_token, file_id, output_path):
    import requests
    import shutil
    file_info = telegram_api.get_file(file_id)
    address = f'https://api.telegram.org/file/bot{telegram_token}/{file_info.file_path}'
    r = requests.get(address, stream=True)
    if r.status_code == 200:
        with open(output_path, 'wb') as f:
            r.raw.decode_content = True
            shutil.copyfileobj(r.raw, f)
    else:
        raise requests.HTTPError(f"Status: '{r.status_code}', address: '{address}'")


def send_photo(telegram_api, image_path, message):
    if not File.exist(image_path):
        raise FileNotFoundError(f"File not exist: '{image_path}'")
    photo = open(image_path, 'rb')
    telegram_api.send_photo(message.chat.id, photo)


def send_message(telegram_api_object, chat_id, text,
                      disable_web_page_preview=None, reply_to_message_id=None, reply_markup=None,
                      parse_mode=None, disable_notification=None):
    texts = [text]
    if len(text) > 4096:
        texts = Str.split_every(text, 4096)
    output = []
    for text in texts:
        output.append(telegram_api_object.send_message(chat_id=chat_id, text=text, disable_web_page_preview=disable_web_page_preview,
                                         reply_to_message_id=reply_to_message_id, reply_markup=reply_markup,
                                         parse_mode=parse_mode, disable_notification=disable_notification))
    if len(output) == 0:
        return None
    elif len(output) == 1:
        return output[0]
    else:
        return output
