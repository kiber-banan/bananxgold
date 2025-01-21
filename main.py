from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3

import cnf

TOKEN = cnf.token  # Замените на ваш токен
bot = TeleBot(TOKEN)
ADMIN_ID = 6336204836


def get_db_connection():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    return conn, c


def close_db_connection(conn):
    conn.close()


def create_table_if_not_exists():
    conn, c = get_db_connection()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY, name TEXT, balance REAL, gold INTEGER)''')
        conn.commit()
    finally:
        close_db_connection(conn)


def get_or_register_user(user_id, user_name):
    conn, c = get_db_connection()
    try:
        c.execute("SELECT * FROM users WHERE id=?", (user_id,))
        user = c.fetchone()
        if user is None:
            c.execute("INSERT INTO users (id, name, balance, gold) VALUES (?, ?, ?, ?)", (user_id, user_name, 0, 0))
            conn.commit()
            user = (user_id, user_name, 0, 0)
        return user
    finally:
        close_db_connection(conn)


def update_user(user_id, balance=None, gold=None):
    conn, c = get_db_connection()
    try:
        if balance is not None:
            c.execute("UPDATE users SET balance = ? WHERE id = ?", (balance, user_id))
        if gold is not None:
            c.execute("UPDATE users SET gold = ? WHERE id = ?", (gold, user_id))
        conn.commit()
    finally:
        close_db_connection(conn)


create_table_if_not_exists()


def main_menu(chat_id, is_admin=False):
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("Продать голду 💰", callback_data='sell'))
    keyboard.row(InlineKeyboardButton("Купить голду 🛒", callback_data='buy'))
    keyboard.row(InlineKeyboardButton("Профиль 👤", callback_data='profile'))
    if is_admin:
        keyboard.row(InlineKeyboardButton("Админ панель ⚙️", callback_data='admin_panel'))

    bot.send_message(chat_id, "Выберите действие:", reply_markup=keyboard)


def back_to_main_menu():
    return InlineKeyboardButton("В главное меню 🔙", callback_data='back')


def admin_panel(chat_id, page=0):
    items_per_page = 10
    conn, c = get_db_connection()
    try:
        c.execute("SELECT id, name, balance, gold FROM users LIMIT ? OFFSET ?", (items_per_page, page * items_per_page))
        users_list = c.fetchall()
        user_text = "\n".join(
            [f"ID: {user[0]}, Ник: @{user[1]}, Баланс: {user[2]}, Голда: {user[3]}" for user in users_list])

        keyboard = InlineKeyboardMarkup()
        if page > 0:
            keyboard.row(InlineKeyboardButton("Предыдущие 10 👈", callback_data=f'prev_{page}'))
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        if (page + 1) * items_per_page < total_users:
            keyboard.row(InlineKeyboardButton("Следующие 10 👉", callback_data=f'next_{page}'))
        keyboard.row(InlineKeyboardButton("Изменить баланс/голду 🔧", callback_data='change_balance_gold'))

        # Для каждого пользователя добавляем кнопку подтверждения пополнения
        for user in users_list:
            keyboard.row(InlineKeyboardButton(f"Подтвердить пополнение для @{user[1]} ✅",
                                              callback_data=f'deposit_confirm_{user[0]}_0'))

        keyboard.add(back_to_main_menu())

        try:
            # Попытка редактирования сообщения
            bot.edit_message_text(chat_id=chat_id, message_id=bot.last_update_id, text=f"Пользователи:\n{user_text}",
                                  reply_markup=keyboard)
        except Exception as e:
            # Если редактирование не удалось, отправляем новое сообщение
            bot.send_message(chat_id, f"Пользователи:\n{user_text}", reply_markup=keyboard)

    finally:
        close_db_connection(conn)


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        user = get_or_register_user(call.from_user.id, call.from_user.username)
        keyboard = InlineKeyboardMarkup().add(back_to_main_menu())

        if call.data == "back":
            main_menu(call.message.chat.id, call.from_user.id == ADMIN_ID)
        elif call.data == "sell":
            bot.answer_callback_query(call.id, "Функция продажи голды")
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Продажа голды пока не реализована. Ваша голда: {user[3]}", reply_markup=keyboard)
        elif call.data == "buy":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите количество голды для покупки:", reply_markup=keyboard)
            bot.register_next_step_handler(call.message, buy_gold)
        elif call.data == "profile":
            profile_keyboard = InlineKeyboardMarkup()
            profile_keyboard.row(InlineKeyboardButton("Вывести голду 🟡", callback_data='withdraw'))
            profile_keyboard.row(InlineKeyboardButton("Пополнить 🔄", callback_data='deposit'))
            profile_keyboard.add(back_to_main_menu())
            bot.answer_callback_query(call.id, "Профиль пользователя")
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=f"Профиль:\nID: {user[0]}\nИмя: @{user[1]}\nБаланс: {user[2]}\nГолда: {user[3]}",
                                  reply_markup=profile_keyboard)
        elif call.data == "withdraw":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите количество голды для вывода (не менее 100):")
            bot.register_next_step_handler(call.message, initiate_withdrawal)
        elif call.data == "deposit":
            start_deposit(call.message)
        elif call.data == "admin_panel":
            if call.from_user.id == ADMIN_ID:
                admin_panel(call.message.chat.id)
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к админ-панели.", show_alert=True)
        elif 'next_' in call.data or 'prev_' in call.data:
            page = int(call.data.split('_')[1]) + (1 if 'next' in call.data else -1)
            admin_panel(call.message.chat.id, page)
        elif call.data == "change_balance_gold":
            if call.from_user.id == ADMIN_ID:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                      text="Введите ID пользователя, затем новое значение баланса и голды (через пробел):",
                                      reply_markup=InlineKeyboardMarkup().add(back_to_main_menu()))
                bot.register_next_step_handler(call.message, handle_balance_gold_change)
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif "withdraw_done_" in call.data:
            user_id = int(call.data.split('_')[2])
            amount = int(call.data.split('_')[3])
            if call.from_user.id == ADMIN_ID:
                bot.send_message(user_id, "Ваша заявка на вывод голды успешно обработана.")
                # Голда уже была вычтена при запросе на вывод
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif "withdraw_cancel_" in call.data:
            user_id = int(call.data.split('_')[2])
            amount = int(call.data.split('_')[3])
            if call.from_user.id == ADMIN_ID:
                bot.send_message(user_id, "Ваша заявка на вывод голды отклонена.")
                update_user(user_id, gold=user[3] + amount)  # Возвращаем голду
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif call.data.startswith("deposit_confirm_"):
            user_id = int(call.data.split('_')[2])
            # Запрашиваем у админа ввести сумму пополнения
            if call.from_user.id == ADMIN_ID:
                bot.send_message(call.message.chat.id, f"Введите сумму пополнения для пользователя с ID {user_id}:")
                bot.register_next_step_handler(call.message, lambda message: confirm_deposit(user_id, message))
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Произошла ошибка: {str(e)}")
        main_menu(call.message.chat.id, call.from_user.id == ADMIN_ID)

def confirm_deposit(user_id, message):
    try:
        amount = float(message.text)
        update_user(user_id, balance=amount)
        bot.send_message(message.chat.id, f"Баланс пользователя с ID {user_id} пополнен на {amount}.")
        bot.send_message(user_id, f"Ваш баланс пополнен на {amount}.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректную сумму.")

def handle_balance_gold_change(message):
    try:
        user_id, new_balance, new_gold = message.text.split()
        user_id = int(user_id)
        new_balance = float(new_balance)
        new_gold = int(new_gold)
        update_user(user_id, balance=new_balance, gold=new_gold)
        bot.send_message(message.chat.id, f"Баланс и голда для пользователя с ID {user_id} обновлены.")
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат ввода. Пожалуйста, введите ID пользователя, новый баланс и голду через пробел.")
    main_menu(message.chat.id, message.from_user.id == ADMIN_ID)

def buy_gold(message):
    try:
        amount = int(message.text)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        if user[2] >= amount * 0.7:  # Проверка баланса
            new_balance = user[2] - amount * 0.7
            new_gold = user[3] + amount
            update_user(message.from_user.id, balance=new_balance, gold=new_gold)
            bot.send_message(message.chat.id, f"Покупка успешна! Ваш новый баланс: {new_balance:.2f}, голда: {new_gold}")
        else:
            bot.send_message(message.chat.id, "Недостаточно средств для покупки.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число.")
    main_menu(message.chat.id, message.from_user.id == ADMIN_ID)


def initiate_withdrawal(message):
    try:
        amount = int(message.text)
        if amount < 100:
            bot.send_message(message.chat.id, "Минимальная сумма для вывода 100 голды.")
        else:
            user = get_or_register_user(message.from_user.id, message.from_user.username)
            if user[3] >= amount:
                withdrawal_amount = amount / 0.8  # Так как после вычета 20% должно остаться amount голды
                new_balance = int(withdrawal_amount) + 0.52  # Округление до целого и добавление 52 копеек
                update_user(message.from_user.id, gold=user[3] - amount)  # Голда уже вычтена
                withdrawal_info = f"Пользователь @{user[1]} запрашивает вывод {amount} голды, сумма: {new_balance:.2f}"

                # Запрашиваем скриншот без вывода главного меню
                bot.send_message(message.from_user.id, "Пожалуйста, отправьте скриншот подтверждения платежа.")

                # Ждем ответа с изображением
                bot.register_next_step_handler(message, lambda msg: handle_screenshot(msg, withdrawal_info, amount))
            else:
                bot.send_message(message.chat.id, "Недостаточно голды на балансе.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число для вывода.")


def handle_screenshot(message, withdrawal_info, amount):
    if message.content_type == 'photo':
        # Получаем фото в наилучшем качестве
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Отправляем админу информацию о выводе с фото
        keyboard = InlineKeyboardMarkup()
        keyboard.row(InlineKeyboardButton("Выведено ✅", callback_data=f'withdraw_done_{message.from_user.id}_{amount}'))
        keyboard.row(
            InlineKeyboardButton("Отменить вывод ❌", callback_data=f'withdraw_cancel_{message.from_user.id}_{amount}'))

        bot.send_photo(ADMIN_ID, downloaded_file, caption=withdrawal_info, reply_markup=keyboard)
        bot.send_message(message.chat.id, "Заявка на вывод отправлена администратору.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот.")
        bot.register_next_step_handler(message, lambda msg: handle_screenshot(msg, withdrawal_info, amount))


@bot.message_handler(commands=['deposit'])
def start_deposit(message):
    bot.send_message(message.chat.id,
                     "Для пополнения баланса, пожалуйста, переведите средства (столько сколько хотите чтобы поплнили мин сумма 70р) на следующий ЮMoney кошелек:\n\n41001234567890\n\nПосле перевода отправьте скриншот платежа (на скрине должна быть сумма, время, дата, откуда отправляете и куда.")
    bot.register_next_step_handler(message, handle_deposit_screenshot)


def handle_deposit_screenshot(message):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Здесь вы должны вручную проверить сумму перевода по скриншоту
        bot.send_photo(ADMIN_ID, downloaded_file,
                       caption=f"Пользователь @{message.from_user.username} хочет пополнить баланс. Пожалуйста, подтвердите сумму.")
        bot.send_message(message.chat.id, "Скриншот отправлен администратору. Ожидайте подтверждения.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот платежа.")
        bot.register_next_step_handler(message, handle_deposit_screenshot)


@bot.message_handler(commands=['start'])
def start_message(message):
    try:
        bot.send_message(message.chat.id, "Добро пожаловать в бот для торговли голдой StandOff 2!")
        main_menu(message.chat.id, message.from_user.id == ADMIN_ID)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при старте: {str(e)}")


if __name__ == '__main__':
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка в основном цикле: {e}")