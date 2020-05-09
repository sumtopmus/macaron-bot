import os
import datetime
import io
import logging
import pickle

import numpy as np
import telegram.error
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler


fmt = '%Y-%m-%d %H:%M:%S'
token = os.getenv('MACARON_BOT_API_TOKEN')
admin_chat_id = int(os.getenv('TELEGRAM_ADMIN_ID'))

fail_chance = 0.05

PLACEHOLDERS = '🥂🍷🍸🍹🍾'
N_PH = len(PLACEHOLDERS)


IMAGES_EXIST = False
if os.path.exists('images'):
    IMAGES_EXIST = True


class EmptyBoxException(Exception):
    pass


class MacaronDB(dict):
    DB_PATH = 'data/db.pkl'
    NAMES_FILE = 'data/names.txt'

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
            self._names = [name.strip() for name in open(MacaronDB.NAMES_FILE, 'r').readlines()]
            self._available_names = np.ones(len(self.__names), dtype=bool)
            MacaronDB.__db = self

    def load(self):
        self.clear()
        if os.path.exists(MacaronDB.DB_PATH):
            with open(MacaronDB.DB_PATH, 'rb') as f:
                self.update(pickle.load(f))
        else:
            self.update({'users': {}, 'boxes': []})

    def save(self):
        print('{}: saving DB...'.format(datetime.datetime.now().strftime(fmt)))
        with open(MacaronDB.DB_PATH, 'wb') as f:
            pickle.dump(self, f)

    def create_unique_name(self, id):
        available_names_indices = self._available_names.nonzero()[0]
        if available_names_indices.size == 0:
            self._names = [name.strip() for name in open(MacaronDB.NAMES_FILE, 'r').readlines()]
            self._available_names = np.ones(len(self.__names), dtype=bool)
            available_names_indices = np.arange(len(self.__names))
        index = np.random.randint(available_names_indices.size)
        self._available_names[index] = False

        return '{0}_{1}'.format(MacaronDB.__names[index], id)

    def get_box_by_id(self, id):
        for box in self['boxes']:
            if box['id'] == id:
                return box
        return None

    def get_box_by_name(self, name):
        for index, box in enumerate(self['boxes']):
            if box['name'] == name:
                return index, box
        return None, None


def mb_to_text(box):
    text_array = np.empty_like(box, dtype=np.unicode_)
    for i in range(box.shape[0]):
        for j in range(box.shape[1]):
            if box[i, j]:
                text_array[i, j] = '🍪'
            else:
                text_array[i, j] = PLACEHOLDERS[np.random.randint(N_PH)]
    with io.StringIO() as s:
        np.savetxt(s, text_array, fmt='%s', delimiter='')
        text_box = s.getvalue()
    return text_box


def mb_left(box):
    return box.nonzero()[0].size


def mb_get(box):
    available_macarons = np.asarray(box.nonzero()).transpose()
    index = np.random.randint(available_macarons.shape[0])
    return available_macarons[index]


def mb_eat(box, loc):
    result = False
    if box[loc[0], loc[1]]:
        box[loc[0], loc[1]] = 0
        result = True
        MacaronDB.db().save()
    available_macarons = np.asarray(box.nonzero())
    if available_macarons.size == 0:
        raise EmptyBoxException()
    return result


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


def permission(update, context):
    query = update.callback_query
    query.answer()

    if query.data[0] == '1':
        data = query.data.split(':')
        eater_id, box_id = data[1], data[2]
        eater = MacaronDB.db()['users'][eater_id]
        eater['eats'] += [box_id]
        if eater['default'] is None:
            eater['default'] = box_id
        box = MacaronDB.db().get_box_by_id(box_id)
        box['eaters'] += eater_id
        MacaronDB.db().save()
        context.bot.send_message(chat_id=eater_id, text='Permission granted. Enjoy the macarons!')
    else:
        context.bot.send_message(chat_id=eater_id, text='DENIED! DENIED! DENIED! РУКИ ПРОЧЬ ОТ ЧУЖИХ МАКАРОН!')


def add_user(update, context):
    chat_id = update.effective_chat.id
    if chat_id not in MacaronDB.db()['users']:
        new_user = {
            'owns': [],
            'eats': [],
            'default': None
        }
        MacaronDB.db()['users'][chat_id] = new_user
        MacaronDB.db().save()


def start(update, context):
    chat_id = update.effective_chat.id
    context.bot.send_message(chat_id=chat_id, text='Congrats on buying that macaron box! Now you can start eating them. If you need my help, refer to the list of commands.')
    add_user(update, context)
    if IMAGES_EXIST:
        with open('images/macarons-1.gif', 'rb') as f:
            context.bot.send_animation(chat_id=chat_id, animation=f)


def add_box(update, context):
    add_user(update, context)
    chat_id = update.effective_chat.id
    try:
        dimensions = list(map(np.uint8, context.args))
        if len(dimensions) != 2:
            raise ValueError()
        if len(MacaronDB.db()['boxes']) > 0:
            new_box_id = MacaronDB.db()['boxes'][-1]['id'] + 1
        else:
            new_box_id = 0
        new_box = {
            'id': new_box_id,
            'name': MacaronDB.db().create_unique_name(new_box_id),
            'owner': chat_id,
            'eaters': [],
            'data': np.ones(dimensions, dtype=bool)
        }
        MacaronDB.db()['boxes'].append(new_box)
        MacaronDB.db()['users'][chat_id]['owns'].append(new_box_id)
        MacaronDB.db()['users'][chat_id]['default'] = new_box_id
        MacaronDB.db().save()
        context.bot.send_message(chat_id=chat_id, text='The box {} is set as default and ready to be eaten!'.format(new_box['name']))
        show_box(update, context)
    except Exception:
        context.bot.send_message(chat_id=chat_id, text='Something went wrong... Check your arguments.')


def request_share(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        if len(context.args) != 1:
            raise ValueError('Wrong arguments.')
        box_name = context.args[0]
        _, box = MacaronDB.db().get_box_by_name(box_name)

        if box:
            keyboard = [[InlineKeyboardButton('✔️', callback_data='1:{}:{}'.format(chat_id, box['id'])),
                         InlineKeyboardButton('❌', callback_data='0:{}:{}'.format(chat_id, box['id']))]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text('{} asks for the unlimited and unconditional control over your macarons in the {} box. Do you allow that?', reply_markup=reply_markup)


def set_default(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        if len(context.args) != 1:
            raise ValueError('Wrong arguments.')
        box_name = context.args[0]
        _, box = MacaronDB.db().get_box_by_name(box_name)
        if not box or (box['owner'] != chat_id and chat_id not in box['eaters']):
            context.bot.send_message(chat_id=chat_id, text="Can't find it.")
        else:
            user['default'] = box['id']
            context.bot.send_message(chat_id=chat_id, text="New default box is set.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")


def show_box(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        box = None
        if len(context.args) == 1:
            box_name = context.args[0]
            _, box = MacaronDB.db().get_box_by_name(box_name)
            if not box or (box['owner'] != chat_id and chat_id not in box['eaters']):
                context.bot.send_message(chat_id=chat_id, text="Can't find it.")
        else:
            box_id = user['default']
            if box_id is not None:
                box = MacaronDB.db().get_box_by_id(box_id)
            else:
                context.bot.send_message(chat_id=chat_id, text="You don't have default box set.")
        if box:
            text_box = mb_to_text(box['data'])
            context.bot.send_message(chat_id=chat_id, text=text_box)
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")


def show_name(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        box_id = user['default']
        if box_id is not None:
            box = MacaronDB.db().get_box_by_id(box_id)
            context.bot.send_message(chat_id=chat_id, text=box['name'])
        else:
            context.bot.send_message(chat_id=chat_id, text="You don't have default box set.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")


def show_all(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        n_box_ids = len(user['owns']) + len(user['eats'])
        if n_box_ids > 0:
            msg = ''
            if len(user['owns']) > 0:
                msg += 'Owner:\n'
                for box_id in user['owns']:
                    box = MacaronDB.db().get_box_by_id(box_id)
                    msg += '{0}: {1}x{2}, {3} left\n'.format(box['name'], box['data'].shape[0], box['data'].shape[1], mb_left(box['data']))
            if len(user['eats']) > 0:
                msg += 'Not an owner:\n'
                for box_id in user['eats']:
                    box = MacaronDB.db().get_box_by_id(box_id)
                    msg += '{0}: {1}x{2}, {3} left\n'.format(box['name'], box['data'].shape[0], box['data'].shape[1], mb_left(box['data']))
            context.bot.send_message(chat_id=chat_id, text=msg)
        else:
            context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")


def get_macaron(update, context):
    chat_id = update.effective_chat.id
    location = None
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        box_id = user['default']
        if box_id is not None:
            box = MacaronDB.db().get_box_by_id(box_id)['data']
            try:
                location = mb_get(box)
            except EmptyBoxException:
                context.bot.send_message(chat_id=chat_id, text='НАТАША, ВСТАВАЙ, ШПИНАТ ВСЁ СЪЕЛА!')
            else:
                context.bot.send_message(chat_id=chat_id, text='Picking a macaron at row {0} and column {1}.'.format(*((location + 1).tolist())))
                if np.random.random() < fail_chance:
                    '{}: FAIL!!!'.format(datetime.datetime.now().strftime(fmt))
                    context.bot.send_message(chat_id=chat_id, text='А НУ ПОЛОЖИ МАКАРОН НА МЕСТО!'.format(*(location.tolist())))
                    location = None
        else:
            context.bot.send_message(chat_id=chat_id, text="You don't have default box set.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")
    return location


def eat_macaron_by_loc(update, context, location):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        box_id = user['default']
        if box_id is not None:
            box = MacaronDB.db().get_box_by_id(box_id)['data']
            try:
                result = mb_eat(box, location)
            except EmptyBoxException:
                if IMAGES_EXIST:
                    with open('images/macarons-2.gif', 'rb') as f:
                        context.bot.send_animation(chat_id=chat_id, animation=f)
                context.bot.send_message(chat_id=chat_id, text='НУ СКОЛЬКО МОЖНО ЖРАТЬ???')
            except IndexError:
                context.bot.send_message(chat_id=chat_id, text='Something went wrong with those coordinates.')
            else:
                msg = 'Yummy-yummy.'
                if not result:
                    if IMAGES_EXIST:
                        with open('images/macaron-gone.gif', 'rb') as f:
                            context.bot.send_animation(chat_id=chat_id, animation=f)
                    msg = "МАКАРОН БЫЛ СЪЕДЕН ШПИНАТОМ."
                context.bot.send_message(chat_id=chat_id, text=msg)
        else:
            context.bot.send_message(chat_id=chat_id, text="You don't have any macaron boxes.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")
    return location


def eat_macaron(update, context):
    location = np.array(list(map(np.uint8, context.args))) - 1
    eat_macaron_by_loc(update, context, location)


def feed_macaron(update, context):
    location = get_macaron(update, context)
    if location is not None:
        eat_macaron_by_loc(update, context, location)


def remove_box(update, context):
    chat_id = update.effective_chat.id
    user = MacaronDB.db()['users'].get(chat_id, None)
    if user:
        box_name = context.args[0]
        index, box = MacaronDB.db().get_box_by_name(box_name)
        if box:
            if box['owner'] == chat_id:
                user['owns'].remove(box['id'])
                if user['default'] == box['id']:
                    user['default'] = None
                for eater_id in box['eaters']:
                    eater = MacaronDB.db()[eater_id]
                    eater['uses'].remove(box['id'])
                    if eater['default'] == box['id']:
                        eater['default'] = None
                MacaronDB.db()['boxes'].pop(index)
                MacaronDB.db().save()
                context.bot.send_message(chat_id=chat_id, text="The box was successfully removed.")
            else:
                context.bot.send_message(chat_id=chat_id, text="НЕ ТВОЯ, ПОЛОЖЬ НА МЕСТО!")
        else:
            context.bot.send_message(chat_id=chat_id, text="Can't find it.")
    else:
        context.bot.send_message(chat_id=chat_id, text="You are not registered with our exceptional service.")


def admin(update, context):
    chat_id = update.effective_chat.id
    if chat_id == admin_chat_id:
        context.bot.send_message(chat_id=chat_id, text=str(MacaronDB.db()))


def main():
    # load the base of macaron boxes
    MacaronDB.db()

    # set up logging
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

    # bot API
    updater = Updater(token, use_context=True)
    dispatcher = updater.dispatcher

    # bot commands
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('add', add_box))
    dispatcher.add_handler(CommandHandler('request', request_share))
    dispatcher.add_handler(CommandHandler('set_default', set_default))
    dispatcher.add_handler(CommandHandler('show', show_box))
    dispatcher.add_handler(CommandHandler('show_name', show_name))
    dispatcher.add_handler(CommandHandler('show_all', show_all))
    dispatcher.add_handler(CommandHandler('get', get_macaron))
    dispatcher.add_handler(CommandHandler('eat', eat_macaron))
    dispatcher.add_handler(CommandHandler('feed', feed_macaron))
    dispatcher.add_handler(CommandHandler('remove', remove_box))
    dispatcher.add_handler(CommandHandler('admin', admin))

    dispatcher.add_handler(CallbackQueryHandler(permission))
    dispatcher.add_error_handler(error)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()