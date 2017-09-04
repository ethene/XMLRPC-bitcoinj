#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

# TODO: imports
import calendar
import logging
import shutil
import traceback
import xmlrpc.client
from datetime import datetime

import coloredlogs
import matplotlib as mpl
import pandas as pd
import psutil
from sqlalchemy import (create_engine, Table, Column, Integer, BigInteger, ForeignKey, DateTime,
                        String, Boolean, MetaData, desc, func)
from sqlalchemy.sql import select
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, \
    InlineKeyboardMarkup
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler, RegexHandler, CallbackQueryHandler
from telegram.ext import Updater

mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys

sys.path.insert(0, '../BitMEX-trader/db/')
from settings import MYSQL_CONNECTION, TELEGRAM_BOT_TOKEN, BASE_URL
from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler
from bitmex import BitMEX
from extra_settings import B_KEY, B_SECRET, POLO_ADDRESS


def error_callback(bot, update, error):
    try:
        raise error
    except TelegramError as e:
        logger.error(e)
        logger.error(traceback.format_exc())


XMLRPCServer = xmlrpc.client.ServerProxy('http://localhost:8000')

actions_table = 'telegram_actions'
log_table = 'telegram_log'
mail_table = 'telegram_mail'
useraccounts_table = 'telegram_useraccounts'
positions_table = 'mercury_positions'
balance_table = 'mercury_balance'
balance_diff_table = 'avg_balance_difference'
pic_folder = './pictures'
pic_1_filename = 'balance.png'
pic_2_filename = 'cumulative.png'
#
poloniex_address = 'mwCwTceJvYV27KXBc3NJZys6CjsgsoeHmf'
bitmex_address = 'mwCwTceJvYV27KXBc3NJZys6CjsgsoeHmf'
TELEGRAM_CHANNEL_NAME = '-1001106984254'

XBt_TO_XBT = 100000000

level = logging.DEBUG
script_name = 'telegram.bot'

db_engine = create_engine(MYSQL_CONNECTION, echo=False)
metadata = MetaData(db_engine)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', level=level)
logger = logging.getLogger(script_name)
log_filename = './log/' + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
coloredlogs.install(level=level)

bitmex = BitMEX(apiKey=B_KEY, apiSecret=B_SECRET, base_url=BASE_URL, logger=logger)

# last command to perform with OTP auth
last_command = None
last_args = None

if not db_engine.dialect.has_table(db_engine, useraccounts_table):
    logger.warn("user accounts table does not exist")
    # Create a table with the appropriate Columns
    useraccounts = Table(useraccounts_table, metadata,
                         Column('ID', Integer, primary_key=True, nullable=False),
                         Column('firstname', String(255)), Column('lastname', String(255)),
                         Column('username', String(255)), Column('isadmin', Boolean(), default=False),
                         Column('address', String(40)),
                         Column('withdrawn', BigInteger(), default=0))
    # Implement the creation
    metadata.create_all()
else:
    useraccounts = Table(useraccounts_table, metadata, autoload=True)

if not db_engine.dialect.has_table(db_engine, positions_table):
    logger.warn("positions table does not exist")
    # Create a table with the appropriate Columns
    positions = Table(positions_table, metadata,
                      Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                      Column('position', BigInteger(), default=0),
                      Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()))
    # Implement the creation
    metadata.create_all()
else:
    positions = Table(positions_table, metadata, autoload=True)

if not db_engine.dialect.has_table(db_engine, actions_table):
    logger.warn("actions table does not exist")
    # Create a table with the appropriate Columns
    actions = Table(actions_table, metadata,
                    Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                    Column('action', String(255)), Column('approved', Boolean(), default=False),
                    Column('args', String(255)),
                    Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()),
                    Column('ID', Integer, primary_key=True, autoincrement=True)
                    )
    # Implement the creation
    metadata.create_all()
else:
    actions = Table(actions_table, metadata, autoload=True)

if not db_engine.dialect.has_table(db_engine, log_table):
    logger.warn("log table does not exist")
    # Create a table with the appropriate Columns
    log = Table(log_table, metadata,
                Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                Column('log', String(1024)),
                Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()),
                Column('ID', Integer, primary_key=True, autoincrement=True)
                )
    # Implement the creation
    metadata.create_all()
else:
    log = Table(log_table, metadata, autoload=True)

if not db_engine.dialect.has_table(db_engine, mail_table):
    logger.warn("mail table does not exist")
    # Create a table with the appropriate Columns
    mail = Table(mail_table, metadata,
                 Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                 Column('mail', String(1024)), Column('read', Boolean(), default=False),
                 Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()),
                 Column('ID', Integer, primary_key=True, autoincrement=True))
    # Implement the creation
    metadata.create_all()
else:
    mail = Table(mail_table, metadata, autoload=True)

updater = Updater(token=TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher


#
# Helpers
#

def getUTCtime():
    d = datetime.utcnow()
    unixtime = calendar.timegm(d.utctimetuple())
    return unixtime * 1000


# TODO: help
def bot_help(bot, update):
    message = "This is your personal interface to the *Mercury* crypto hedge fund\n"
    message += "You can use your personal wallet\nto put _BTC_ funds under portfolio management\n"
    message += "And withdraw them back with profit\nwhen position is ready to be closed\n"
    message += "You can check fund performance /statistics\n"
    message += "To participate, you need to top up your account\n"
    message += "by sending funds to your personal wallet _BTC_ address\n"
    message += "Then you can /invest to open your personal portfolio\n"
    message += "or /contact administration at any time\n"
    message += "When you have /portfolio you can check its performance as well\n"
    message += "Requesting to /close your portfolio will return your funds when the position is ready\n"
    # message += "And then you can ask to /withdwraw the funds when they are back\n"
    bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown')


# TODO: update
def update_main(bot, update):
    query = update.callback_query
    bot.answerCallbackQuery(callback_query_id=query.id, text="~~~Updated~~~")
    chat_id = query.message.chat_id
    address, isadmin, keyboard, message = StartMessage(bot, update)

    bot.edit_message_text(text=message,
                          chat_id=chat_id,
                          message_id=query.message.message_id,
                          reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# TODO: start
def start(bot, update):
    address, isadmin, keyboard, message = StartMessage(bot, update)

    if isadmin:
        keyboard += [[InlineKeyboardButton(text="admin functions", callback_data="/admin")]]

    logger.debug("msg: %s" % message)
    if message and len(keyboard) > 0:
        bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                         reply_markup=ReplyKeyboardRemove())
        if address:
            bot.send_message(chat_id=update.message.chat_id, text="*%s*" % address, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


def StartMessage(bot, update):
    with db_engine.connect() as con:
        userfrom = update.effective_user
        logger.debug("userfrom : %s" % userfrom)
        userID = userfrom.id
        firstname = userfrom.first_name
        lastname = userfrom.last_name
        username = userfrom.username

        stm = select([useraccounts]).where(useraccounts.c.ID == userID)
        rs = con.execute(stm)
        response = rs.fetchall()
        isadmin = False
        message = None
        keyboard = []
        address = None

        # TODO: new user
        if len(response) == 0:
            # user not found in db
            logger.debug("user not found in db, creating new user %s" % userfrom)
            try:
                address = XMLRPCServer.getNewAddress()
                ins = useraccounts.insert().values(ID=userID, firstname=firstname, lastname=lastname, username=username,
                                                   isadmin=False, address=address, withdrawn=0)
                con.execute(ins)
                select_positions = select([positions]).order_by(desc(positions.c.timestamp))
                rs = con.execute(select_positions).fetchall()
                max_pos_timestamp = rs[0].timestamp
                ins = positions.insert().values(userID=userID, position=0, timestamp=max_pos_timestamp)
                con.execute(ins)
                ins = log.insert().values(userID=userID, log='new user created % s' % username,
                                          timestamp=datetime.utcnow())
                con.execute(ins)
                message = "Hello, *%s*!\nThis is your personal interface to the *Mercury* crypto hedge fund\n" % (
                    username)
                message += "Your new account has just created\n"
                message += "To see the fund performance use /statistics\n"
                # message += "or use /help for full command list\n"
                message += "Your wallet is yet empty.\nPlease top-up your account\n"
                message += "by making a transfer to your main wallet to your address as below:\n"
                message += "*%s*\n" % address
                keyboard += [[InlineKeyboardButton(text="update", callback_data="/refresh")],
                             [InlineKeyboardButton(text="view fund performance", callback_data='/statistics')]]
                msg = "New user created [%s](tg://user?id=%s)\n" % (userID, userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
            except:
                logger.error(traceback.format_exc())
                log_event = 'failed to create user'
                log_record(log_event, update)
                message = "Failed to create new user"
                keyboard += [[InlineKeyboardButton(text="contact support", callback_data="/contact")]]
                msg = "failed to create user [%s](tg://user?id=%s)\n" % (userID, userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
        # TODO: existing user
        else:
            # user found in DB
            for u in response:
                isadmin = u.isadmin == 1
                logger.debug("user found in db, admin: %s" % isadmin)

            ins = log.insert().values(userID=userID, log='user /start', timestamp=datetime.utcnow())
            con.execute(ins)

            if isadmin:
                message = "Hello, admin *%s*!\nWelcome back to use the bot\n" % (username)
            else:
                message = "Hello, *%s*!\nWelcome back to Mercury crypto hedge fund\n" % (username)

            select_positions = select([positions]).where(positions.c.userID == userID).order_by(
                desc(positions.c.timestamp))
            rs = con.execute(select_positions)
            response2 = rs.fetchall()
            address = response[0].address
            position = response2[0].position
            withdrawn = response[0].withdrawn

            try:
                logger.debug("address %s" % (address))
                balance = XMLRPCServer.getInputValue(address) - withdrawn
                logger.debug("balance %.8f" % (balance / 1e8))
                unconfirmedTXs = XMLRPCServer.getUnconfirmedTransactions(address)
                logger.debug("unconfirmed: %s" % unconfirmedTXs)
                message += "Would you like to see our performance /statistics\n"
                # message += "or read /help for full command list?\n"
                balance = int(balance) / 1e8
                if balance == 0:
                    message += "Your wallet is yet empty\nPlease top-up your account\n"
                    message += "by making a transfer to your main wallet address\n"
                    # keyboard = [[KeyboardButton(text="/start")], [KeyboardButton(text="/statistics")],
                    #            [KeyboardButton(text="/help")]]
                    keyboard += [[InlineKeyboardButton(text="update", callback_data="/refresh")],
                                 [InlineKeyboardButton(text="view fund performance", callback_data='/statistics')]]
                else:
                    message += "Your balance is *%.8f* BTC\n" % (balance)

                new_mail = select([mail]).where(mail.c.userID == userID).where(mail.c.read == False).order_by(
                    desc(mail.c.timestamp))
                mail_rs = con.execute(new_mail).fetchall()
                for m in mail_rs:
                    message += "*new mail:* _%s_\n" % m.mail

                upd = mail.update().values(read=True).where(
                    mail.c.userID == userID)
                con.execute(upd)

                invest_actions = select([actions]).where(actions.c.userID == userID).where(
                    actions.c.action == 'INVEST').where(actions.c.approved == None)
                invest_rs = con.execute(invest_actions).fetchall()

                if len(invest_rs) > 0:
                    message += "Waiting to update your portfolio\n"
                    keyboard += [[InlineKeyboardButton(text="update", callback_data="/refresh")]]
                else:
                    position = int(position) / 1e8
                    message += "Your portfolio is *%.8f* BTC\n" % (position)
                    if (balance == 0) and (position > 0):
                        #message += "Would you check /portfolio stats?\n"
                        # keyboard = [[KeyboardButton(text="/portfolio")]]
                        keyboard += [[InlineKeyboardButton(text="check portfolio stats", callback_data="/portfolio")]]
                    elif (len(unconfirmedTXs) == 0) and (balance > 0):
                        message += "Please confirm creation of your portfolio by entering\n/invest\n"
                        keyboard += [[InlineKeyboardButton(text="Yes, please", callback_data="/invest")]]
                    for tx in unconfirmedTXs:
                        message += "Pending transaction for: %s BTC\n" % (int(tx['value']) / 1e8)
                        message += "tx ID: *%s*\n" % tx['ID']
                        keyboard += [[InlineKeyboardButton(text="update", callback_data="/refresh")]]
                    message += "Your address is\n"

            except:
                logger.error(traceback.format_exc())
                log_event = 'balance unavailable'
                log_record(log_event, update)
                message += "*Balance is unavailable*"
                keyboard += [[InlineKeyboardButton(text="contact support", callback_data="/contact")]]
                msg = "Balance is unavailable [%s](tg://user?id=%s)\n" % (userID, userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
    return address, isadmin, keyboard, message


# TODO: folio stats
def folio_stats(bot, update):
    query = update.callback_query
    chat_id = query.message.chat_id
    log_event = 'folio stats checked'
    userID = log_record(log_event, update)
    df = pd.read_sql_query(sql='SELECT * FROM ' + positions_table + ' WHERE `USERID` = ' + str(userID),
                           con=db_engine, index_col='timestamp')
    df_groupped = df.groupby(df.index)['position'].mean()
    send_stats(bot, df_groupped, chat_id)


def log_record(log_event, update):
    userfrom = update.effective_user
    logger.debug("userfrom : %s" % userfrom)
    userID = userfrom.id
    with db_engine.connect() as con:
        ins = log.insert().values(userID=userID, log=log_event, timestamp=datetime.utcnow())
        con.execute(ins)
    return userID


# TODO: stats
def stats(bot, update):
    log_event = 'hedge fund stats checked'
    log_record(log_event, update)
    df = pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')
    df_groupped = df.groupby(df.timestamp.dt.date)['totalbalance'].mean()
    send_stats(bot, df_groupped, update)


def send_stats(bot, df_groupped, chat_id):
    if len(df_groupped) > 0:
        # daily_pc = df_groupped.pct_change().dropna() * 365 * 100
        cumulative_pc = ((df_groupped - df_groupped.ix[0]) / df_groupped.ix[0]) * 100

        # plot_graph(daily_pc, pic_1_filename, 'Yearly %')
        plot_graph(cumulative_pc, pic_2_filename, 'Return On Investment, %')

        # picture_1 = open(pic_folder + '/' + pic_1_filename, 'rb')
        # bot.send_photo(chat_id=update.message.chat_id, photo=picture_1)
        picture_2 = open(pic_folder + '/' + pic_2_filename, 'rb')
        keyboard = [[KeyboardButton(text="/start")]]
        bot.send_photo(chat_id=chat_id, photo=picture_2,
                       reply_markup=ReplyKeyboardMarkup(keyboard=keyboard))


# TODO: OTP command
def OTP_command(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    OTP = update.message.text
    log_event = 'OTP command: %s args: %s' % (OTP, last_args)
    log_record(log_event, update)
    message = None

    if last_command == 'BW' and last_args > 0.05:
        try:
            result = bitmex.withdraw(amount=last_args * XBt_TO_XBT, address=POLO_ADDRESS, otptoken=OTP)
            logger.debug(result)
        except Exception as e:
            result = e
        if 'error' in result:
            message = result['error']['message']
        elif 'transactID' in result:
            message = 'BitMEX -> Polo transfer created, ID: *%s*' % result['transactID']

        if message:
            bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=admin_keyboard))

    last_command = None
    last_args = None


# TODO: cancel OTP
def CancelOTP(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    log_event = 'Cancel OTP'
    log_record(log_event, update)
    last_command = None
    last_args = None
    message = "Command cancelled"
    bot.send_message(chat_id=update.message.chat_id, text=message, reply_markup=ReplyKeyboardMarkup(
        keyboard=admin_keyboard))


# TODO: contact
def contact(bot, update):
    log_event = 'Support request is sent'
    userID = log_record(log_event, update)
    with db_engine.connect() as con:
        # actions = Table(actions_table, metadata, autoload=True)
        ins = actions.insert().values(userID=userID, action='SUPPORT', timestamp=datetime.utcnow())
        con.execute(ins)
        message = "Support request is sent.\n*Please wait to be contacted.*\n"
        bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                         reply_markup=ReplyKeyboardMarkup(
                             keyboard=[[KeyboardButton(text="/start")]]))
        msg = "New support request from [%s](tg://user?id=%s)\n" % (userID, userID)
        bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')


# TODO: invest
def invest(bot, update):
    log_event = 'Invest request is sent'
    userID = log_record(log_event, update)
    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.ID == userID)
        rs = con.execute(stm).fetchall()
        address = rs[0].address
        withdrawn = rs[0].withdrawn
        try:
            balance = XMLRPCServer.getInputValue(address) - withdrawn
            logger.debug("balance %.8f" % (balance / 1e8))
            if balance > 0:
                ins = actions.insert().values(userID=userID, action='INVEST', args=balance, timestamp=datetime.utcnow())
                con.execute(ins)
                message = "Invest request is sent.\n*Please wait until we double-check and process your request.*\n"
                msg = "New invest request from [%s](tg://user?id=%s)\n" % (userID, userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
            else:
                message = "*You have insufficient balance.\nPlease top-up your wallet first and wait until your funds are confirmed.*"
            bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                             reply_markup=ReplyKeyboardMarkup(
                                 keyboard=[[KeyboardButton(text="/start")]]))
        except:
            logger.error(traceback.format_exc())
            msg = "Invest request error from [%s](tg://user?id=%s)\n" % (userID, userID)
            bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')


# TODO: actions
def unapproved_actions(bot, update):
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    with db_engine.connect() as con:
        j = actions.join(useraccounts)
        q = select([actions, useraccounts]).where(actions.c.approved == None).order_by(
            desc(actions.c.timestamp)).select_from(j)
        rs = con.execute(q)
        response = rs.fetchall()
        message = ""
        i = 0
        for a in response:
            i += 1
            username = a.username
            user_id = a.userID
            action = a.action
            timestamp = a.timestamp
            message += "*a%d*: [%s](tg://user?id=%s) %s (%s)\n" % (
                i, username, user_id, action, timestamp.strftime("%d %b %H:%M:%S"))

    if message == "":
        message = "All actions were approved\n"
        reply_markup = ReplyKeyboardMarkup(keyboard=admin_keyboard)
    else:
        message += "Type *a[n]* to approve\n"
        reply_markup = ReplyKeyboardRemove()
    bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                     reply_markup=reply_markup)


# TODO: action_approve
def action_approve(bot, update):
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    action_id = update.message.text.split("a")[1]
    found = False
    with db_engine.connect() as con:
        j = actions.join(useraccounts)
        q = select([actions, useraccounts]).where(actions.c.approved == None).order_by(
            desc(actions.c.timestamp)).select_from(j)
        rs = con.execute(q)
        response = rs.fetchall()
        i = 0
        action = None
        user_address = None
        user_withdrawn = None
        user_id = None
        timestamp = None
        for a in response:
            i += 1
            if i == int(action_id):
                username = a.username
                user_id = a.userID
                user_address = a.address
                user_withdrawn = a.withdrawn
                action = a.action
                timestamp = a.timestamp

                found = True
                break

    if found:
        message = "Action *%s* approved:\n[%s](tg://user?id=%s) %s (%s)\n" % (
            action_id, username, user_id, action, timestamp.strftime("%d %b %H:%M:%S"))
        logger.debug("%s %s %s" % (action, user_address, user_withdrawn))
        # TODO: INVEST APPROVE
        if (action == 'INVEST') and user_address:
            logger.debug("invest action started")
            try:
                logger.debug("getting balance")
                balance = XMLRPCServer.getInputValue(user_address) - user_withdrawn
                logger.debug("balance %.8f" % (balance / 1e8))
                message += 'user balance: %.8f\n' % (balance / 1e8)
                logger.debug("sending to polo")
                send_result = XMLRPCServer.sendCoins(user_address, poloniex_address, balance)
                logger.debug("sr: %s" % send_result)
                if send_result:
                    tx_id = send_result['TX']
                    tx_value = int(send_result['value'])
                    message += 'TX ID: *%s*\n' % tx_id
                    message += 'TX value: *%s*\n' % tx_value
                    if tx_value > 0:
                        with db_engine.connect() as con:
                            select_positions = select([positions]).where(positions.c.userID == user_id).order_by(
                                desc(positions.c.timestamp))
                            rs = con.execute(select_positions)
                            response = rs.fetchall()

                            user_position = response[0].position
                            user_pos_timestamp = response[0].timestamp

                            upd = positions.update().values(position=(user_position + tx_value)).where(
                                positions.c.userID == user_id).where(positions.c.timestamp == user_pos_timestamp)
                            con.execute(upd)
                            upd = useraccounts.update().values(withdrawn=(user_withdrawn + balance)).where(
                                useraccounts.c.ID == user_id)
                            con.execute(upd)
                            msg_to_user = 'Portfolio is created: %.8f BTC, %8f fee paid' % (
                                tx_value / 1e8, (balance - tx_value) / 1e8)
                            ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user,
                                                       timestamp=datetime.utcnow())
                            con.execute(ins)
                        approve_action(action, timestamp, user_id)
                        log_event = 'user: %s tx: %s val %s' % (user_id, tx_id, tx_value)
                        log_record(log_event, update)

            except:
                logger.error(traceback.format_exc())
                message += '*cannot send coins*\n'

        # TODO: SUPPORT APPROVE
        elif action == 'SUPPORT':
            with db_engine.connect() as con:
                msg_to_user = 'Support is notified and will contact you soon'
                ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user, timestamp=datetime.utcnow())
                con.execute(ins)
            log_record(message, update)
            approve_action(action, timestamp, user_id)
        else:
            log_record(message, update)
            approve_action(action, timestamp, user_id)
    else:
        message = "Action *%s* not found!\n" % (action_id)

    bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                     reply_markup=ReplyKeyboardMarkup(
                         keyboard=admin_keyboard))


# TODO: fn - approve
def approve_action(action, timestamp, user_id):
    with db_engine.connect() as con:
        upd = actions.update().values(approved=True).where(actions.c.userID == user_id).where(
            actions.c.action == action).where(actions.c.timestamp == timestamp)
        con.execute(upd)


# TODO: transfers_show
def transfers_show(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    df = pd.read_sql_table(balance_diff_table, con=db_engine, index_col='index')
    transfer_record = df.to_dict(orient='records')
    transfer_diff = round(transfer_record[0]['avg_balance_difference'] * 0.5, 6)
    if transfer_diff > 0:
        direction = '->'
        last_command = 'BW'
        last_args = transfer_diff
    elif transfer_diff < 0:
        direction = '<-'
        last_command = 'PW'
        last_args = abs(transfer_diff)

    message = "_BitMEX_ %s _Poloniex_ %.6f\n" % (direction, abs(transfer_diff))
    result = bitmex.min_withdrawal_fee()
    logger.debug(result)
    message += "_Min fee is:_ %s\n" % (result['minFee'] / XBt_TO_XBT)

    message += "_Current UTC now is_ %s\n" % (datetime.utcnow().strftime("%H:%M:%S"))
    message += "send OTP to confirm or 0 to cancel"
    bot.send_message(chat_id=update.message.chat_id, text=message, reply_markup=ReplyKeyboardRemove(),
                     parse_mode='Markdown')
    last_command = 'BW'
    last_args = transfer_diff


# TODO: health
def health_check(bot, update):
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    message = ''
    pid = None
    for proc in psutil.process_iter():
        proc_dict = proc.as_dict()
        if 'mercurybot' in proc_dict['cmdline']:
            if 'pid' in proc_dict:
                pid = proc_dict['pid']
    if pid:
        message += "bot pid: *%s*\n" % pid
    else:
        message += "*bot is not running!*\n"
    message += "virtual memory used *%d%%*\n" % psutil.virtual_memory().percent
    message += "swap memory used *%d%%*\n" % psutil.swap_memory().percent

    freeG = shutil.disk_usage('/').free / 1e9
    message += "free disk space: *%.2f* Gb\n" % freeG
    health_df = pd.read_sql_table('mercury_health', con=db_engine)
    health_record = health_df.to_dict(orient='records')
    for r in health_record[0]:
        if r not in ['index', 'timestamp']:
            message += "_%s_ is alive: *%s*\n" % (r, health_record[0][r] == 1)
    message += "_time is_ *%s* _UTC_\n" % (datetime.utcnow().strftime("%H:%M:%S"))
    message += "_updated %d s ago_\n" % ((getUTCtime() - health_record[0]['index']) / 1000)

    logger.debug(message)
    bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown')


# TODO: check_admin_privilege
def check_admin_privilege(update):
    isadmin = False
    useraccounts = Table(useraccounts_table, metadata, autoload=True)
    stm = select([useraccounts]).where(useraccounts.c.ID == update.effective_user.id)
    with db_engine.connect() as con:
        rs = con.execute(stm)
        response = rs.fetchall()
        if len(response) == 1:
            for u in response:
                isadmin = u.isadmin == 1
                if isadmin:
                    logger.debug("admin privilege confirmed, %s" % update.effective_user.id)

    return isadmin


# TODO: plot glaph
def plot_graph(df, name, label):
    fig, ax = plt.subplots()
    ax.plot(df.index, df, label=label)

    myFmt = mdates.DateFormatter('%d %b %y')
    ax.xaxis.set_major_formatter(myFmt)

    ax.set_xlim(df.index.min(), df.index.max())
    ax.grid(True)
    fig.autofmt_xdate()

    plt.title(label)
    plt.legend()

    plt.plot(df)
    plt.savefig(pic_folder + '/' + name)


if __name__ == "__main__":
    # admin_keyboard = [[KeyboardButton(text="/statistics")], [KeyboardButton(text="/transfers")],
    #                  [KeyboardButton(text="/health")], [KeyboardButton(text="/actions")]]
    admin_keyboard = [[KeyboardButton(text="/statistics")], [KeyboardButton(text="/transfers")],
                      [KeyboardButton(text="/health")], [KeyboardButton(text="/actions")]]

    user_keyboard = [[KeyboardButton(text="/start")], [KeyboardButton(text="/statistics")],
                     [KeyboardButton(text="/help")]]

    # TODO: handlers
    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', bot_help)
    stats_handler = CommandHandler('statistics', stats)
    # folio_handler = CommandHandler('portfolio', folio_stats)
    health_handler = CommandHandler('health', health_check)
    contact_handler = CommandHandler('contact', contact)
    invest_handler = CommandHandler('invest', invest)
    actions_handler = CommandHandler('actions', unapproved_actions)
    transfers_show_handler = CommandHandler('transfers', transfers_show)
    OTP_handler = RegexHandler(pattern='^\d{6}$', callback=OTP_command)
    OTP_cancel_handler = RegexHandler(pattern='^0$', callback=CancelOTP)
    action_approve_handler = RegexHandler(pattern='^a\d{1,3}$', callback=action_approve)

    folio_handler = CallbackQueryHandler(callback=folio_stats, pattern='^/portfolio')
    update_handler = CallbackQueryHandler(callback=update_main, pattern='^/update')

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(stats_handler)
    dispatcher.add_handler(folio_handler)
    dispatcher.add_handler(health_handler)
    dispatcher.add_handler(transfers_show_handler)
    dispatcher.add_handler(OTP_handler)
    dispatcher.add_handler(OTP_cancel_handler)
    dispatcher.add_handler(contact_handler)
    dispatcher.add_handler(invest_handler)
    dispatcher.add_handler(actions_handler)
    dispatcher.add_handler(action_approve_handler)
    dispatcher.add_handler(update_handler)

    dispatcher.add_error_handler(error_callback)
    updater.start_polling()
