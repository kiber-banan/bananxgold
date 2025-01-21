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


def create_tables_if_not_exists():
    conn, c = get_db_connection()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY, name TEXT, balance REAL, gold INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      user_id INTEGER, 
                      request_type TEXT, 
                      amount REAL, 
                      status TEXT, 
                      details TEXT,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
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


def create_request(user_id, request_type, amount, details=''):
    conn, c = get_db_connection()
    try:
        c.execute("INSERT INTO requests (user_id, request_type, amount, status, details) VALUES (?, ?, ?, ?, ?)",
                  (user_id, request_type, amount, 'pending', details))
        conn.commit()
        return c.lastrowid
    finally:
        close_db_connection(conn)


def get_pending_requests():
    conn, c = get_db_connection()
    try:
        c.execute("SELECT id, user_id, request_type, amount, details FROM requests WHERE status = 'pending'")
        return c.fetchall()
    finally:
        close_db_connection(conn)


def update_request_status(request_id, status):
    conn, c = get_db_connection()
    try:
        c.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
    finally:
        close_db_connection(conn)


create_tables_if_not_exists()


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

        # Добавляем обработку заявок на пополнение
        c.execute("SELECT id, user_id, amount FROM requests WHERE request_type = 'deposit_gold' AND status = 'pending'")
        pending_deposits = c.fetchall()
        for deposit in pending_deposits:
            keyboard.row(
                InlineKeyboardButton(f"Подтвердить пополнение {deposit[2]} голды для @{deposit[1]} ✅",
                                     callback_data=f'confirm_deposit_gold_{deposit[0]}'),
                InlineKeyboardButton(f"Отклонить пополнение {deposit[2]} голды для @{deposit[1]} ❌",
                                     callback_data=f'reject_deposit_gold_{deposit[0]}')
            )

        # Продажа голды
        c.execute(
            "SELECT id, user_id, amount, details FROM requests WHERE request_type = 'sell_gold' AND status = 'pending'")
        pending_sales = c.fetchall()
        for sale in pending_sales:
            keyboard.row(
                InlineKeyboardButton(f"Подтвердить продажу {sale[2]} голды от @{sale[1]} ✅",
                                     callback_data=f'confirm_sale_{sale[0]}'),
                InlineKeyboardButton(f"Отклонить продажу {sale[2]} голды от @{sale[1]} ❌",
                                     callback_data=f'reject_sale_{sale[0]}')
            )

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
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите количество голды для продажи:", reply_markup=keyboard)
            bot.register_next_step_handler(call.message, sell_gold)
        elif call.data == "buy":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите количество голды для покупки:", reply_markup=keyboard)
            bot.register_next_step_handler(call.message, buy_gold)
        elif call.data == "profile":
            profile_keyboard = InlineKeyboardMarkup()
            profile_keyboard.row(InlineKeyboardButton("Вывести голду 💸", callback_data='withdraw_gold'))
            profile_keyboard.row(InlineKeyboardButton("Вывести деньги 💳", callback_data='withdraw_money'))
            profile_keyboard.row(InlineKeyboardButton("Пополнить баланс 🔄", callback_data='deposit'))
            profile_keyboard.add(back_to_main_menu())
            bot.answer_callback_query(call.id, "Профиль пользователя")
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text=f"Профиль:\nID: {user[0]}\nИмя: @{user[1]}\nБаланс: {user[2]}\nГолда: {user[3]}",
                                  reply_markup=profile_keyboard)
        elif call.data == "withdraw_gold":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите количество голды для вывода (не менее 100):")
            bot.register_next_step_handler(call.message, initiate_withdrawal_gold)
        elif call.data == "withdraw_money":
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="Введите сумму и номер телефона для вывода (через пробел, сумма не менее 100):")
            bot.register_next_step_handler(call.message, initiate_withdrawal_money)
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
        elif call.data.startswith("handle_request_"):
            request_id, action = call.data.split('_')[2:]
            if call.from_user.id == ADMIN_ID:
                handle_request(request_id, action, call)
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif call.data.startswith("buy_skin_"):
            buyer_id, request_id, sale_amount = call.data.split('_')[2:]
            update_user(int(buyer_id), balance=float(sale_amount))
            bot.send_message(int(buyer_id), f"Покупка скина подтверждена. На ваш баланс зачислено {sale_amount:.2f}.")
            update_request_status(request_id, 'completed')
            bot.send_message(call.message.chat.id, "Покупка скина подтверждена, баланс обновлён.")
            admin_panel(call.message.chat.id)  # Обновляем админ панель
        elif call.data.startswith("cancel_skin_sale_"):
            seller_id, request_id = call.data.split('_')[3:]
            bot.send_message(int(seller_id), "Продажа скина отменена.")
            update_request_status(request_id, 'cancelled')
            bot.send_message(call.message.chat.id, "Продажа скина отменена.")
            admin_panel(call.message.chat.id)  # Обновляем админ панель
        elif call.data.startswith("confirm_sale_"):
            request_id = call.data.split('_')[2]
            if call.from_user.id == ADMIN_ID:
                bot.send_message(call.message.chat.id, "Отправьте скриншот скина.")
                bot.register_next_step_handler(call.message, lambda msg: handle_admin_screenshot(msg, request_id))
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif call.data.startswith("reject_sale_"):
            request_id = call.data.split('_')[2]
            if call.from_user.id == ADMIN_ID:
                update_request_status(request_id, 'rejected')
                bot.send_message(call.message.chat.id, "Заявка на продажу отклонена.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif call.data.startswith("finalize_purchase_"):
            buyer_id, request_id, sale_amount = call.data.split('_')[2:]
            if call.from_user.id == ADMIN_ID:
                update_user(int(buyer_id), balance=float(sale_amount))
                update_request_status(request_id, 'completed')
                bot.send_message(int(buyer_id), f"Покупка скина подтверждена. На ваш баланс зачислено {sale_amount:.2f}.")
                bot.send_message(call.message.chat.id, "Покупка подтверждена, баланс обновлён.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

        elif call.data.startswith("dispute_purchase_"):
            request_id = call.data.split('_')[2]
            if call.from_user.id == ADMIN_ID:
                update_request_status(request_id, 'disputed')
                bot.send_message(call.message.chat.id, "Покупка оспорена.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
        elif call.data.startswith("confirm_purchase_"):
            buyer_id, request_id, sale_amount = call.data.split('_')[2:]
            bot.send_message(call.message.chat.id, "Отправьте скриншот купленного скина.")
            bot.register_next_step_handler(call.message, lambda msg: handle_buyer_screenshot(msg, buyer_id, request_id, sale_amount))

        elif call.data.startswith("finalize_purchase_"):
            buyer_id, request_id, sale_amount = call.data.split('_')[2:]
            if call.from_user.id == ADMIN_ID:
                update_user(int(buyer_id), balance=float(sale_amount))
                update_request_status(request_id, 'completed')
                bot.send_message(int(buyer_id),
                                 f"Покупка скина подтверждена. На ваш баланс зачислено {sale_amount:.2f}.")
                bot.send_message(call.message.chat.id, "Покупка подтверждена, баланс обновлён.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

        elif call.data.startswith("dispute_purchase_"):
            request_id = call.data.split('_')[2]
            if call.from_user.id == ADMIN_ID:
                update_request_status(request_id, 'disputed')
                bot.send_message(call.message.chat.id, "Покупка оспорена.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

        elif call.data.startswith("confirm_deposit_gold_"):
            request_id = call.data.split('_')[3]
            if call.from_user.id == ADMIN_ID:
                bot.send_message(call.message.chat.id, "Введите количество голды для зачисления:")
                bot.register_next_step_handler(call.message, lambda msg: finalize_deposit_gold(msg, request_id))
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

        elif call.data.startswith("reject_deposit_gold_"):
            request_id = call.data.split('_')[3]
            if call.from_user.id == ADMIN_ID:
                update_request_status(request_id, 'rejected')
                bot.send_message(call.message.chat.id, "Заявка на пополнение голды отклонена.")
                admin_panel(call.message.chat.id)  # Обновляем админ панель
            else:
                bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Произошла ошибка: {str(e)}")
        main_menu(call.message.chat.id, call.from_user.id == ADMIN_ID)


def handle_balance_gold_change(message):
    try:
        user_id, new_balance, new_gold = message.text.split()
        user_id = int(user_id)
        new_balance = float(new_balance)
        new_gold = int(new_gold)
        update_user(user_id, balance=new_balance, gold=new_gold)
        bot.send_message(message.chat.id, f"Баланс и голда для пользователя с ID {user_id} обновлены.")
    except ValueError:
        bot.send_message(message.chat.id,
                         "Неверный формат ввода. Пожалуйста, введите ID пользователя, новый баланс и голду через пробел.")
    main_menu(message.chat.id, message.from_user.id == ADMIN_ID)


def buy_gold(message):
    try:
        amount = int(message.text)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        if user[2] >= amount * 0.7:  # Проверка баланса
            new_balance = user[2] - amount * 0.7
            new_gold = user[3] + amount
            update_user(message.from_user.id, balance=new_balance, gold=new_gold)
            bot.send_message(message.chat.id,
                             f"Покупка успешна! Ваш новый баланс: {new_balance:.2f}, голда: {new_gold}")
        else:
            bot.send_message(message.chat.id, "Недостаточно средств для покупки.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число.")
    main_menu(message.chat.id, message.from_user.id == ADMIN_ID)


def initiate_withdrawal_gold(message):
    try:
        amount = int(message.text)
        if amount < 100:
            bot.send_message(message.chat.id, "Минимальная сумма для вывода 100 голды.")
        else:
            user = get_or_register_user(message.from_user.id, message.from_user.username)
            if user[3] >= amount:
                withdrawal_amount = amount / 0.8  # Так как после вычета 20% должно остаться amount голды
                new_balance = int(withdrawal_amount) + 0.52  # Округление до целого и добавление 52 копеек
                update_user(message.from_user.id, gold=user[3] - amount)
                request_id = create_request(message.from_user.id, 'withdraw_gold', amount, f"Сумма: {new_balance:.2f}")
                withdrawal_info = f"Пользователь @{user[1]} запрашивает вывод {amount} голды, сумма: {new_balance:.2f}"

                bot.send_message(message.from_user.id, "Пожалуйста, отправьте скриншот подтверждения платежа.")
                bot.register_next_step_handler(message, lambda msg: handle_screenshot(msg, withdrawal_info, request_id, amount))
            else:
                bot.send_message(message.chat.id, "Недостаточно голды на балансе.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число для вывода.")


def initiate_withdrawal_money(message):
    try:
        amount, phone = message.text.split()
        amount = float(amount)
        if amount < 100:
            bot.send_message(message.chat.id, "Минимальная сумма для вывода 100 рублей.")
        else:
            user = get_or_register_user(message.from_user.id, message.from_user.username)
            if user[2] >= amount:
                update_user(message.from_user.id, balance=user[2] - amount)  # Сразу списываем сумму
                request_id = create_request(message.from_user.id, 'withdraw_money', amount, f"Номер телефона: {phone}")
                withdrawal_info = f"Пользователь @{user[1]} запрашивает вывод {amount} руб на номер {phone}"
                bot.send_message(ADMIN_ID, withdrawal_info, reply_markup=InlineKeyboardMarkup().row(
                    InlineKeyboardButton("Выведено ✅", callback_data=f'handle_request_{request_id}_accept'),
                    InlineKeyboardButton("Отменить вывод ❌", callback_data=f'handle_request_{request_id}_reject')
                ))
                bot.send_message(message.chat.id, "Заявка на вывод отправлена администратору.")
            else:
                bot.send_message(message.chat.id, "Недостаточно средств на балансе.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректные данные для вывода (сумма и номер телефона через пробел).")


def sell_gold(message):
    try:
        amount = int(message.text)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        # Сумма продажи после комиссии
        sale_amount = amount * 0.8
        request_id = create_request(message.from_user.id, 'sell_gold', amount, f"Сумма продажи: {sale_amount:.2f}")
        bot.send_message(message.chat.id, f"Вы продаете {amount} голды. Покупатель должен купить скин за {sale_amount:.2f}. Отправьте админу скриншот выставленного скина.")
        bot.register_next_step_handler(message, lambda msg: handle_skin_sale(msg, request_id, sale_amount, amount))
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число голды для продажи.")

def handle_skin_sale(message, request_id, sale_amount, amount):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        sale_info = f"Пользователь @{user[1]} продает {amount} голды. Сумма продажи: {sale_amount:.2f}"
        bot.send_photo(ADMIN_ID, downloaded_file, caption=sale_info, reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Подтвердить продажу ✅", callback_data=f'confirm_sale_{request_id}'),
            InlineKeyboardButton("Отклонить продажу ❌", callback_data=f'reject_sale_{request_id}')
        ))
        bot.send_message(message.chat.id, "Заявка на продажу голды отправлена администратору.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот скина.")
        bot.register_next_step_handler(message, lambda msg: handle_skin_sale(msg, request_id, sale_amount, amount))


def handle_accept_request(request_id, call):
    conn, c = get_db_connection()
    try:
        c.execute("SELECT user_id, request_type, amount, details FROM requests WHERE id = ?", (request_id,))
        request = c.fetchone()
        if request:
            user_id, request_type, amount, details = request
            if request_type == 'withdraw_gold':
                bot.send_message(user_id, "Ваша заявка на вывод голды успешно обработана.")
            elif request_type == 'withdraw_money':
                bot.send_message(user_id, "Ваша заявка на вывод денег успешно обработана.")
                # Здесь должно быть реальное выполнение перевода
            elif request_type == 'sell_gold':
                bot.send_message(user_id, "Ваша заявка на продажу голды принята. Ожидайте скриншот скина.")
                sale_amount = float(details.split(',')[1].split(':')[1].strip())
                bot.send_message(call.message.chat.id, "Запросите скриншот скина у продавца.")
                bot.register_next_step_handler(call.message,
                                               lambda msg: handle_skin_screenshot(msg, user_id, request_id,
                                                                                  sale_amount))

            update_request_status(request_id, 'accepted')
            admin_panel(call.message.chat.id)  # Обновляем админ панель
    finally:
        close_db_connection(conn)


def handle_request(request_id, action, call):
    if action == 'accept':
        handle_accept_request(request_id, call)
    elif action == 'reject':
        handle_reject_request(request_id, call)

def handle_admin_screenshot(message, request_id):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        conn, c = get_db_connection()
        try:
            c.execute("SELECT user_id, amount, details FROM requests WHERE id = ?", (request_id,))
            request = c.fetchone()
            if request:
                user_id, amount, details = request
                sale_amount = float(details.split(':')[1].strip())
                bot.send_photo(user_id, downloaded_file, caption=f"Проверьте, пожалуйста, этот скин. Если он соответствует заявке, нажмите 'Купил скин'.")
                bot.send_message(user_id, "Скин готов к покупке", reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("Купил скин ✅", callback_data=f'confirm_purchase_{user_id}_{request_id}_{sale_amount}'),
                    InlineKeyboardButton("Отменить покупку ❌", callback_data=f'cancel_purchase_{request_id}')))
        finally:
            close_db_connection(conn)
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот скина.")
        bot.register_next_step_handler(message, lambda msg: handle_admin_screenshot(msg, request_id))

def handle_buyer_screenshot(message, buyer_id, request_id, sale_amount):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_photo(ADMIN_ID, downloaded_file, caption=f"Покупатель подтвердил покупку скина за {sale_amount:.2f}.", reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Подтвердить покупку ✅", callback_data=f'finalize_purchase_{buyer_id}_{request_id}_{sale_amount}'),
            InlineKeyboardButton("Отклонить покупку ❌", callback_data=f'dispute_purchase_{request_id}')
        ))
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот купленного скина.")
        bot.register_next_step_handler(message, lambda msg: handle_buyer_screenshot(msg, buyer_id, request_id, sale_amount))



def handle_reject_request(request_id, call):
    conn, c = get_db_connection()
    try:
        c.execute("SELECT user_id, request_type FROM requests WHERE id = ?", (request_id,))
        request = c.fetchone()
        if request:
            user_id, request_type = request
            if request_type == 'withdraw_gold':
                bot.send_message(user_id, "Ваша заявка на вывод голды отклонена.")
            elif request_type == 'withdraw_money':
                bot.send_message(user_id, "Ваша заявка на вывод денег отклонена.")
            elif request_type == 'sell_gold':
                bot.send_message(user_id, "Ваша заявка на продажу голды отклонена.")

            update_request_status(request_id, 'rejected')
            admin_panel(call.message.chat.id)  # Обновляем админ панель
    finally:
        close_db_connection(conn)


def start_deposit(message):
    bot.send_message(message.chat.id,
                     "Для пополнения баланса, пожалуйста, переведите средства на следующий ЮMoney кошелек:\n\n**41001234567890**\n\nПосле перевода отправьте скриншот платежа.")
    bot.register_next_step_handler(message, handle_deposit_screenshot)


def handle_deposit_screenshot(message):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        bot.send_photo(ADMIN_ID, downloaded_file,
                       caption=f"Пользователь @{user[1]} хочет пополнить баланс. Пожалуйста, подтвердите сумму.")
        bot.send_message(message.chat.id, "Скриншот отправлен администратору. Ожидайте подтверждения.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот платежа.")
        bot.register_next_step_handler(message, handle_deposit_screenshot)


def handle_skin_screenshot(message, user_id, request_id, sale_amount):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_photo(user_id, downloaded_file, caption="Проверьте, пожалуйста, этот скин. Если он соответствует заявке, нажмите 'Купил скин'.")
        bot.send_message(user_id, "Скин готов к покупке", reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Купил скин ✅", callback_data=f'buy_skin_{message.from_user.id}_{request_id}_{sale_amount}'),
            InlineKeyboardButton("Отменить вывод ❌", callback_data=f'cancel_skin_sale_{message.from_user.id}_{request_id}')
        ))
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот скина.")
        bot.register_next_step_handler(message, lambda msg: handle_skin_screenshot(msg, user_id, request_id, sale_amount))

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
                update_user(message.from_user.id, gold=user[3] - amount)
                request_id = create_request(message.from_user.id, 'withdraw_gold', amount, f"Сумма: {new_balance:.2f}")
                withdrawal_info = f"Пользователь @{user[1]} запрашивает вывод {amount} голды, сумма: {new_balance:.2f}"

                bot.send_message(message.from_user.id, "Пожалуйста, отправьте скриншот подтверждения платежа.")
                bot.register_next_step_handler(message,
                                               lambda msg: handle_screenshot(msg, withdrawal_info, request_id, amount))
            else:
                bot.send_message(message.chat.id, "Недостаточно голды на балансе.")
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число для вывода.")


def handle_screenshot(message, withdrawal_info, request_id, amount):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        bot.send_photo(ADMIN_ID, downloaded_file, caption=withdrawal_info, reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Выведено ✅", callback_data=f'handle_request_{request_id}_accept'),
            InlineKeyboardButton("Отменить вывод ❌", callback_data=f'handle_request_{request_id}_reject')
        ))
        bot.send_message(message.chat.id, "Заявка на вывод отправлена администратору.")
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот.")
        bot.register_next_step_handler(message, lambda msg: handle_screenshot(msg, withdrawal_info, request_id, amount))

def handle_buyer_screenshot(message, buyer_id, request_id, sale_amount):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_photo(ADMIN_ID, downloaded_file, caption=f"Покупатель @{message.from_user.username} подтвердил покупку скина за {sale_amount:.2f}.", reply_markup=InlineKeyboardMarkup().row(
            InlineKeyboardButton("Подтвердить покупку ✅", callback_data=f'finalize_purchase_{buyer_id}_{request_id}_{sale_amount}'),
            InlineKeyboardButton("Отклонить покупку ❌", callback_data=f'dispute_purchase_{request_id}')
        ))
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот купленного скина.")
        bot.register_next_step_handler(message, lambda msg: handle_buyer_screenshot(msg, buyer_id, request_id, sale_amount))


def start_deposit_gold(message):
    bot.send_message(message.chat.id, "Для пополнения голды, пожалуйста, переведите средства на следующий ЮMoney кошелек:\n\n41001234567890\n\nПосле перевода отправьте скриншот платежа.")
    bot.register_next_step_handler(message, handle_deposit_gold_screenshot)

def handle_deposit_gold_screenshot(message):
    if message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user = get_or_register_user(message.from_user.id, message.from_user.username)
        bot.send_photo(ADMIN_ID, downloaded_file, caption=f"Пользователь @{user[1]} хочет пополнить голду. Пожалуйста, подтвердите сумму.")
        bot.send_message(message.chat.id, "Скриншот отправлен администратору. Ожидайте подтверждения.")
        create_request(message.from_user.id, 'deposit_gold', 0, 'Ожидает подтверждения суммы')
    else:
        bot.send_message(message.chat.id, "Пожалуйста, отправьте скриншот платежа.")
        bot.register_next_step_handler(message, handle_deposit_gold_screenshot)

def finalize_deposit_gold(message, request_id):
    try:
        amount = int(message.text)
        conn, c = get_db_connection()
        try:
            c.execute("UPDATE requests SET amount = ?, details = ? WHERE id = ?", (amount, f"Зачислено {amount} голды", request_id))
            c.execute("SELECT user_id FROM requests WHERE id = ?", (request_id,))
            user_id = c.fetchone()[0]
            update_user(user_id, gold=amount)
            update_request_status(request_id, 'completed')
        finally:
            close_db_connection(conn)
        bot.send_message(user_id, f"Ваш баланс голды пополнен на {amount}.")
        bot.send_message(message.chat.id, f"Пополнение на {amount} голды подтверждено.")
        admin_panel(message.chat.id)  # Обновляем админ панель
    except ValueError:
        bot.send_message(message.chat.id, "Введите корректное число голды для зачисления.")

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
