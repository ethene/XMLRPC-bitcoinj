#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

# TODO: imports
import calendar
import gettext
import logging
import math
import re
import shutil
import traceback
import xmlrpc.client
from calendar import monthrange
from datetime import datetime, timedelta

import coloredlogs
import emoji
import matplotlib as mpl
import pandas as pd
import psutil
import requests
from sqlalchemy import (create_engine, Table, Column, Integer, BigInteger, ForeignKey, DateTime,
                        String, Boolean, MetaData, desc, func)
from sqlalchemy.sql import select
from telegram import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler, RegexHandler, CallbackQueryHandler
from telegram.ext import Updater

from utils.dotdict import dotdict

mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys

sys.path.insert(0, '../BitMEX-trader/db/')
from settings import MYSQL_CONNECTION
from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler
from bitmex import BitMEX

en = gettext.translation('mercury-telegram', localedir='locale', languages=['en'])
en.install()

def error_callback(bot, update, error):
    try:
        raise error
    except TelegramError as e:
        logger.error(e)
        logger.error(traceback.format_exc())


actions_table = 'telegram_actions'
log_table = 'telegram_log'
mail_table = 'telegram_mail'
useraccounts_table = 'telegram_useraccounts'
positions_table = 'mercury_positions'
balance_table = 'mercury_balance'
balance_diff_table = 'avg_balance_difference'
tc_table = 'mercury_TC'
unhedge_pnl_table = 'unhedge_pnl'
transactions_table = 'bitcoinj_transactions'
pic_folder = './pictures'
pic_1_filename = 'balance.png'
pic_2_filename = 'cumulative.png'
#

XBt_TO_XBT = 100000000

level = logging.DEBUG
script_name = 'telegram.bot'

db_engine = create_engine(MYSQL_CONNECTION, echo=False, pool_recycle=3600)
metadata = MetaData(db_engine)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', level=level)
logger = logging.getLogger(script_name)
log_filename = './log/' + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
coloredlogs.install(level=level)

# last command to perform with OTP auth
last_command = None
last_args = None

settings_table = 'mercury_settings'
mercury_settings = Table(settings_table, metadata, autoload=True)
settings_dict = {}
with db_engine.connect() as con:
    tc_select = select([mercury_settings])
    rs = con.execute(tc_select).fetchall()
    for r in rs:
        settings_dict[r['S_KEY']] = r['S_VALUE']

settings_dict = dotdict(settings_dict)
# logger.debug(settings_dict)

XMLRPCServer = xmlrpc.client.ServerProxy(settings_dict['XMLRPCServer'])
# BLOCK_EXPLORER = settings_dict['BLOCK_EXPLORER']
TESTING_MODE = (settings_dict.TESTING_MODE == 'True')
# TEST_ADDRESS = settings_dict['TEST_ADDRESS']
# BITMEX_ADDRESS = settings_dict['BITMEX_ADDRESS']
TELEGRAM_CHANNEL_NAME = settings_dict.TELEGRAM_CHANNEL_NAME
# POLO_ADDRESS = settings_dict['POLO_ADDRESS']
# BITMEX_KEY = settings_dict['BITMEX_KEY']
# BITMEX_SECRET = settings_dict['BITMEX_SECRET']

bitmex = BitMEX(apiKey=settings_dict.BITMEX_KEY, apiSecret=settings_dict.BITMEX_SECRET,
                base_url=settings_dict.BITMEX_URL, logger=logger)

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
                    Column('action', String(255)), Column('approved', Boolean()),
                    Column('args', String(255)),
                    Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()),
                    Column('actionID', Integer, primary_key=True, autoincrement=True)
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
    mail = Table(mail_table, metadata,
                 Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                 Column('mail', String(1024)), Column('read', Boolean(), default=False),
                 Column('timestamp', DateTime, default=datetime.utcnow(), onupdate=func.utc_timestamp()),
                 Column('ID', Integer, primary_key=True, autoincrement=True))
    # Implement the creation
    metadata.create_all()
else:
    mail = Table(mail_table, metadata, autoload=True)

if not db_engine.dialect.has_table(db_engine, transactions_table):
    logger.warn("transactions table does not exist")
    bitcoinj_transactions = Table(transactions_table, metadata,
                                  Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                                  Column('TXID', String(255)), Column('confirmed', Boolean(), default=False),
                                  Column('timestamp', DateTime, default=datetime.utcnow(),
                                         onupdate=func.utc_timestamp()),
                                  Column('value', BigInteger(), default=0), Column('direction', String(3)),
                                  Column('ID', Integer, primary_key=True, autoincrement=True))
    metadata.create_all()
else:
    bitcoinj_transactions = Table(transactions_table, metadata, autoload=True)

unhedge_pnl = Table(unhedge_pnl_table, metadata, autoload=True)
mercury_tc = Table(tc_table, metadata, autoload=True)
updater = Updater(token=settings_dict.TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher


#
# Helpers
#

def getUTCtime():
    d = datetime.utcnow()
    unixtime = calendar.timegm(d.utctimetuple())
    return unixtime * 1000


def admin_functions(bot, update):
    query = update.callback_query
    bot.answerCallbackQuery(callback_query_id=query.id, text="~~~Admin Functions~~~")
    chat_id = query.message.chat_id
    bot.editMessageReplyMarkup(chat_id=chat_id, message_id=query.message.message_id,
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard))


# TODO: start
def start(bot, update):
    chat_id = get_chat_id(update)

    address, isadmin, keyboard, message = StartMessage(bot, update)

    tc_button = [[InlineKeyboardButton(
        text=_("TC_BUTTON") % (
            emoji.emojize(':mag_right:', use_aliases=True)),
        callback_data='/readtc1')]]
    keyboard = tc_button + keyboard
    keyboard += [[InlineKeyboardButton(
        text=_("STATS_BUTTON") % (emoji.emojize(':chart_with_upwards_trend:', use_aliases=True)),
        callback_data='/statistics')]]
    keyboard += [[InlineKeyboardButton(
        text=_("SUPPORT_BUTTON") % (
            emoji.emojize(':warning:', use_aliases=True)),
        callback_data='/contact')]]
    if isadmin:
        keyboard += [[InlineKeyboardButton(
            text="%s admin functions" % (
                emoji.emojize(':memo:', use_aliases=True)),
            callback_data='/admin')]]
    keyboard += back_button
    logger.debug(keyboard)
    logger.debug(message)

    if message and len(keyboard) > 0:
        if address:
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown', disable_web_page_preview=True)
            bot.send_message(chat_id=chat_id, text="`%s`" % (address),
                             parse_mode='Markdown', disable_web_page_preview=True,
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        else:
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown', disable_web_page_preview=True,
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
                ins = log.insert().values(userID=userID, log='new user created % s' % (username or firstname),
                                          timestamp=datetime.utcnow())
                con.execute(ins)
                logger.debug(_("HELLO_NEW_USER") + "\n")
                logger.debug((username or firstname))
                message = _("HELLO_NEW_USER") % (username or firstname) + "\n"
                if TESTING_MODE:
                    message += _("BOT_IN_TESTING") + "\n"
                message += _("NEW_USER_INFO") + ":\n"
                msg = "*New user created:* [%s](tg://user?id=%s)\n" % ((username or firstname), userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
            except:
                logger.error(traceback.format_exc())
                message = "Failed to create new user"
                msg = "*Error:* failed to create user [%s](tg://user?id=%s)\n" % ((username or firstname), userID)
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
                message = _("WELCOME_BACK_ADMIN") % (
                    (username or firstname), emoji.emojize(':purple_heart:', use_aliases=True)) + "\n"
            else:
                message = _("WELCOME_BACK_USER") % (
                    (username or firstname), emoji.emojize(':currency_exchange:', use_aliases=True)) + "\n"

            select_positions = select([positions]).where(positions.c.userID == userID).order_by(
                desc(positions.c.timestamp))
            rs = con.execute(select_positions)
            response2 = rs.fetchall()
            address = response[0].address
            position = response2[0].position
            withdrawn = response[0].withdrawn

            try:
                logger.debug("address %s" % (address))
                logger.debug("withdrawn %s" % (withdrawn))
                try:
                    inp_value = XMLRPCServer.getInputValue(address)
                except:
                    inp_value = 0

                balance = inp_value - withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                try:
                    unconfirmedTXs = XMLRPCServer.getUnconfirmedTransactions(address)
                except:
                    unconfirmedTXs = []
                    logger.debug("unconfirmed: %s" % unconfirmedTXs)

                balance = int(balance) / XBt_TO_XBT

                new_mail = select([mail]).where(mail.c.userID == userID).where(mail.c.read == False).order_by(
                    desc(mail.c.timestamp))
                mail_rs = con.execute(new_mail).fetchall()
                for m in mail_rs:
                    message += _("NEW_MAIL") % (emoji.emojize(':email:', use_aliases=True)) + "\n%s\n" % m.mail

                upd = mail.update().values(read=True).where(
                    mail.c.userID == userID)
                con.execute(upd)

                invest_actions = select([actions]).where(actions.c.userID == userID).where(
                    actions.c.action == 'INVEST').where(actions.c.approved == None)
                invest_rs = con.execute(invest_actions).fetchall()

                if len(invest_rs) > 0:
                    message += _("WAITING_TO_APPROVE_INVEST") + "\n"
                    address = None

                else:
                    if position:
                        position = int(position) / XBt_TO_XBT
                        message += _("YOUR_PORTFOLIO_WORTH") % position + "\n"

                    if balance == 0:
                        if TESTING_MODE:
                            message += _("BOT_IN_TESTING") + "\n"
                        message += _("WALLET_EMPTY") % emoji.emojize(':o:', use_aliases=True) + "\n"
                    else:
                        message += _("YOUR_BALANCE_IS") % (balance) + "\n"

                    for tx in unconfirmedTXs:
                        message += _("PENDING_TRANSACTION") % (int(tx['value']) / XBt_TO_XBT) + "\n"
                        message += _("TX_ID") % (tx['ID'], settings_dict.BLOCK_EXPLORER, tx['ID']) + "\n"
                        select_txs = select([bitcoinj_transactions]).where(
                            bitcoinj_transactions.c.TXID == tx['ID']).where(bitcoinj_transactions.c.confirmed == False)
                        txs = con.execute(select_txs).fetchall()
                        if len(txs) == 0:
                            ins = bitcoinj_transactions.insert().values(userID=userID, TXID=tx['ID'],
                                                                        value=int(tx['value']), direction='IN',
                                                                        confirmed=False, timestamp=datetime.utcnow())
                            con.execute(ins)

                    if (len(unconfirmedTXs) == 0) and (balance > 0):
                        message += _("IF_YOU_AGREE_TO_INVEST") + "\n"
                        keyboard += [[InlineKeyboardButton(
                            text=_("OK_AGREE") % (
                                emoji.emojize(':ok_hand:', use_aliases=True)),
                            callback_data='/invest')]]
                        address = None
                    else:
                        message += _("YOUR_ADDRESS_IS") % (
                            emoji.emojize(':arrow_heading_down:', use_aliases=True)) + "\n"

            except:
                logger.error(traceback.format_exc())
                log_event = 'balance unavailable'
                log_record(log_event, update)
                message += _("BALANCE_UNAV") + "\n"
                keyboard += [[InlineKeyboardButton(
                    text=_("SUPPORT_BUTTON") % (
                        emoji.emojize(':warning:', use_aliases=True)),
                    callback_data='/contact')]]
                msg = "Balance is unavailable [%s](tg://user?id=%s)\n" % ((username or firstname), userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
    return address, isadmin, keyboard, message


# TODO: Terms and Conditions:
def readtc(bot, update):
    chat_id = get_chat_id(update)
    data = update.callback_query.data

    logger.debug(data)
    page_id = int(str.split(data, "readtc")[1])
    logger.debug(page_id)
    with db_engine.connect() as con:
        tc_select = select([mercury_tc])
        rs = con.execute(tc_select).fetchall()
        tc_text = rs[0].tc
        tc_page = str.split(tc_text, "<br>")[page_id]
        tc_headers = re.findall(r"(\*)(.+)(\*)", tc_text)
        keyboard = []
        i = 0
        myheader = ""
        for h in tc_headers:
            i += 1
            if i != page_id:
                keyboard += [[InlineKeyboardButton(
                    text="%s" % (h[1]),
                    callback_data='/readtc' + str(i))]]
            else:
                myheader = h[1]

        logger.debug(tc_page)
        logger.debug(tc_headers)
        keyboard += back_button

        query = update.callback_query
        bot.answerCallbackQuery(callback_query_id=query.id, text=myheader)
        bot.send_message(chat_id=chat_id, text=tc_page, parse_mode='Markdown',
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=keyboard))


def log_record(log_event, update):
    userID = get_userID(update)
    with db_engine.connect() as con:
        ins = log.insert().values(userID=userID, log=log_event, timestamp=datetime.utcnow())
        con.execute(ins)
    return userID


def get_userID(update):
    userfrom = update.effective_user
    logger.debug("userfrom : %s" % userfrom)
    userID = userfrom.id
    return userID


def getBTCPrice():
    BITSTAMP_URL = 'https://www.bitstamp.net/api/ticker/'
    r = requests.get(url=BITSTAMP_URL)
    j = r.json()
    return float(j['high'])


# TODO: statistics
def stats(bot, update):
    chat_id = get_chat_id(update)
    log_event = 'hedge fund stats checked'
    userID = log_record(log_event, update)
    BTCprice = getBTCPrice()
    logger.debug(getBTCPrice())
    with db_engine.connect() as con:
        select_positions = select([positions]).where(positions.c.userID == userID).order_by(
            desc(positions.c.timestamp))
        rs = con.execute(select_positions)
        response2 = rs.fetchall()
        position = response2[0].position
        if position > 0:
            df = pd.read_sql_query(sql='SELECT * FROM ' + positions_table + ' WHERE `USERID` = ' + str(userID),
                                   con=db_engine, index_col='timestamp')
            df = df[(df.position != 0)]
            df_groupped = df.groupby(df.index)['position'].mean()
            message = _("YOUR_FOLIO_PERFORMANCE")
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=ReplyKeyboardRemove())
            send_stats(bot, df_groupped, chat_id)
            t_diff = monthdelta(df_groupped.index[0], df_groupped.index[-1])
            month_diff = t_diff[0]
            d_diff = t_diff[1]
            message = _("WAS_OPENED_AGO") % (month_diff, d_diff) + "\n"
            balance_profit = (df_groupped[-1] - df_groupped[0]) / XBt_TO_XBT
            message += _("YOUVE_INVESED") % (df_groupped[0] / XBt_TO_XBT) + "\n"
            if balance_profit > 0:
                message += _("NOW_WORTH") % (df_groupped[-1] / XBt_TO_XBT) + "\n"
                message += _("ABS_RETURN") % (balance_profit) + "\n"
                message += _("EQUALS_TO") % (balance_profit * BTCprice, BTCprice) + "\n"
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=ReplyKeyboardRemove())

    df = pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')
    df_groupped = df.groupby(df.timestamp.dt.date)['totalbalance'].mean()
    message = _("COMBINED_STATS")
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=ReplyKeyboardRemove())

    send_stats(bot, df_groupped, chat_id)
    balance_profit = df_groupped[-1] - df_groupped[0]
    timedelta = df_groupped.index[-1] - df_groupped.index[0]
    yearly_pc = ((balance_profit / timedelta.days) * 365) / df_groupped[0] * 100
    t_diff = monthdelta(df_groupped.index[0], df_groupped.index[-1])
    month_diff = t_diff[0]
    d_diff = t_diff[1]
    message = _("CS_WHICH_IS") % yearly_pc + "\n\n"
    message += _("CS_WAS_ACHIEVED") % (month_diff, d_diff) + "\n"
    message += _("CS_IF_INVESTED") % (
        df_groupped.index[0].strftime("%d %b"), (balance_profit / df_groupped[0]) + 1) + "\n"
    message += _("CS_ABS_PROFIT") % (balance_profit / df_groupped[0]) + "\n"
    message += _("EQUALS_TO") % ((balance_profit / df_groupped[0]) * BTCprice, BTCprice) + "\n"
    keyboard = back_button
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(
                         inline_keyboard=keyboard))


def send_stats(bot, df_groupped, chat_id):
    if len(df_groupped) > 0:
        # daily_pc = df_groupped.pct_change().dropna() * 365 * 100
        cumulative_pc = ((df_groupped - df_groupped.ix[0]) / df_groupped.ix[0]) * 100

        plot_graph(cumulative_pc, pic_2_filename, 'Return On Investment, %')
        picture_2 = open(pic_folder + '/' + pic_2_filename, 'rb')
        keyboard = ReplyKeyboardRemove()
        bot.send_photo(chat_id=chat_id, photo=picture_2,
                       reply_markup=keyboard)


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
            result = bitmex.withdraw(amount=last_args * XBt_TO_XBT, address=settings_dict.POLO_ADDRESS, otptoken=OTP)
            logger.debug(result)
        except Exception as e:
            result = e
        if 'error' in result:
            message = result['error']['message']
        elif 'transactID' in result:
            message = 'BitMEX -> Polo transfer created\nID: *%s*' % result['transactID']

        if message:
            keyboard = admin_keyboard
            bot.send_message(chat_id=update.message.chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=keyboard))

    last_command = None
    last_args = None


# TODO: cancel OTP
def CancelOTP(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    chat_id = get_chat_id(update)
    log_event = 'Cancel OTP'
    log_record(log_event, update)
    last_command = None
    last_args = None
    message = "Command cancelled"
    keyboard = admin_keyboard
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(
                         inline_keyboard=keyboard))


# TODO: contact
def contact(bot, update):
    query = update.callback_query
    # chat_id = get_chat_id(update)
    user_id = get_userID(update)
    message = "\n" + _("SUPPORT_REQUEST_SENT") + "\n"
    bot.answerCallbackQuery(callback_query_id=query.id, text=message, show_alert=True)

    with db_engine.connect() as con:
        msg_to_user = '\n' + _("SUPPORT_REQUEST_SENT") + "\n"
        ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user, timestamp=datetime.utcnow())
        con.execute(ins)
        user_select = select([useraccounts]).where(useraccounts.c.ID == user_id)
        rs = con.execute(user_select).fetchall()
        username = rs[0].username
        firstname = rs[0].firstname
    # keyboard = back_button

    msg = "*Support request*\nfrom [%s](tg://user?id=%s)\n" % (username or firstname, user_id)
    bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
    start(bot, update)


# TODO: invest
def invest(bot, update):
    query = update.callback_query
    chat_id = get_chat_id(update)
    log_event = 'Invest request is sent'
    userID = log_record(log_event, update)
    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.ID == userID)
        rs = con.execute(stm).fetchall()
        address = rs[0].address
        username = rs[0].username
        firstname = rs[0].firstname
        withdrawn = rs[0].withdrawn
        invest_actions = select([actions]).where(actions.c.userID == userID).where(
            actions.c.action == 'INVEST').where(actions.c.approved == None)
        invest_rs = con.execute(invest_actions).fetchall()
        message = None
        if len(invest_rs) > 0:
            message = _("YOU_SENT_INVEST") + "\n"
        else:
            try:
                balance = XMLRPCServer.getInputValue(address) - withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                if balance > 0:
                    ins = actions.insert().values(userID=userID, action='INVEST', args=balance, approved=None,
                                                  timestamp=datetime.utcnow())
                    con.execute(ins)
                    message = _("YOU_HAVE_AGREED") + "\n"
                    msg = "New invest request from [%s](tg://user?id=%s)\n" % (username or firstname, userID)
                    bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
                else:
                    message = _("INSUFFICIENT_BALANCE") + "\n"

            except:
                logger.error(traceback.format_exc())
                msg = "Invest request error from [%s](tg://user?id=%s)\n" % (username or firstname, userID)
                bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')
        if message:
            keyboard = back_button
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=keyboard))


# TODO: show users with positions
def show_users(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    message = ""
    with db_engine.connect() as con:
        select_positions = select([positions]).order_by(desc(positions.c.timestamp))
        rs = con.execute(select_positions).fetchall()
        max_pos_timestamp = rs[0].timestamp
        j = positions.join(useraccounts)
        q = select([positions, useraccounts]).where(positions.c.timestamp == max_pos_timestamp).where(
            positions.c.position > 0).order_by(desc(positions.c.position)).select_from(j)
        rs = con.execute(q).fetchall()
        i = 0
        for u in rs:
            logger.debug(u)
            i += 1
            username = u.username
            firstname = u.firstname
            user_id = u.userID
            position = u.position
            message += "*%d*: [%s](tg://user?id=%s) *%.6f*\n" % (
                i, username or firstname, user_id, (position / XBt_TO_XBT))

        if message:
            logger.debug(message)
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=admin_keyboard))


# TODO: show unapproved actions
def unapproved_actions(bot, update):
    chat_id = get_chat_id(update)
    query = update.callback_query
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return

    keyboard = []
    with db_engine.connect() as con:
        j = actions.join(useraccounts)
        q = select([actions, useraccounts]).where(actions.c.approved == None).order_by(
            desc(actions.c.timestamp)).select_from(j).limit(9)
        rs = con.execute(q)
        response = rs.fetchall()
        message = ""
        for a in response:
            username = a.username
            firstname = a.firstname
            user_id = a.userID
            action = a.action
            timestamp = a.timestamp
            i = a.actionID
            action_args = a.args if action != 'INVEST' else "%.6f _BTC_" % (int(a.args) / XBt_TO_XBT)
            message = "%d: [%s](tg://user?id=%s) *%s* _%s_ (%s)\n" % (
                i, username or firstname, user_id, action, action_args, timestamp.strftime("%d %b %H:%M:%S"))

            keyboard = [[InlineKeyboardButton(
                text="%s" % (emoji.emojize(':heavy_check_mark:', use_aliases=True)),
                callback_data=("a%s" % i)), InlineKeyboardButton(
                text="%s" % (emoji.emojize(':x:', use_aliases=True)),
                callback_data=("d%s" % i))]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=reply_markup)

        if len(response) == 0:
            message = "All actions were approved\n"
            reply_markup = ReplyKeyboardRemove()
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=reply_markup)


# TODO: action_disapprove
def action_disapprove(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    data = update.callback_query.data
    action_id = str.split(data, "d")[1]
    found, found_action = find_action(action_id)

    if found:
        username = found_action.username
        firstname = found_action.firstname
        user_id = found_action.userID
        user_address = found_action.address
        user_withdrawn = found_action.withdrawn
        action = found_action.action
        timestamp = found_action.timestamp
        message = "Action *%s* disapproved:\n[%s](tg://user?id=%s) %s (%s)\n" % (
            action_id, username or firstname, user_id, action, timestamp.strftime("%d %b %H:%M:%S"))
        logger.debug("%s %s %s" % (action, user_address, user_withdrawn))

        log_record(message, update)
        change_action(action_id=action_id, approved=False)
        msg_to_user = "\n" + _("YOUR_ACTION_DISAPPROVED") + "\n"
        bot.send_message(chat_id=user_id, text=msg_to_user, parse_mode='Markdown',
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=back_button))
        with db_engine.connect() as con:
            ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user,
                                       timestamp=datetime.utcnow())
            con.execute(ins)

    else:
        message = "Action *%s* not found!\n" % (action_id)

    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(
                         inline_keyboard=admin_keyboard))


# TODO: action_approve
def action_approve(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    data = update.callback_query.data
    # chat_id = query.message.chat_id
    action_id = str.split(data, "a")[1]
    found, found_action = find_action(action_id)

    if found:
        username = found_action.username
        firstname = found_action.firstname
        user_id = found_action.userID
        user_address = found_action.address
        user_withdrawn = found_action.withdrawn
        action = found_action.action
        timestamp = found_action.timestamp
        message = "Action *%s* approved:\n[%s](tg://user?id=%s) %s (%s)\n" % (
            action_id, username or firstname, user_id, action, timestamp.strftime("%d %b %H:%M:%S"))
        logger.debug("%s %s %s" % (action, user_address, user_withdrawn))
        # TODO: INVEST APPROVE
        if (action == 'INVEST') and user_address:
            logger.debug("invest action started")
            try:
                logger.debug("getting balance")
                balance = XMLRPCServer.getInputValue(user_address) - user_withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                message += 'user balance: %.8f\n' % (balance / XBt_TO_XBT)
                logger.debug("sending to polo")

                address = settings_dict.TEST_ADDRESS
                if not TESTING_MODE:
                    df = pd.read_sql_table(balance_diff_table, con=db_engine, index_col='index')
                    transfer_record = df.to_dict(orient='records')
                    transfer_diff = round(transfer_record[0]['avg_balance_difference'], 6)
                    if transfer_diff > 0:
                        address = settings_dict.POLO_ADDRESS
                    else:
                        address = settings_dict.BITMEX_ADDRESS
                send_result = XMLRPCServer.sendCoins(user_address, address, balance)
                logger.debug("sr: %s" % send_result)
                if send_result:
                    tx_id = send_result['TX']
                    tx_value = int(send_result['value'])
                    message += "TX ID: [%s](%s%s)\n" % (tx_id, settings_dict.BLOCK_EXPLORER, tx_id)
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
                            msg_to_user = "\n" + _("ADDED_TO_PORTFOLIO") % (
                                tx_value / XBt_TO_XBT, (balance - tx_value) / XBt_TO_XBT) + "\n"
                            bot.send_message(chat_id=user_id, text=msg_to_user, parse_mode='Markdown',
                                             reply_markup=InlineKeyboardMarkup(
                                                 inline_keyboard=back_button))
                            ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user,
                                                       timestamp=datetime.utcnow())
                            con.execute(ins)
                            ins = bitcoinj_transactions.insert().values(userID=user_id, TXID=tx_id,
                                                                        value=tx_value, direction='OUT',
                                                                        confirmed=True, timestamp=datetime.utcnow())
                            con.execute(ins)

                        change_action(action_id=action_id, approved=True)
                        log_event = 'user: %s tx: %s val %s' % (user_id, tx_id, tx_value)
                        log_record(log_event, update)

            except:
                logger.error(traceback.format_exc())
                message += '*cannot send coins*\n'

        # TODO: SUPPORT APPROVE
        elif action == 'SUPPORT':
            with db_engine.connect() as con:
                msg_to_user = 'Support request received!'
                ins = mail.insert().values(userID=user_id, read=False, mail=msg_to_user, timestamp=datetime.utcnow())
                con.execute(ins)
            log_record(message, update)
            change_action(action_id=action_id, approved=True)
        else:
            log_record(message, update)
            change_action(action_id=action_id, approved=True)
    else:
        message = "Action *%s* not found!\n" % (action_id)

    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown', disable_web_page_preview=True,
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard))


def find_action(action_id):
    found = False
    found_action = None
    with db_engine.connect() as con:
        j = actions.join(useraccounts)
        q = select([actions, useraccounts]).where(actions.c.actionID == action_id).order_by(
            desc(actions.c.timestamp)).select_from(j)
        rs = con.execute(q)
        response = rs.fetchall()
        if len(response) > 0:
            found = True
            found_action = response[0]
    return found, found_action


# TODO: fn - change_action
def change_action(action_id, approved):
    with db_engine.connect() as con:
        upd = actions.update().values(approved=approved).where(actions.c.actionID == action_id)
        con.execute(upd)


# TODO: transfers_show
def transfers_show(bot, update):
    chat_id = get_chat_id(update)
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    df = pd.read_sql_table(balance_diff_table, con=db_engine, index_col='index')
    transfer_record = df.to_dict(orient='records')
    transfer_diff = round(transfer_record[0]['avg_balance_difference'], 6)
    if transfer_diff > 0:
        direction = '->'
        last_command = 'BW'
        last_args = transfer_diff
    elif transfer_diff < 0:
        direction = '<-'
        last_command = 'PW'
        last_args = abs(transfer_diff)

    message = "_BitMEX_ %s _Poloniex_ *%.6f*\n" % (direction, abs(transfer_diff))
    result = bitmex.min_withdrawal_fee()
    logger.debug(result)
    message += "_Min fee is:_ *%s*\n" % (result['minFee'] / XBt_TO_XBT)

    message += "_Current UTC now is_ *%s*\n" % (datetime.utcnow().strftime("%H:%M:%S"))
    message += "send OTP to confirm or 0 to cancel"
    bot.send_message(chat_id=chat_id, text=message, reply_markup=ReplyKeyboardRemove(),
                     parse_mode='Markdown')
    last_command = 'BW'
    last_args = transfer_diff


def get_chat_id(update):
    try:
        chat_id = update.message.chat_id
    except:
        query = update.callback_query
        chat_id = query.message.chat_id
    return chat_id


# TODO: health
def health_check(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    message = ''
    pid = None
    isRunning = False
    for proc in psutil.process_iter():
        proc_dict = proc.as_dict()
        if 'mercurybot' in proc_dict['cmdline']:
            if 'pid' in proc_dict:
                pid = proc_dict['pid']
    if pid:
        isRunning = True
        message += "bot pid: *%s*\n" % pid
    else:
        message += "*bot is not running!*\n"
    message += "virtual memory used *%d%%*\n" % psutil.virtual_memory().percent
    message += "swap memory used *%d%%*\n" % psutil.swap_memory().percent

    freeG = shutil.disk_usage('/').free / 1e9
    message += "free disk space: *%.2f* Gb\n" % freeG
    health_df = pd.read_sql_table('mercury_health', con=db_engine)
    health_record = health_df.to_dict(orient='records')
    if isRunning:
        for r in health_record[0]:
            if r not in ['index', 'timestamp']:
                message += "_%s_ is alive: *%s*\n" % (r, health_record[0][r] == 1)

    with db_engine.connect() as con:
        select_positions = select([positions]).order_by(desc(positions.c.timestamp))
        rs = con.execute(select_positions).fetchall()
        max_pos_timestamp = rs[0].timestamp
        max_pos_timestamp = calendar.timegm(max_pos_timestamp.utctimetuple()) * 1000

        select_unh_pnl = select([unhedge_pnl]).order_by(desc(unhedge_pnl.c.timestamp))
        rs = con.execute(select_unh_pnl).fetchall()
        last_unhedge_pnl = rs[0].unhedge_pnl
        max_unh_timestamp = rs[0].timestamp
        max_unh_timestamp = calendar.timegm(max_unh_timestamp.utctimetuple()) * 1000

        message += "_time is_ *%s* _UTC_\n" % (datetime.utcnow().strftime("%H:%M:%S"))
        last_unh_s = (getUTCtime() - max_unh_timestamp) / 1000
        last_unh_m = math.floor(last_unh_s / 60.0)
        last_unh_h = math.floor(last_unh_m / 60.0)
        message += "_last unhedge %d h %d m ago\nlast pnl: %.6f_\n" % (
            last_unh_h, last_unh_m - (last_unh_h * 60), float(last_unhedge_pnl))
        message += "_position updated %d m ago_\n" % ((getUTCtime() - max_pos_timestamp) / 60000)
    message += "_health updated %d s ago_\n" % ((getUTCtime() - health_record[0]['index']) / 1000)

    logger.debug(message)
    query = update.callback_query
    bot.answerCallbackQuery(callback_query_id=query.id, text="~~~Health Status~~~")
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard))


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


def monthdelta(d1, d2):
    delta = 0
    diff = d2 - d1
    while True:
        mdays = monthrange(d1.year, d1.month)[1]
        d1 += timedelta(days=mdays)
        if d1 <= d2:
            diff -= timedelta(days=mdays)
            delta += 1
        else:
            break
    return delta, diff.days


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
    # TODO: keyboards
    back_button = [[InlineKeyboardButton(text=_("HOME_BUTTON") % emoji.emojize(":arrow_up_small:", use_aliases=True),
                                         callback_data="/start")]]

    admin_keyboard = [[InlineKeyboardButton(
        text="%s manage user actions" % emoji.emojize(":1234:", use_aliases=True),
        callback_data="/actions")],
                         [InlineKeyboardButton(
                             text="%s manage transfers" % emoji.emojize(":arrows_clockwise:", use_aliases=True),
                             callback_data="/transfers")],
                         [InlineKeyboardButton(
                             text="%s users with positions" % emoji.emojize(":busts_in_silhouette:", use_aliases=True),
                             callback_data="/users")],
                         [InlineKeyboardButton(
                             text="%s check bot health" % emoji.emojize(":battery:", use_aliases=True),
                             callback_data="/health")]] + back_button

    # TODO: handlers
    start_handler = CommandHandler('start', start)
    OTP_handler = RegexHandler(pattern='^\d{6}$', callback=OTP_command)
    OTP_cancel_handler = RegexHandler(pattern='^0$', callback=CancelOTP)

    # folio_handler = CallbackQueryHandler(pattern='^/portfolio', callback=folio_stats)
    stats_handler = CallbackQueryHandler(pattern='^/statistics', callback=stats)
    users_handler = CallbackQueryHandler(pattern='^/users', callback=show_users)
    update_handler = CallbackQueryHandler(pattern='^/start', callback=start)
    health_handler = CallbackQueryHandler(pattern='^/health', callback=health_check)
    actions_handler = CallbackQueryHandler(pattern='^/actions', callback=unapproved_actions)
    transfers_show_handler = CallbackQueryHandler(pattern='^/transfers', callback=transfers_show)
    admin_functions_handler = CallbackQueryHandler(pattern='^/admin', callback=admin_functions)
    contact_handler = CallbackQueryHandler(pattern='^/contact', callback=contact)
    invest_handler = CallbackQueryHandler(pattern='^/invest', callback=invest)
    action_approve_handler = CallbackQueryHandler(pattern='^a\d{1,3}$', callback=action_approve)
    action_disapprove_handler = CallbackQueryHandler(pattern='^d\d{1,3}$', callback=action_disapprove)
    tc_handler = CallbackQueryHandler(pattern='^/readtc\d', callback=readtc)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(tc_handler)
    dispatcher.add_handler(stats_handler)
    # dispatcher.add_handler(folio_handler)
    dispatcher.add_handler(health_handler)
    dispatcher.add_handler(transfers_show_handler)
    dispatcher.add_handler(OTP_handler)
    dispatcher.add_handler(OTP_cancel_handler)
    dispatcher.add_handler(contact_handler)
    dispatcher.add_handler(invest_handler)
    dispatcher.add_handler(actions_handler)
    dispatcher.add_handler(action_approve_handler)
    dispatcher.add_handler(action_disapprove_handler)
    dispatcher.add_handler(update_handler)
    dispatcher.add_handler(users_handler)
    dispatcher.add_handler(admin_functions_handler)

    dispatcher.add_error_handler(error_callback)
    updater.start_polling()
