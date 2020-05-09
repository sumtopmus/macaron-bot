import os
import datetime
import io
import logging
import pickle

import numpy as np
import telegram.error
from telegram.ext import Updater, CommandHandler


fmt = '%Y-%m-%d %H:%M:%S'
token = os.getenv('MACARON_BOT_API_TOKEN')

fail_chance = 0.05


class MacaronDB(dict):
    DB_PATH = 'data/db.pkl'
    __db = None

    @staticmethod
    def db():
        if MacaronDB.__db is None:
            MacaronDB()
        return MacaronDB.__db

    def __init__(self):
        if MacaronDB.__db is not None:
            raise Exception("This class is a singleton!")
        else:
            self.load()
            MacaronDB.__db = self

    def load(self):
        self.clear()
        if os.path.exists(MacaronDB.DB_PATH):
            with open(MacaronDB.DB_PATH, 'rb') as f:
                self.update({key: MacaronBox().from_numpy(value) for (key, value) in pickle.load(f).items()})

    def save(self):
        print('{}: saving DB...'.format(datetime.datetime.now().strftime(fmt)))
        with open(MacaronDB.DB_PATH, 'wb') as f:
            pickle.dump({key: value.box for (key, value) in self.items()}, f)


class MacaronBox():
    class EmptyBoxException(Exception):
        pass

    _placeholders = '🥂🍷🍸🍹🍾'
    _n_ph = len(_placeholders)

    def __init__(self, width=None, height=None):
        if width is not None and height is not None:
            self.set_box(width, height)

    def from_numpy(self, array):
        self.box = np.copy(array)
        return self

    def set_box(self, width, height):
        self.box = np.ones((height, width), dtype=bool)
        MacaronDB.db().save()

    def to_text(self):
        text_array = np.empty_like(self.box, dtype=np.unicode_)
        for i in range(self.box.shape[0]):
            for j in range(self.box.shape[1]):
                if self.box[i, j]:
                    text_array[i, j] = '🍪'
                else:
                    text_array[i, j] = MacaronBox._placeholders[np.random.randint(MacaronBox._n_ph)]
        with io.StringIO() as s:
            np.savetxt(s, text_array, fmt='%s', delimiter='')
            text_box = s.getvalue()
        return text_box

    def get_macaron(self):
        available_macarons = np.asarray(self.box.nonzero()).transpose()
        index = np.random.randint(available_macarons.shape[0])
        return available_macarons[index]

    def eat_macaron(self, loc):
        result = False
        if self.box[loc[0], loc[1]]:
            self.box[loc[0], loc[1]] = 0
            result = True
            MacaronDB.db().save()
        available_macarons = np.asarray(self.box.nonzero())
        if available_macarons.size == 0:
            raise MacaronBox.EmptyBoxException()
        return result

    def feed(self):
        loc = self.get_macaron().tolist()
        self.eat_macaron(loc[0], *loc)
        return loc


def error(update, context, error):
    logging.getLogger(__name__).warning('Update "%s" caused error "%s"', update, error)
    try:
        raise context.error
    except telegram.error.Unauthorized:
        # remove update.message.chat_id from conversation list
        pass
    except telegram.error.BadRequest:
        # handle malformed requests - read more below!
        pass
    except telegram.error.TimedOut:
        # handle slow connection problems
        pass
    except telegram.error.NetworkError:
        # handle other connection problems
        pass
    except telegram.error.ChatMigrated:
        # the chat_id of a group has changed, use e.new_chat_id instead
        pass
    except telegram.error.TelegramError:
        # handle all other telegram related errors
        pass


def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text='Congrats on buying that macaron box! Now you can start eating them. If you need my help, refer to the list of commands.')


def set_box(update, context):
    chat_id = update.effective_chat.id
    try:
        dimensions = list(map(np.uint8, context.args))
        if chat_id in MacaronDB.db():
            context.bot.send_message(chat_id=chat_id, text='You already have one box of the macarons.')
        else:
            MacaronDB.db()[chat_id] = MacaronBox(*dimensions)
            context.bot.send_message(chat_id=chat_id, text='The box is set!')
            show_box(update, context)
    except Exception:
        context.bot.send_message(chat_id=chat_id, text='The dimensions of the box should be two positive integers.')


def show_box(update, context):
    chat_id = update.effective_chat.id
    if chat_id in MacaronDB.db():
        text_box = MacaronDB.db()[chat_id].to_text()
        context.bot.send_message(chat_id=chat_id, text=text_box)
    else:
        context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")


def get_macaron(update, context):
    chat_id = update.effective_chat.id
    location = None
    if chat_id in MacaronDB.db():
        location = MacaronDB.db()[chat_id].get_macaron()
        context.bot.send_message(chat_id=chat_id, text='Picked a macaron at row {0} and column {1}.'.format(*((location + 1).tolist())))
        if np.random.random() < fail_chance:
            '{}: FAIL!!!'.format(datetime.datetime.now().strftime(fmt))
            context.bot.send_message(chat_id=chat_id, text='А НУ ПОЛОЖИ МАКАРОН НА МЕСТО!'.format(*(location.tolist())))
            location = None
    else:
        context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")
    return location


def eat_macaron_by_loc(update, context, location):
    chat_id = update.effective_chat.id
    if chat_id in MacaronDB.db():
        try:
            result = MacaronDB.db()[chat_id].eat_macaron(location)
        except MacaronBox.EmptyBoxException:
            context.bot.send_message(chat_id=chat_id, text='СКОЛЬКО МОЖНО ЖРАТЬ???')
        except IndexError:
            context.bot.send_message(chat_id=chat_id, text='Your box is not that big.')
        else:
            msg = 'Yummy-yummy.'
            if not result:
                msg = "МАКАРОН БЫЛ СЪЕДЕН ШПИНАТОМ."
            context.bot.send_message(chat_id=chat_id, text=msg)
    else:
        context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")


def eat_macaron(update, context):
    location = np.array(list(map(np.uint8, context.args))) - 1
    eat_macaron_by_loc(update, context, location)


def feed_macaron(update, context):
    location = get_macaron(update, context)
    if location is not None:
        eat_macaron_by_loc(update, context, location)


def reset(update, context):
    chat_id = update.effective_chat.id
    if chat_id not in MacaronDB.db():
        context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")
    else:
        MacaronDB.db().pop(chat_id)
        context.bot.send_message(chat_id=chat_id, text="You don't have a macaron box anymore.")


def main():
    # load the base of macaron boxes
    # MacaronDB.db().load()

    # set up logging
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # bot API
    updater = Updater(token, use_context=True)
    dispatcher = updater.dispatcher

    # bot commands
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('set', set_box))
    dispatcher.add_handler(CommandHandler('show', show_box))
    dispatcher.add_handler(CommandHandler('get', get_macaron))
    dispatcher.add_handler(CommandHandler('eat', eat_macaron))
    dispatcher.add_handler(CommandHandler('feed', feed_macaron))
    dispatcher.add_handler(CommandHandler('reset', reset))

    dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
