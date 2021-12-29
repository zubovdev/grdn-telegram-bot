import logging

from telegram import Bot
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CallbackContext
from telegram.ext import CallbackQueryHandler
from telegram.ext import Updater
from telegram.ext import MessageHandler
from telegram.ext import CommandHandler
from telegram.ext import ConversationHandler
from telegram.ext import Filters
from telegram.utils.request import Request

from echo.config import load_config
from echo.utils import logger_factory
from anketa.validators import GENDER_MAP
from anketa.validators import gender_hru
from anketa.validators import validate_age


config = load_config()

logger = logging.getLogger(__name__)

debug_requests = logger_factory(logger=logger)


NAME, GENDER, AGE = range(3)

CALLBACK_BEGIN = 'x1'


@debug_requests
def start_buttons_handler(update: Update, context: CallbackContext):
    """ Не относится к сценарию диалога, но создаёт начальные inline-кнопки
    """
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text='Начать', callback_data=CALLBACK_BEGIN),
            ],
        ],
    )
    update.message.reply_text(
        'Нажми на кнопку:',
        reply_markup=inline_buttons,
    )


@debug_requests
def start_handler(update: Update, context: CallbackContext):
    """ Начало взаимодействия по клику на inline-кнопку
    """
    init = update.callback_query.data
    chat_id = update.callback_query.message.chat.id

    if init != CALLBACK_BEGIN:
        logger.debug('bad init: %s', init)
        update.callback_query.bot.send_message(
            chat_id=chat_id,
            text='Что-то пошло не так, обратитесь к администратору бота',
        )
        return ConversationHandler.END

    update.callback_query.answer()

    # Спросить имя
    update.callback_query.bot.send_message(
        chat_id=chat_id,
        text='Введи своё имя чтобы продолжить:',
    )
    return NAME


@debug_requests
def name_handler(update: Update, context: CallbackContext):
    # Получить имя
    context.user_data[NAME] = update.message.text
    logger.info('user_data: %s', context.user_data)

    # Спросить пол
    inline_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=value, callback_data=key) for key, value in GENDER_MAP.items()],
        ],
    )
    update.message.reply_text(
        text='Выберите свой пол чтобы продолжить',
        reply_markup=inline_buttons,
    )
    return GENDER


@debug_requests
def age_handler(update: Update, context: CallbackContext):
    # Получить пол
    gender = update.callback_query.data
    gender = int(gender)
    if gender not in GENDER_MAP:
        # Этой ситуации не должно быть для пользователя! То есть какое-то значение
        # в кнопках есть, но оно не включено в список гендеров
        update.effective_message.reply_text('Что-то пошло не так, обратитесь к администратору бота')
        return GENDER

    context.user_data[GENDER] = gender
    logger.info('user_data: %s', context.user_data)

    # Спросить возраст
    update.effective_message.reply_text(
        text='Введите свой возраст:',
    )
    return AGE


@debug_requests
def finish_handler(update: Update, context: CallbackContext):
    # Получить возраст
    age = validate_age(text=update.message.text)
    if age is None:
        update.message.reply_text('Пожалуйста, введите корректный возраст!')
        return AGE

    context.user_data[AGE] = age
    logger.info('user_data: %s', context.user_data)

    # TODO: вот тут запись в базу финала
    # TODO 2: очистить `user_data`

    # Завершить диалог
    update.message.reply_text(f'''
Все данные успешно сохранены! 
Вы: {context.user_data[NAME]}, пол: {gender_hru(context.user_data[GENDER])}, возраст: {context.user_data[AGE]} 
''')
    return ConversationHandler.END


@debug_requests
def cancel_handler(update: Update, context: CallbackContext):
    """ Отменить весь процесс диалога. Данные будут утеряны
    """
    update.message.reply_text('Отмена. Для начала с нуля нажмите /start')
    return ConversationHandler.END


@debug_requests
def echo_handler(update: Update, context: CallbackContext):
    update.message.reply_text(
        'Нажмите /start для заполнения анкеты!',
    )


def main():
    logger.info('Started Anketa-bot')

    req = Request(
        connect_timeout=0.5,
        read_timeout=1.0,
    )
    bot = Bot(
        token=config.TG_TOKEN,
        request=req,
        base_url=config.TG_API_URL,
    )
    updater = Updater(
        bot=bot,
        use_context=True,
    )

    # Проверить что бот корректно подключился к Telegram API
    info = bot.get_me()
    logger.info(f'Bot info: {info}')

    # Навесить обработчики команд
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_handler, pass_user_data=True),
        ],
        states={
            NAME: [
                MessageHandler(Filters.all, name_handler, pass_user_data=True),
            ],
            GENDER: [
                CallbackQueryHandler(age_handler, pass_user_data=True),
            ],
            AGE: [
                MessageHandler(Filters.all, finish_handler, pass_user_data=True),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel_handler),
        ],
    )
    updater.dispatcher.add_handler(conv_handler)
    updater.dispatcher.add_handler(CommandHandler('start', start_buttons_handler))
    updater.dispatcher.add_handler(MessageHandler(Filters.all, echo_handler))

    # Начать бесконечную обработку входящих сообщений
    updater.start_polling()
    updater.idle()
    logger.info('Stopped Anketa-bot')


if __name__ == '__main__':
    main()
