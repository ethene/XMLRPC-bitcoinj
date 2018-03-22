#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

# TODO: imports
import calendar
import gettext
import json
import logging
import math
import os
import re
import traceback
import xmlrpc.client
from calendar import monthrange
from datetime import datetime, timedelta

import coloredlogs
import emoji
import matplotlib as mpl
import pandas as pd
import requests
from sqlalchemy import (create_engine, Table, Column, Integer, BigInteger, ForeignKey, DateTime, String, Boolean,
                        MetaData, desc, func)
from sqlalchemy.sql import select
from telegram import ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler, RegexHandler, CallbackQueryHandler
from telegram.ext import Updater

from utils.dotdict import dotdict

mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
# import sys

from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler
from bitmex import BitMEX
import poloniex

en = gettext.translation('mercury-telegram', localedir='locale', languages=['en'])
en.install()


def error_callback(bot, update, error):
    try:
        raise error
    except TelegramError as e:
        logger.error(e)
        logger.error(traceback.format_exc())


bitcoinj_host = os.getenv('BITCOINJ_HOST', 'localhost')
bitcoinj_port = os.getenv('BTICOINJ_RPCPORT', '8010')

mercurybot_host = os.getenv('MERCURYBOT_HOST', 'localhost')
mercurybot_port = os.getenv('MERCURYBOT_PORT', '8000')

mysql_host = os.getenv('MYSQL_HOST', 'localhost')
mysql_port = os.getenv('MYSQL_PORT', '3306')
mysql_user = os.getenv('MYSQL_USER', 'user')
mysql_pass = os.getenv('MYSQL_PASS', 'pass')
mysql_db = os.getenv('MYSQL_DB', 'cryptomarkets')

TEST_MODE = os.getenv('TEST_MODE', 'True') == 'True'

db_engine = create_engine(
    'mysql+mysqlconnector://' + mysql_user + ':' + mysql_pass + '@' + mysql_host + ':' + mysql_port + '/' + mysql_db,
    echo=False, pool_recycle=3600)
metadata = MetaData(db_engine)

SETTINGS_TABLE = 'mercury_settings'
settings = {}
mercury_settings = Table(SETTINGS_TABLE, metadata, autoload=True)
settings_dict = {}
with db_engine.connect() as con:
    tc_select = select([mercury_settings])
    rs = con.execute(tc_select).fetchall()
    for r in rs:
        settings_dict[r['S_KEY']] = r['S_VALUE']
settings.update(settings_dict)
settings = dotdict(settings)

BLOCK_EXPLORER = settings.BLOCK_EXPLORER
TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
BASE_URL = settings.BITMEX_URL
B_KEY = settings.BITMEX_KEY
B_SECRET = settings.BITMEX_SECRET

emoji_count = [':zero:', ':one:',
               ':two:', ':three:',
               ':four:', ':five:',
               ':six:', ':seven:',
               ':eight:', ':nine:']

efsfolder = os.getenv('EFSFOLDER', '.')

# TODO: table names
actions_table = 'telegram_actions'
log_table = 'telegram_log'
mail_table = 'telegram_mail'
useraccounts_table = 'mercury_useraccounts'
positions_table = 'mercury_positions'
balance_table = 'mercury_balance'
balance_diff_table = 'avg_balance_difference'
tc_table = 'mercury_TC'
unhedge_pnl_table = 'unhedge_pnl'
mm_pnl_table = 'mm_pnl'
fees_table = 'mercury_fees'
transactions_table = 'bitcoinj_transactions'
hold_balance_table = 'mercury_hold_balance'
investments_table = 'mercury_investments'
withdrawals_table = 'mercury_withdrawals'

pic_folder = efsfolder + '/pictures'
try:
    os.stat(pic_folder)
except:
    os.mkdir(pic_folder)
pic_1_filename = 'balance.png'
pic_2_filename = 'cumulative.png'

POLO_ADDRESS = settings['POLO_ADDRESS']
BITMEX_ADDRESS = settings['BITMEX_ADDRESS']
TELEGRAM_CHANNEL_NAME = settings['TELEGRAM_CHANNEL_NAME']

XBt_TO_XBT = 100000000
ROUNDING_DIGITS = 6

level = logging.DEBUG
script_name = 'telegram.bot'

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', level=level)
logger = logging.getLogger(script_name)
logfolder = efsfolder + '/log/'
try:
    os.stat(efsfolder)
except:
    os.mkdir(efsfolder)

try:
    os.stat(logfolder)
except:
    os.mkdir(logfolder)
log_filename = logfolder + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
coloredlogs.install(level=level)

# last command to perform with OTP auth
last_command = None
last_args = None

# TODO: table definitions
if not db_engine.dialect.has_table(db_engine, useraccounts_table):
    logger.warn("user accounts table does not exist")
    # Create a table with the appropriate Columns
    useraccounts = Table(useraccounts_table, metadata,
                         Column('ID', Integer, primary_key=True, nullable=False),
                         Column('telegram_ID', Integer),
                         Column('firstname', String(255)), Column('lastname', String(255)),
                         Column('username', String(255)), Column('isadmin', Boolean(), default=False),
                         Column('address', String(40)),
                         Column('withdrawn', BigInteger(), default=0),
                         Column('pending_close', BigInteger(), default=0),
                         Column('last_position_close', DateTime, default=datetime.utcnow())
                         )
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

if not db_engine.dialect.has_table(db_engine, investments_table):
    logger.warn("investments table does not exist")
    mercury_investments = Table(investments_table, metadata,
                                Column('userID', Integer, ForeignKey(useraccounts.c.ID)),
                                Column('timestamp', DateTime, default=datetime.utcnow(),
                                       onupdate=func.utc_timestamp()),
                                Column('value', BigInteger(), default=0),
                                Column('ID', Integer, primary_key=True, autoincrement=True))
    metadata.create_all()
else:
    mercury_investments = Table(investments_table, metadata, autoload=True)

# TODO: load additional tables
unhedge_pnl = Table(unhedge_pnl_table, metadata, autoload=True)
mm_pnl = Table(mm_pnl_table, metadata, autoload=True)
mercury_tc = Table(tc_table, metadata, autoload=True)
mercury_fees = Table(fees_table, metadata, autoload=True)
mercury_hold_balance = Table(hold_balance_table, metadata, autoload=True)
updater = Updater(token=TELEGRAM_BOT_TOKEN)
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
        user_telegram_ID = userfrom.id
        firstname = userfrom.first_name
        lastname = userfrom.last_name
        username = userfrom.username

        stm = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
        rs = con.execute(stm)
        response = rs.fetchall()
        isadmin = False
        message = None
        keyboard = []
        address = None
        XMLRPCServer_bitcoinj = get_bitcoinj_XMLRPC()

        # TODO: new user
        if len(response) == 0:
            # user not found in db
            logger.debug("user not found in db, creating new user %s" % userfrom)
            try:
                address = XMLRPCServer_bitcoinj.getNewAddress()
                ins = useraccounts.insert().values(telegram_ID=user_telegram_ID, firstname=firstname, lastname=lastname,
                                                   username=username,
                                                   isadmin=False, address=address, withdrawn=0)
                con.execute(ins)
                user_DB_ID, last_position_close = get_DB_user_ID(con, user_telegram_ID)
                select_positions = select([positions]).order_by(desc(positions.c.timestamp))
                rs = con.execute(select_positions).fetchall()
                if len(rs) != 0:
                    max_pos_timestamp = rs[0].timestamp
                else:
                    max_pos_timestamp = datetime.utcnow()
                ins = positions.insert().values(userID=user_DB_ID, position=0, timestamp=max_pos_timestamp)
                con.execute(ins)
                ins = log.insert().values(userID=user_DB_ID, log='new user created % s' % (username or firstname),
                                          timestamp=datetime.utcnow())
                con.execute(ins)
                logger.debug(_("HELLO_NEW_USER") + "\n")
                logger.debug((username or firstname))
                message = _("HELLO_NEW_USER") % (username or firstname) + "\n"
                if TEST_MODE:
                    message += _("BOT_IN_TESTING") + "\n"
                message += _("NEW_USER_INFO") + ":\n"
                notify_action = "New user created as"
                notify_user_action(bot, notify_action, user_telegram_ID)
            except:
                logger.error(traceback.format_exc())
                message = "Failed to create new user"
                notify_action = "*Error:* failed to create user as"
                notify_user_action(bot, notify_action, user_telegram_ID)
        # TODO: existing user
        else:
            # user found in DB
            for u in response:
                isadmin = u.isadmin == 1
                logger.debug("user found in db, admin: %s" % isadmin)
            user_DB_ID = response[0].ID
            last_position_close = response[0].last_position_close
            ins = log.insert().values(userID=user_DB_ID, log='user /start', timestamp=datetime.utcnow())
            con.execute(ins)

            if isadmin:
                message = _("WELCOME_BACK_ADMIN") % (
                    (username or firstname), emoji.emojize(':purple_heart:', use_aliases=True)) + "\n"
            else:
                message = _("WELCOME_BACK_USER") % (
                    (username or firstname), emoji.emojize(':currency_exchange:', use_aliases=True)) + "\n"
            # get position
            position = get_latest_user_position(con, last_position_close, user_DB_ID)
            address = response[0].address
            withdrawn = response[0].withdrawn
            pending_close = response[0].pending_close

            try:
                logger.debug("address %s" % (address))
                logger.debug("absent %s" % (address == '0'))
                logger.debug("withdrawn %s" % (withdrawn))
                if address == '0':
                    address = XMLRPCServer_bitcoinj.getNewAddress()
                    ins = useraccounts.update().values(address=address).where(useraccounts.c.ID == user_DB_ID)
                    con.execute(ins)
                try:
                    inp_value = XMLRPCServer_bitcoinj.getInputValue(address)
                except:
                    inp_value = 0

                balance = inp_value - withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                try:
                    unconfirmedTXs = XMLRPCServer_bitcoinj.getUnconfirmedTransactions(address)
                except:
                    unconfirmedTXs = []
                    logger.debug("unconfirmed: %s" % unconfirmedTXs)

                balance = int(balance) / XBt_TO_XBT

                new_mail = select([mail]).where(mail.c.userID == user_DB_ID).where(mail.c.read == False).order_by(
                    desc(mail.c.timestamp))
                mail_rs = con.execute(new_mail).fetchall()
                for m in mail_rs:
                    message += _("NEW_MAIL") % (emoji.emojize(':email:', use_aliases=True)) + "\n%s\n" % m.mail

                upd = mail.update().values(read=True).where(
                    mail.c.userID == user_DB_ID)
                con.execute(upd)

                unapproved_actions = select([actions]).where(actions.c.userID == user_DB_ID).where(
                    actions.c.approved == None)
                actions_rs = con.execute(unapproved_actions).fetchall()

                close_request = False
                invest_request = False
                for a in actions_rs:
                    if a.action == 'INVEST':
                        message += "\n" + _("WAITING_TO_APPROVE_INVEST") + "\n\n"
                        invest_request = True
                    elif a.action == 'CLOSE':
                        message += "\n" + _("WAITING_TO_APPROVE_CLOSE") + "\n\n"
                        close_request = True
                else:
                    if position:
                        position = int(position) / XBt_TO_XBT
                        message += _("YOUR_PORTFOLIO_WORTH") % position + "\n"
                        if not close_request:
                            keyboard += [[InlineKeyboardButton(
                                text=_("CLOSE_REQUEST") % (
                                    emoji.emojize(':arrow_heading_down:', use_aliases=True)),
                                callback_data='/close_position')]]

                    if pending_close > 0:
                        message += _("PENDING_CLOSE") % (pending_close / XBt_TO_XBT) + "\n"
                    if balance == 0:
                        if TEST_MODE:
                            message += _("BOT_IN_TESTING") + "\n"
                        message += _("WALLET_EMPTY") % emoji.emojize(':o:', use_aliases=True) + "\n"
                    else:
                        message += _("YOUR_BALANCE_IS") % (balance) + "\n"

                    for tx in unconfirmedTXs:
                        message += _("PENDING_TRANSACTION") % (int(tx['value']) / XBt_TO_XBT) + "\n"
                        message += _("TX_ID") % (tx['ID'], BLOCK_EXPLORER, tx['ID']) + "\n"
                        # save unconfirmed TX
                        select_txs = select([bitcoinj_transactions]).where(
                            bitcoinj_transactions.c.TXID == tx['ID']).where(bitcoinj_transactions.c.confirmed == False)
                        txs = con.execute(select_txs).fetchall()
                        if len(txs) == 0:
                            ins = bitcoinj_transactions.insert().values(userID=user_DB_ID, TXID=tx['ID'],
                                                                        value=int(tx['value']), direction='IN',
                                                                        confirmed=False, timestamp=datetime.utcnow())
                            con.execute(ins)

                    if (len(unconfirmedTXs) == 0) and (balance > 0) and not invest_request:
                        message += _("IF_YOU_AGREE_TO_INVEST") + "\n"
                        keyboard += [[InlineKeyboardButton(
                            text=_("OK_AGREE") % (
                                emoji.emojize(':ok_hand:', use_aliases=True)),
                            callback_data='/invest')]]
                        address = None
                    elif address:
                        message += _("YOUR_ADDRESS_IS") % (
                            emoji.emojize(':arrow_heading_down:', use_aliases=True)) + "\n"

            except Exception as e:
                logger.error(e)
                logger.error(traceback.format_exc())
                log_event = 'balance unavailable'
                log_record(log_event, update)
                message += _("BALANCE_UNAV") + "\n"
                keyboard += [[InlineKeyboardButton(
                    text=_("SUPPORT_BUTTON") % (
                        emoji.emojize(':warning:', use_aliases=True)),
                    callback_data='/contact')]]
                notify_action = "*Error:* Balance is unavailable"
                notify_user_action(bot, notify_action, user_telegram_ID)

    return address, isadmin, keyboard, message


def get_bitcoinj_XMLRPC():
    XMLRPCServer_bitcoinj = xmlrpc.client.ServerProxy('http://' + bitcoinj_host + ':' + bitcoinj_port)
    return XMLRPCServer_bitcoinj


def get_latest_user_position(con, last_position_close, user_DB_ID):
    select_positions = select([positions]).where(positions.c.userID == user_DB_ID).where(
        positions.c.timestamp >= last_position_close).order_by(
        desc(positions.c.timestamp))
    rs = con.execute(select_positions)
    response2 = rs.fetchall()
    try:
        position = response2[0].position
    except Exception as e:
        logger.error("position error: %e")
        position = 0
    return position


def get_DB_user_ID(con, user_telegram_ID):
    stm = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
    rs = con.execute(stm)
    response_ID = rs.fetchall()
    user_DB_ID = response_ID[0].ID
    last_position_close = response_ID[0].last_position_close
    return user_DB_ID, last_position_close


def get_telegram_user_ID(con, user_DB_ID):
    stm = select([useraccounts]).where(useraccounts.c.ID == user_DB_ID)
    rs = con.execute(stm)
    response_ID = rs.fetchall()
    user_telegram_ID = response_ID[0].telegram_ID
    return user_telegram_ID


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
    user_telegram_ID = get_userID(update)
    with db_engine.connect() as con:
        user_DB_ID, last_position_close = get_DB_user_ID(con, user_telegram_ID)
        ins = log.insert().values(userID=user_DB_ID, log=log_event, timestamp=datetime.utcnow())
        con.execute(ins)
    return user_telegram_ID


def get_userID(update):
    userfrom = update.effective_user
    logger.debug("userfrom : %s" % userfrom)
    user_telegram_ID = userfrom.id
    return user_telegram_ID


def getBTCPrice():
    try:
        BITSTAMP_URL = 'https://www.bitstamp.net/api/ticker/'
        r = requests.get(url=BITSTAMP_URL)
        j = r.json()
        btc_price = float(j['high'])
    except Exception as e:
        logger.error(e)
        btc_price = 11000
    return btc_price


# TODO: statistics
def stats(bot, update):
    chat_id = get_chat_id(update)
    log_event = 'hedge fund stats checked'
    user_telegram_ID = log_record(log_event, update)
    btc_price = getBTCPrice()
    logger.debug("BTC price %s" % btc_price)

    # separate procedure to reuse
    logger.debug("getting balance DF")
    df = pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')

    df_mean = df.groupby(df.timestamp.dt.date)['totalbalance'].mean()
    df_groupped = df_mean

    # pd.rolling_mean(df_mean, min(15, len(df_mean) // 6 ))
    df_groupped = df_groupped.dropna()
    # logger.debug(df_groupped)

    # df_projected = df.groupby(df.timestamp.dt.date)['projectedbalance'].mean()
    logger.debug('stats processed')
    '''
    with db_engine.connect() as con:
        user_DB_ID, last_position_close = get_DB_user_ID(con, user_telegram_ID)
        logger.debug("user ID %s last_position_close %s" % (user_DB_ID, last_position_close))
        get_user_portfolio_stats(btc_price, bot, chat_id, user_DB_ID, last_position_close, df_groupped, con)


    message = _("COMBINED_STATS") + "\n\n"
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=ReplyKeyboardRemove())

    send_stats2(bot, df_groupped, chat_id, label='Absolute portfolio value, BTC', pic_ix='1_')
    balance_profit = df_groupped[-1] - df_groupped[0]
    timedelta = df_groupped.index[-1] - df_groupped.index[0]
    yearly_pc = ((balance_profit / timedelta.days) * 365) / df_groupped[0] * 100
    t_diff = monthdelta(df_groupped.index[0], df_groupped.index[-1])
    month_diff = t_diff[0]
    d_diff = t_diff[1]
    absolute_profit_pc = (balance_profit / df_groupped[0]) * 100
    # message = _("CS_WHICH_IS") % yearly_pc + "\n\n"
    message = _("CS_CURRENT_VALUE") % df_groupped[-1] + "\n"
    message += _("EQUALS_TO") % (df_groupped[-1] * btc_price, btc_price) + "\n"

    # message = _("CS_GREW_UP") % balance_profit + "\n\n"
    # message += _("CS_WAS_ACHIEVED") % (month_diff, d_diff) + "\n"
    message += _("CS_RUNNING_TIME") % (month_diff, d_diff) + "\n"
    # message += _("CS_ABSOLUTE_PROFIT_PC") % absolute_profit_pc + "\n\n"
    # message += _("CS_IF_INVESTED") % (
    #    df_groupped.index[0].strftime("%d %b"), (balance_profit / df_groupped[0]) + 1) + "\n"
    # message += _("CS_ABS_PROFIT") % (balance_profit / df_groupped[0]) + "\n"
    # message += _("EQUALS_TO") % ((balance_profit / df_groupped[0]) * btc_price, btc_price) + "\n"
    keyboard = back_button
    logger.debug('exiting stats')
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(
                         inline_keyboard=keyboard))

    '''

# TODO: user portfolio stats
def get_user_portfolio_stats(btc_price, bot, chat_id, user_DB_ID, last_position_close, portfolio_df, con):
    position = get_latest_user_position(con, last_position_close, user_DB_ID)
    logger.debug("position: %s" % position)

    if position > 0:
        balance_profit, df_groupped = get_user_balance_profit(user_DB_ID)
        logger.debug("balance_profit: %s" % balance_profit)
        message = _("YOUR_FOLIO_PERFORMANCE")
        if TEST_MODE:
            message += "\n" + _("TESTING_STATS") + "\n"
        bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                         reply_markup=ReplyKeyboardRemove())

        logger.debug("sending portfolio value")
        send_stats2(bot, df_groupped / XBt_TO_XBT, chat_id, label="Current portfolio value, BTC", pic_ix='2_')
        t_diff = monthdelta(df_groupped.index[0], df_groupped.index[-1])
        month_diff = t_diff[0]
        d_diff = t_diff[1]
        message = _("WAS_OPENED_AGO") % (month_diff, d_diff) + "\n"
        # logger.debug(message)
        inv_select = select([mercury_investments]).where(mercury_investments.c.userID == user_DB_ID)
        rs = con.execute(inv_select)
        investments = rs.fetchall()

        message += _("YOUVE_INVESTED") + "\n\n"
        # logger.debug(message)
        total_investments = 0
        no_inv = 0
        for i in investments:
            message += _("YOUVE_INVESTED_ON") % ((i.value / XBt_TO_XBT), i.timestamp.strftime("%d %b %Y")) + "\n"
            no_inv += 1
            total_investments += (i.value / XBt_TO_XBT)
        if no_inv > 1:
            message += "---\n"
            message += _("TOTAL_INVESTED") % total_investments + "\n"

        message += "\n"
        # current_value = None
        current_value = df_groupped[-1] / XBt_TO_XBT
        message += _("NOW_WORTH") % (current_value) + "\n"
        logger.debug(message)
        if balance_profit > 0:
            message += _("ABS_RETURN") % (balance_profit) + "\n"
            message += _("EQUALS_TO") % (balance_profit * btc_price, btc_price) + "\n"
            timedelta = df_groupped.index[-1] - df_groupped.index[0]
            yearly_pc = (((balance_profit / timedelta.days) * 365) / (df_groupped[0] / XBt_TO_XBT)) * 100
            message += _("CS_WHICH_IS") % yearly_pc + "\n\n"
        try:
            XMLRPCServer_mercurybot = getBotXMLRPC()
            pnlminpnl = XMLRPCServer_mercurybot.pnlminpnl()
            pnlminpnl = json.loads(pnlminpnl)
            projected_profit = float(pnlminpnl['minpnl']) - float(pnlminpnl['pnl'])
            max_days = int(pnlminpnl['max_daysleft'])
            swing = float(pnlminpnl['swing'])
        except Exception as e:
            logger.error("shit happened here:")
            logger.error(e)
            logger.error(traceback.format_exc())
            swing = None
            max_days = None
            projected_profit = None

        portfolio_share = current_value / portfolio_df[-1]
        logger.debug("portfolio share: %.8f" % portfolio_share)

        # pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')
        df = pd.read_sql_query(
            sql='SELECT * FROM ' + balance_table + ' WHERE `TIMESTAMP` > (SELECT LAST_POSITION_CLOSE from ' + useraccounts_table + ' WHERE `ID`= ' + str(
                user_DB_ID) + ')', con=db_engine, index_col='index')

        df = df[(df.projectedbalance >= (df_groupped[0] / XBt_TO_XBT))]
        df_projected = df.groupby(df.timestamp.dt.date)['projectedbalance'].mean()

        try:
            df_projected = df_projected * portfolio_share
        except Exception as e:
            logger.error(e)
            logger.error(traceback.format_exc())

        # df_projected = df_projected[(df_projected != 0)]
        # df_projected = df_projected[(df_projected >= (df_groupped[0] / XBt_TO_XBT))]
        logger.debug("sending stats 2")
        if len(df) > 2:
            send_stats2(bot, df_projected, chat_id, label='Projected portfolio value, BTC', pic_ix='3_')


        if projected_profit and current_value:
            # is a chunk of a whole projected profit
            projected_profit = portfolio_share * (projected_profit)
            projected_value = current_value + projected_profit
            message += _("PROJECTED_PROFIT") % projected_profit + "\n"
            message += _("PROJECTED_VALUE") % projected_value + "\n"
            # projected_pc = (projected_value - (df_groupped[0] / XBt_TO_XBT)) / (df_groupped[0] / XBt_TO_XBT) * 100
            # message += _("PROJECTED_VALUE_PC") % projected_pc + "\n"

        if max_days:
            message += _("MAX_DAYS") % max_days + "\n"

        if swing:
            message += _("CURRENT_SWING") % swing + "\n"

        logger.debug("getting fees")
        admin_fee, early_fee, withdrawal_fees = get_user_fees(user_DB_ID, balance_profit, con)
        message += "\n" + _("YOUR_FEES") % (admin_fee, early_fee, withdrawal_fees) + "\n"

        logger.debug("sending message:\n %s" % message)
        bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                         reply_markup=ReplyKeyboardRemove())


def get_user_balance_profit(user_DB_ID):
    # logger.debug("GUP")
    df = pd.read_sql_query(sql='SELECT * FROM ' + positions_table + ' WHERE `USERID` = ' + str(
        user_DB_ID) + ' AND `TIMESTAMP` > (SELECT LAST_POSITION_CLOSE from ' + useraccounts_table + ' WHERE `ID`= ' + str(
        user_DB_ID) + ')', con=db_engine, index_col='timestamp')

    df = df[(df.position != 0)]
    df_groupped = df.groupby(df.index)['position'].mean()

    # df_groupped = df[(df.position != 0)]['position']

    balance_profit = 0

    with db_engine.connect() as con:
        inv_select = select([mercury_investments]).where(mercury_investments.c.userID == user_DB_ID)

        rs = con.execute(inv_select)
        investments = rs.fetchall()

        invested_value = 0
        for i in investments:
            invested_value += i.value
        balance_profit = (df_groupped[-1] - invested_value) / XBt_TO_XBT

    # logger.debug(df_groupped)
    return balance_profit, df_groupped


def get_user_fees(user_DB_ID, balance_profit, con):
    admin_fee = balance_profit * float(settings.ADMIN_FEE)
    logger.debug("Balance profit %.8f" % balance_profit)
    admin_fee = max(0, admin_fee)
    logger.debug("Admin fee %.8f" % admin_fee)
    select_fees = select([mercury_fees]).where(mercury_fees.c.userID == user_DB_ID).order_by(
        desc(mercury_fees.c.timestamp))
    rs = con.execute(select_fees).fetchall()
    early_fee = rs[0].early_fee / XBt_TO_XBT
    withdrawal_fees = rs[0].withdrawal_fees / XBt_TO_XBT
    logger.debug("Withdrawal fee %.8f" % withdrawal_fees)
    return round(admin_fee, ROUNDING_DIGITS), round(early_fee, ROUNDING_DIGITS), round(withdrawal_fees,
                                                                                       ROUNDING_DIGITS)  # send % return stats


def send_stats(bot, df_groupped, chat_id):
    if len(df_groupped) > 0:
        # daily_pc = df_groupped.pct_change().dropna() * 365 * 100
        cumulative_pc = ((df_groupped - df_groupped.ix[0]) / df_groupped.ix[0]) * 100

        plot_graph(cumulative_pc, pic_2_filename, 'Return On Investment, %')
        picture_2 = open(pic_folder + '/' + pic_2_filename, 'rb')
        keyboard = ReplyKeyboardRemove()
        bot.send_photo(chat_id=chat_id, photo=picture_2,
                       reply_markup=keyboard)


# send absolute profit stats
def send_stats2(bot, df_groupped, chat_id, label='Absolute growth, BTC', pic_ix='1_'):
    if len(df_groupped) > 0:
        df_groupped = pd.rolling_mean(df_groupped, min(len(df_groupped) // 10, 100))
        df_groupped = df_groupped.dropna()
        # daily_pc = df_groupped.pct_change().dropna() * 365 * 100
        # cumulative_pc = ((df_groupped - df_groupped.ix[0]) / df_groupped.ix[0]) * 100
        # logger.debug(df_groupped)
        if len(df_groupped) > 0:
            plot_graph(df_groupped, pic_ix + pic_2_filename, label)
            picture_2 = open(pic_folder + '/' + pic_ix + pic_2_filename, 'rb')
            logger.debug(picture_2.name)
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
    logger.debug("last command: %s args: %s" % (last_command, last_args))
    message = None

    if last_command == 'BW' and last_args > 0.05:
        logger.debug("Bitmex Withdraw")
        try:
            bitmex = get_bitmex()
            result = bitmex.withdraw(amount=last_args * XBt_TO_XBT, address=POLO_ADDRESS, otptoken=OTP)
            logger.debug(result)
        except Exception as e:
            result = e
        if 'error' in result:
            message = result['error']['message']
        elif 'transactID' in result:
            message = 'BitMEX -> Polo transfer created\nID: *%s*' % result['transactID']
        else:
            message = str(result)
    elif last_command == 'PW' and last_args > 0.05:
        logger.debug("Poloniex Withdraw")
        try:
            polo = get_poloniex()
            result = polo.withdraw(currency="BTC", address=BITMEX_ADDRESS, amount=last_args)
            logger.debug(result)
            if 'response' in result:
                message = result['response']
        except Exception as e:
            logger.error(e)
            message = str(e)

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
    user_telegram_ID = get_userID(update)
    message = "\n" + _("SUPPORT_REQUEST_SENT") + "\n"
    bot.answerCallbackQuery(callback_query_id=query.id, text=message, show_alert=True)

    with db_engine.connect() as con:
        user_DB_ID, last_position_close = get_DB_user_ID(con, user_telegram_ID)
        msg_to_user = '\n' + _("SUPPORT_REQUEST_SENT") + "\n"
        ins = mail.insert().values(userID=user_DB_ID, read=False, mail=msg_to_user, timestamp=datetime.utcnow())
        con.execute(ins)
        user_select = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
        rs = con.execute(user_select).fetchall()
        username = rs[0].username
        firstname = rs[0].firstname
    # keyboard = back_button
    notify_action = "*Support request*"
    notify_user_action(bot, notify_action, user_telegram_ID)
    start(bot, update)


# TODO: close position
def close_position(bot, update):
    chat_id = get_chat_id(update)
    log_event = 'Close position request is sent'
    user_telegram_ID = log_record(log_event, update)
    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
        rs = con.execute(stm).fetchall()
        address = rs[0].address
        username = rs[0].username
        firstname = rs[0].firstname
        withdrawn = rs[0].withdrawn
        user_DB_ID = rs[0].ID
        last_position_close = rs[0].last_position_close
        position = get_latest_user_position(con, last_position_close, user_DB_ID)
        close_actions = select([actions]).where(actions.c.userID == user_DB_ID).where(
            actions.c.action == 'CLOSE').where(actions.c.approved == None)
        close_rs = con.execute(close_actions).fetchall()
        message = None
        if len(close_rs) > 0:
            message = _("YOU_SENT_CLOSE") + "\n"
        else:
            ins = actions.insert().values(userID=user_DB_ID, action='CLOSE', approved=None, args=position / XBt_TO_XBT,
                                          timestamp=datetime.utcnow())
            con.execute(ins)
            message = _("POSITION_CLOSE_SENT") + "\n"
            notify_action = "New position close request"
            notify_user_action(bot, notify_action, user_telegram_ID)

        if message:
            keyboard = back_button
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=keyboard))


# notify admin of the user action
def notify_user_action(bot, notify_action, user_telegram_ID):
    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
        rs = con.execute(stm).fetchall()
        username = rs[0].username
        firstname = rs[0].firstname
        nick = username or firstname
        msg = "([x](tg://user?id=%s)) " % settings.TELEGRAM_ADMIN_USER + notify_action + \
              " from [%s](tg://user?id=%s)\n" % (nick, user_telegram_ID)
        bot.send_message(chat_id=TELEGRAM_CHANNEL_NAME, text=msg, parse_mode='Markdown')


# TODO: invest
def invest(bot, update):
    query = update.callback_query
    chat_id = get_chat_id(update)
    log_event = 'Invest request is sent'
    user_telegram_ID = log_record(log_event, update)
    XMLRPCServer_bitcoinj = get_bitcoinj_XMLRPC()
    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.telegram_ID == user_telegram_ID)
        rs = con.execute(stm).fetchall()
        address = rs[0].address
        username = rs[0].username
        firstname = rs[0].firstname
        withdrawn = rs[0].withdrawn
        user_DB_ID = rs[0].ID
        invest_actions = select([actions]).where(actions.c.userID == user_DB_ID).where(
            actions.c.action == 'INVEST').where(actions.c.approved == None)
        invest_rs = con.execute(invest_actions).fetchall()
        message = None
        if len(invest_rs) > 0:
            message = _("YOU_SENT_INVEST") + "\n"
        else:
            try:
                balance = XMLRPCServer_bitcoinj.getInputValue(address) - withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                if balance > 0:
                    ins = actions.insert().values(userID=user_DB_ID, action='INVEST', args=balance / XBt_TO_XBT,
                                                  approved=None,
                                                  timestamp=datetime.utcnow())
                    con.execute(ins)
                    message = _("YOU_HAVE_AGREED") + "\n"
                    notify_action = "New invest request"
                    notify_user_action(bot, notify_action, user_telegram_ID)
                else:
                    message = _("INSUFFICIENT_BALANCE") + "\n"

            except:
                logger.error(traceback.format_exc())
                notify_action = "Invest request error"
                notify_user_action(bot, notify_action, user_telegram_ID)
        if message:
            keyboard = back_button
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=keyboard))


# TODO: show custom user stats
def user_stats(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    data = update.callback_query.data
    stats_user_DB_ID = str.split(data, "ch")[1]
    btc_price = getBTCPrice()

    df = pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')
    df_groupped = df.groupby(df.timestamp.dt.date)['totalbalance'].mean()
    # df_projected = df.groupby(df.timestamp.dt.date)['projectedbalance'].mean()

    with db_engine.connect() as con:
        stm = select([useraccounts]).where(useraccounts.c.ID == stats_user_DB_ID)
        rs = con.execute(stm)
        response = rs.fetchall()
        last_position_close = response[0].last_position_close
        get_user_portfolio_stats(btc_price, bot, chat_id, stats_user_DB_ID, last_position_close, df_groupped, con)

    message = "^"
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(
                         inline_keyboard=admin_keyboard))


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
        sum_positions = 0
        btc_price = getBTCPrice()
        for u in rs:
            logger.debug(u)
            i += 1
            username = u.username
            firstname = u.firstname
            user_id = u.userID
            position = u.position / XBt_TO_XBT
            sum_positions += position
            telegram_ID = get_telegram_user_ID(con, user_id)
            message = "*%d*: [%s](tg://user?id=%s) *%.6f* BTC (%.2f USD)\n" % (
                i, username or firstname, telegram_ID, position, position * btc_price)

            keyboard = [[InlineKeyboardButton(
                text="%s" % (emoji.emojize(':chart_with_upwards_trend:', use_aliases=True)),
                callback_data=("ch%s" % user_id))]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=reply_markup)

        message = "Total amount: %.2f BTC (%.2f USD)" % (sum_positions, sum_positions * btc_price)
        if message:
            logger.debug(message)
            bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                             reply_markup=InlineKeyboardMarkup(
                                 inline_keyboard=admin_keyboard))


# TODO: show unapproved actions
def unapproved_actions(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return

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
            user_DB_ID = a.userID
            user_telegram_ID = get_telegram_user_ID(con, user_DB_ID)
            action = a.action
            timestamp = a.timestamp
            i = a.actionID
            action_args = a.args
            message = "%d: [%s](tg://user?id=%s) *%s* _%s_ (%s)\n" % (
                i, username or firstname, user_telegram_ID, action, action_args, timestamp.strftime("%d %b %H:%M:%S"))

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
        user_DB_ID = found_action.userID
        with db_engine.connect() as con:
            user_telegram_ID = get_telegram_user_ID(con, user_DB_ID)
        user_address = found_action.address
        user_withdrawn = found_action.withdrawn
        action = found_action.action
        timestamp = found_action.timestamp
        message = "Action *%s* disapproved:\n[%s](tg://user?id=%s) %s (%s)\n" % (
            action_id, username or firstname, user_telegram_ID, action, timestamp.strftime("%d %b %H:%M:%S"))
        logger.debug("%s %s %s" % (action, user_address, user_withdrawn))

        log_record(message, update)
        change_action(action_id=action_id, approved=False)
        msg_to_user = "\n" + _("YOUR_ACTION_DISAPPROVED") + "\n"
        bot.send_message(chat_id=user_telegram_ID, text=msg_to_user, parse_mode='Markdown',
                         reply_markup=InlineKeyboardMarkup(
                             inline_keyboard=back_button))
        with db_engine.connect() as con:
            ins = mail.insert().values(userID=user_DB_ID, read=False, mail=msg_to_user,
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
    action_id = str.split(data, "a")[1]
    found, found_action = find_action(action_id)
    XMLRPCServer_bitcoinj = get_bitcoinj_XMLRPC()
    if found:
        username = found_action.username
        firstname = found_action.firstname
        user_DB_ID = found_action.userID
        with db_engine.connect() as con:
            user_telegram_ID = get_telegram_user_ID(con, user_DB_ID)
        user_address = found_action.address
        user_withdrawn = found_action.withdrawn
        action = found_action.action
        timestamp = found_action.timestamp
        message = "Action *%s* approved:\n[%s](tg://user?id=%s) %s (%s)\n" % (
            action_id, username or firstname, user_telegram_ID, action, timestamp.strftime("%d %b %H:%M:%S"))
        logger.debug("%s %s %s" % (action, user_address, user_withdrawn))
        # TODO: INVEST APPROVE
        if (action == 'INVEST') and user_address:
            logger.debug("invest action started")
            try:
                logger.debug("getting balance")
                balance = XMLRPCServer_bitcoinj.getInputValue(user_address) - user_withdrawn
                logger.debug("balance %.8f" % (balance / XBt_TO_XBT))
                message += 'user balance: %.8f\n' % (balance / XBt_TO_XBT)
                logger.debug("sending to polo")
                if not TEST_MODE:
                    df = pd.read_sql_table(balance_diff_table, con=db_engine, index_col='index')
                    transfer_record = df.to_dict(orient='records')
                    logger.debug(transfer_record)
                    transfer_diff = round(transfer_record[0]['avg_balance_difference'], 6)
                    if transfer_diff > 0:
                        address = settings.POLO_ADDRESS
                    else:
                        address = settings.BITMEX_ADDRESS
                else:
                    address = '2N8hwP1WmJrFF5QWABn38y63uYLhnJYJYTF'

                send_result = XMLRPCServer_bitcoinj.sendCoins(user_address, address, balance)
                logger.debug("sr: %s" % send_result)
                if send_result:
                    tx_id = send_result['TX']
                    tx_value = int(send_result['value'])
                    message += "TX ID: [%s](%s%s)\n" % (tx_id, BLOCK_EXPLORER, tx_id)
                    message += 'TX value: *%s*\n' % tx_value
                    if tx_value > 0:
                        with db_engine.connect() as con:
                            select_positions = select([positions]).where(positions.c.userID == user_DB_ID).order_by(
                                desc(positions.c.timestamp))
                            rs = con.execute(select_positions)
                            response = rs.fetchall()

                            user_position = response[0].position
                            user_pos_timestamp = response[0].timestamp

                            upd = positions.update().values(position=(user_position + tx_value)).where(
                                positions.c.userID == user_DB_ID).where(positions.c.timestamp == user_pos_timestamp)
                            con.execute(upd)
                            upd = useraccounts.update().values(withdrawn=(user_withdrawn + balance)).where(
                                useraccounts.c.ID == user_DB_ID)
                            con.execute(upd)

                            ins = mercury_investments.insert().values(userID=user_DB_ID, value=tx_value,
                                                                      timestamp=datetime.utcnow())
                            con.execute(ins)

                            msg_to_user = "\n" + _("ADDED_TO_PORTFOLIO") % (
                                tx_value / XBt_TO_XBT, (balance - tx_value) / XBt_TO_XBT) + "\n"
                            bot.send_message(chat_id=user_telegram_ID, text=msg_to_user, parse_mode='Markdown',
                                             reply_markup=InlineKeyboardMarkup(
                                                 inline_keyboard=back_button))
                            ins = mail.insert().values(userID=user_DB_ID, read=False, mail=msg_to_user,
                                                       timestamp=datetime.utcnow())
                            con.execute(ins)
                            ins = bitcoinj_transactions.insert().values(userID=user_DB_ID, TXID=tx_id,
                                                                        value=tx_value, direction='OUT',
                                                                        confirmed=True, timestamp=datetime.utcnow())
                            con.execute(ins)

                        change_action(action_id=action_id, approved=True)
                        log_event = 'user: %s tx: %s val %s' % (user_DB_ID, tx_id, tx_value)
                        log_record(log_event, update)

            except Exception as e:
                logger.error(traceback.format_exc())
                logger.error(e)
                message += '*cannot send coins: %s *\n' % str(e)
        elif action == 'CLOSE':
            # TODO: CLOSE APPROVE
            logger.debug("close portfolio action started")
            with db_engine.connect() as con:
                balance_profit, df_groupped = get_user_balance_profit(user_DB_ID)
                logger.debug("profit: %s" % balance_profit)
                admin_fee, early_fee, withdrawal_fees = get_user_fees(user_DB_ID, balance_profit, con)
                total_fees = admin_fee + early_fee + withdrawal_fees
                logger.debug("fees: %s" % total_fees)
                position = df_groupped[-1]
                logger.debug("position: %s" % (position / XBt_TO_XBT))
                withdraw_amount = position - (total_fees * XBt_TO_XBT)
                if withdraw_amount > 0:
                    # get max timestamp
                    select_positions = select([positions]).where(positions.c.userID == user_DB_ID).order_by(
                        desc(positions.c.timestamp))
                    rs = con.execute(select_positions)
                    response = rs.fetchall()
                    user_pos_timestamp = response[0].timestamp
                    # reset current position
                    upd = positions.update().values(position=0).where(
                        positions.c.userID == user_DB_ID).where(positions.c.timestamp == user_pos_timestamp)
                    con.execute(upd)
                    # save pending withdraw amount
                    upd = useraccounts.update().values(pending_close=(int(withdraw_amount))).where(
                        useraccounts.c.ID == user_DB_ID)
                    con.execute(upd)
                    # updating hold balance
                    select_hold_balance = select([mercury_hold_balance]).order_by(
                        desc(mercury_hold_balance.c.timestamp))
                    rs = con.execute(select_hold_balance).fetchall()
                    hold_balance = rs[0].hold_balance.__float__()
                    hold_balance += float(round((withdraw_amount / XBt_TO_XBT), ROUNDING_DIGITS))
                    ins = mercury_hold_balance.insert().values(hold_balance=hold_balance, index=datetime.utcnow())
                    con.execute(ins)
                    # message to user
                    msg_to_user = "\n" + _("POSITION_PENDING_WITHDRAW") % (
                        withdraw_amount / XBt_TO_XBT, admin_fee / XBt_TO_XBT, early_fee / XBt_TO_XBT,
                        withdrawal_fees / XBt_TO_XBT) + "\n"
                    bot.send_message(chat_id=user_telegram_ID, text=msg_to_user, parse_mode='Markdown',
                                     reply_markup=InlineKeyboardMarkup(
                                         inline_keyboard=back_button))
                    ins = mail.insert().values(userID=user_DB_ID, read=False, mail=msg_to_user,
                                               timestamp=datetime.utcnow())
                    con.execute(ins)
                    change_action(action_id=action_id, approved=True)

        # TODO: SUPPORT APPROVE
        elif action == 'SUPPORT':
            with db_engine.connect() as con:
                msg_to_user = 'Support request received!'
                ins = mail.insert().values(userID=user_DB_ID, read=False, mail=msg_to_user, timestamp=datetime.utcnow())
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


# TODO: get wallet_balance
def wallet_balance(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    XMLRPCServer_bitcoinj = get_bitcoinj_XMLRPC()
    try:
        balance = XMLRPCServer_bitcoinj.getWalletBalance()
        message = "Balance %.8f BTC" % (balance / XBt_TO_XBT)
    except Exception as e:
        message = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')


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
        bitmex = get_bitmex()
        result = bitmex.min_withdrawal_fee()
        logger.debug(result)
        fee = result['minFee'] / XBt_TO_XBT
    else:
        direction = '<-'
        last_command = 'PW'
        last_args = abs(transfer_diff)
        polo = get_poloniex()
        currencies = polo.returnCurrencies()
        fee = currencies['BTC']['txFee']

    message = "_BitMEX_ %s _Poloniex_ *%.6f*\n" % (direction, abs(transfer_diff))
    message += "_Fee is:_ *%s*\n" % (fee)
    message += "_Current UTC now is_ *%s*\n" % (datetime.utcnow().strftime("%H:%M:%S"))
    message += "send OTP to confirm or 0 to cancel"
    bot.send_message(chat_id=chat_id, text=message, reply_markup=ReplyKeyboardRemove(),
                     parse_mode='Markdown')


def get_bitmex():
    bitmex = BitMEX(apiKey=B_KEY, apiSecret=B_SECRET, base_url=BASE_URL, logger=logger)
    return bitmex


def get_poloniex():
    myCoach = poloniex.Coach(callLimit=1)
    polo = poloniex.Poloniex(coach=myCoach, key=settings.P_API_KEY, secret=settings.P_API_SECRET, timeout=180)
    return polo


def get_chat_id(update):
    try:
        chat_id = update.message.chat_id
    except:
        query = update.callback_query
        chat_id = query.message.chat_id
    return chat_id


# TODO: request unhedge
def request_trade(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    chat_id = get_chat_id(update)
    command = update.message.text
    try:
        t, market, symbol, side, amount, marginal = command.split('_')
    except ValueError:
        t, market, symbol, side, amount = command.split('_')
        marginal = 'n'

    log_event = 'Requested to trade: %s' % command
    user_telegram_ID = log_record(log_event, update)
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        result = XMLRPCServer_mercurybot.trade(market, symbol, side, amount, marginal)
        logger.debug(result)
        message = "trade result: %s" % result
    except Exception as e:
        message = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')


# TODO: request unhedge
def request_unhedge(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    chat_id = get_chat_id(update)
    command = update.message.text
    unhedge_amount = float(str.split(command, "u")[1])
    log_event = 'Requested for unhedge: %s' % unhedge_amount
    user_telegram_ID = log_record(log_event, update)
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        result = XMLRPCServer_mercurybot.request_unhedge(unhedge_amount)
        result = json.loads(result)
        logger.debug(result)

        sum_btc = result['sum_btc']
        sum_pnl = result['sum_pnl']
        count = result['count']

        message = "*%d* orders, %.6f _BTC_ sum PNL, %6f _BTC_ value" % (count, sum_pnl, sum_btc)
    except Exception as e:
        message = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')


# TODO: update hold balance
def hold_balance_update(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    chat_id = get_chat_id(update)
    command = update.message.text
    hold_balance = float(str.split(command, "h")[1])
    log_event = 'New hold balance: %s' % hold_balance
    user_telegram_ID = log_record(log_event, update)
    with db_engine.connect() as con:
        select_hold_balance = select([mercury_hold_balance]).order_by(desc(mercury_hold_balance.c.timestamp))
        rs = con.execute(select_hold_balance).fetchall()
        hold_loan = rs[0].hold_loan.__float__()
        ins = mercury_hold_balance.insert().values(index=getUTCtime(), hold_balance=hold_balance, hold_loan=hold_loan)
        con.execute(ins)
    message = "Updated hold balance as *%s*\n" % hold_balance
    message += "Hold loan balance is *%s*\n" % hold_loan
    bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')


# TODO: update hold loan balance
def hold_loan_balance_update(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    chat_id = get_chat_id(update)
    command = update.message.text
    hold_loan_balance = float(str.split(command, "l")[1])
    log_event = 'New hold loan balance: %s' % hold_loan_balance
    user_telegram_ID = log_record(log_event, update)
    with db_engine.connect() as con:
        select_hold_balance = select([mercury_hold_balance]).order_by(desc(mercury_hold_balance.c.timestamp))
        rs = con.execute(select_hold_balance).fetchall()
        hold_balance = rs[0].hold_balance.__float__()
        ins = mercury_hold_balance.insert().values(index=getUTCtime(), hold_balance=hold_balance,
                                                   hold_loan=hold_loan_balance)
        con.execute(ins)
    message = "Updated hold loan balance as *%s*\n" % hold_loan_balance
    message += "Hold balance is *%s*\n" % hold_balance
    bot.send_message(chat_id=chat_id, text=message, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')


# TODO: show hold balance
def show_hold_balance(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    try:
        with db_engine.connect() as con:
            select_hold_balance = select([mercury_hold_balance]).order_by(desc(mercury_hold_balance.c.timestamp))
            rs = con.execute(select_hold_balance).fetchall()
            hold_balance = rs[0].hold_balance.__float__()
            hold_loan = rs[0].hold_loan.__float__()
            message = "Current hold balance: *%.2f* BTC\n" % hold_balance
            message += "Current hold loan balance: *%.2f* BTC\n" % hold_loan
            message += "_Type hx.x to update hold balance\n_"
            message += "_Type lx.x to update loan hold balance\n_"
    except Exception as e:
        message = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=message, reply_markup=ReplyKeyboardRemove(),
                     parse_mode='Markdown')


# TODO: cheapest
def cheapest(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        cheapest_trading_pairs = XMLRPCServer_mercurybot.cheapest_pairs()
        cheapest_trading_pairs = json.loads(cheapest_trading_pairs)
        logger.debug(cheapest_trading_pairs)
        message = ""
        sum_orders = 0
        for p in cheapest_trading_pairs:
            order_symbol = p['symbol']
            order_qty = p['orderQty']
            order_price = p['price']
            partial_pnl = p['partial_pnl']
            btc_value = order_qty * order_price
            sum_orders += btc_value
            message += "_%s_ %d PNL: *%.6f* V: *%.6f* _BTC_\n" % (order_symbol, order_qty, partial_pnl, btc_value)
        message += "Sum: *%.6f* _BTC_\n" % (sum_orders)
        message += "_Type ux.x to request unhedge for x.x BTC\n_"
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(e)
        message = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=message, reply_markup=ReplyKeyboardRemove(),
                     parse_mode='Markdown')


# TODO: pairs
def pairs(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        trading_pairs = XMLRPCServer_mercurybot.pairs()
        trading_pairs = json.loads(trading_pairs)
        logger.debug(trading_pairs)
        NoErrors = True
        for p in trading_pairs:
            response = ""
            response += "*%s:* pnl: %.4f min: %.4f vol: %.4f T: %s \n" % (
                p, trading_pairs[p]['pnl'], trading_pairs[p]['minpnl'], trading_pairs[p]['total_amount'],
                trading_pairs[p]['trading'])
            if trading_pairs[p]['future_qty'] - (
                            trading_pairs[p]['volume_to_spot_hedge'] + trading_pairs[p]['volume_to_spread_hedge'] +
                        trading_pairs[p]['spot_hedged']) != 0:
                response += "*not hedged correctly*\n"
                response += "*F:* %s\n" % trading_pairs[p]['future_qty']
                response += "*H:* %s\n" % trading_pairs[p]['volume_to_spread_hedge']
                response += "*SH:* %s\n" % trading_pairs[p]['volume_to_spot_hedge']
                response += "*S:* %s\n" % trading_pairs[p]['spot_hedged']

                NoErrors = False
            try:
                b_position = trading_pairs[p]['b_position']
                p_position = trading_pairs[p]['p_position']

                if (b_position == 0) and (p_position == 0):
                    continue

                df = pd.read_sql_table(p + '_future', con=db_engine)
                df = df.drop_duplicates()
                fh = df.to_dict(orient='records')

                df = pd.read_sql_table(p + '_spot', con=db_engine)
                df = df.drop_duplicates()
                sh = df.to_dict(orient='records')
                side_a = 'F'
                side_b = 'S'
                cf = 1 - 0.0025

                sum_future = 0

                nl = 0
                response += ("%s  - > %s \n" % (side_b, side_a))
                for s in fh:  # future
                    found = False
                    sum_spot = 0
                    for s2 in sh:  # spot
                        if s2['hedgeID'] == s['ID']:
                            sum_spot += float(s2['amount']) * cf
                            found = True
                    if not found:
                        response += ("*f hedge %s not linked ,q: %d* \n" % (s['ID'], s['orderQty']))
                        nl += s['orderQty']
                    else:
                        sum_future += float(s['orderQty'])

                    sum_spot = round(sum_spot)
                    if s['orderQty'] < sum_spot:
                        response += ("*problem with %s* \n" % s['ID'])
                        response += (
                            "*f %s f %d / s_s %d = %d*\n" % (
                                s['ID'], s['orderQty'], sum_spot, sum_spot - s['orderQty']))

                response += ("sum %s: %.2f\n" % (side_a, sum_future))
                if nl > 0:
                    response += ("nl: %d\n" % nl)

                sum_spot = 0
                sum_spot_disount = 0
                response += ("_%s  - > %s_\n" % (side_a, side_b))
                for s in sh:
                    found = False
                    for s2 in fh:
                        if s['hedgeID'] == s2['ID']:
                            found = True
                    if not found:
                        response += ("*s hedge %s not linked*\n" % s['hedgeID'])
                    else:
                        vol = float(s['amount'])
                        sum_spot += vol
                        sum_spot_disount += vol * cf
                response += ("sum %s: %.2f / %.2f\n" % (side_b, sum_spot, sum_spot_disount))

                hedge_vol = trading_pairs[p]['hedge_vol']
                balance_diff = abs(b_position - math.copysign(p_position, b_position)) - hedge_vol
                if balance_diff != 0:
                    response += "*Not correctly hedged:* b: %s h: %s p: %s\n" % (
                        b_position, hedge_vol, p_position)
                    diff_f = sum_future - (abs(b_position) - hedge_vol)
                    diff_s = sum_spot_disount - abs(p_position)
                    response += "*F diff: %d S diff: %d*" % (diff_f, diff_s)
                    NoErrors = False
                else:
                    response += "_Correctly hedged_\n"
            except Exception as e:
                response = e
            logger.debug(response)
            bot.send_message(chat_id=chat_id, text=response, reply_markup=ReplyKeyboardRemove(),
                             parse_mode='Markdown')

        response = "*Errors detected*"
        if NoErrors:
            response = "*No errors detected*"
        bot.send_message(chat_id=chat_id, text=response,
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                         parse_mode='Markdown')

    except Exception as e:
        response = "Could not initiate: %s" % e
        bot.send_message(chat_id=chat_id, text=response,
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                         parse_mode='Markdown')
        return


# TODO: bot restart
def restart(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        XMLRPCServer_mercurybot.restart()
        response = "Restart initiated"
    except Exception as e:
        response = "Could not initiate: %s" % e
    bot.send_message(chat_id=chat_id, text=response, reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                     parse_mode='Markdown')
    return


# TODO: health
def health_check(bot, update):
    chat_id = get_chat_id(update)
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    message = ''
    '''
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
    '''
    try:
        XMLRPCServer_mercurybot = getBotXMLRPC()
        health = XMLRPCServer_mercurybot.health()
        health_record = json.loads(health)
        healthy = True
        for h in health_record:
            if not health_record[h]:
                message += "*%s is not running*\n" % h
        if healthy:
            message += "_All threads are healthy_\n"

        with db_engine.connect() as con:
            select_positions = select([positions]).order_by(desc(positions.c.timestamp))
            rs = con.execute(select_positions).fetchall()
            max_pos_timestamp = rs[0].timestamp
            max_pos_timestamp = calendar.timegm(max_pos_timestamp.utctimetuple()) * 1000

            select_fees = select([mercury_fees]).order_by(desc(mercury_fees.c.timestamp))
            rs = con.execute(select_fees).fetchall()
            max_fee_timestamp = rs[0].timestamp
            max_fee_timestamp = calendar.timegm(max_fee_timestamp.utctimetuple()) * 1000

            message += "_time is_ *%s* _UTC_\n" % (datetime.utcnow().strftime("%H:%M:%S"))

            utc_time = getUTCtime()

            try:
                select_mm_pnl = select([mm_pnl]).order_by(desc(mm_pnl.c.timestamp))
                rs = con.execute(select_mm_pnl).fetchall()
                last_mm_symbol = rs[0].symbol
                last_mm_pnl = rs[0].mm_pnl
                max_mm_timestamp = rs[0].timestamp
                max_mm_timestamp = calendar.timegm(max_mm_timestamp.utctimetuple()) * 1000
                last_mm_s = (utc_time - max_mm_timestamp) / 1000
                last_mm_m = math.floor(last_mm_s / 60.0)
                last_mm_h = math.floor(last_mm_m / 60.0)
                message += "_last mm %s %d h %d m ago\nlast pnl: %.6f_\n" % (
                    last_mm_symbol, last_mm_h, last_mm_m - (last_mm_h * 60), float(last_mm_pnl))

                select_unh_pnl = select([unhedge_pnl]).order_by(desc(unhedge_pnl.c.timestamp))
                rs = con.execute(select_unh_pnl).fetchall()
                last_unh_symbol = rs[0].symbol
                last_unhedge_pnl = rs[0].unhedge_pnl
                max_unh_timestamp = rs[0].timestamp
                max_unh_timestamp = calendar.timegm(max_unh_timestamp.utctimetuple()) * 1000
                last_unh_s = (utc_time - max_unh_timestamp) / 1000
                last_unh_m = math.floor(last_unh_s / 60.0)
                last_unh_h = math.floor(last_unh_m / 60.0)
                message += "_last unhedge %s %d h %d m ago\nlast pnl: %.6f_\n" % (
                    last_unh_symbol, last_unh_h, last_unh_m - (last_unh_h * 60), float(last_unhedge_pnl))
            except:
                pass
            pos_updated_min = (utc_time - max_pos_timestamp) / 60000
            fee_updated_min = (utc_time - max_fee_timestamp) / 60000
            message += "_position updated %d m ago_\n" % pos_updated_min
            message += "_fees updated %d m ago_\n" % fee_updated_min
            if (fee_updated_min > 70) or (pos_updated_min > 70):
                message += "*Position and/or fees were updated too long ago*"
    except Exception as e:
        message = "Could not initiate: %s" % e
        logger.error(traceback.format_exc())

    logger.debug(message)
    query = update.callback_query
    bot.answerCallbackQuery(callback_query_id=query.id, text="~~~Health Status~~~")
    bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown',
                     reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard))


def getBotXMLRPC():
    XMLRPCServer_mercurybot = xmlrpc.client.ServerProxy('http://' + mercurybot_host + ':' + mercurybot_port)
    return XMLRPCServer_mercurybot


# TODO: check_admin_privilege
def check_admin_privilege(update):
    isadmin = False
    useraccounts = Table(useraccounts_table, metadata, autoload=True)
    stm = select([useraccounts]).where(useraccounts.c.telegram_ID == update.effective_user.id)
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
                             text="%s restart" % emoji.emojize(":arrows_counterclockwise:", use_aliases=True),
                             callback_data="/restart")],
                         [InlineKeyboardButton(
                             text="%s current pairs" % emoji.emojize(":diamonds:", use_aliases=True),
                             callback_data="/pairs")],
                         [InlineKeyboardButton(
                             text="%s hold balance" % emoji.emojize(":anchor:", use_aliases=True),
                             callback_data="/hold_balance")],
                         [InlineKeyboardButton(
                             text="%s cheapest pairs" % emoji.emojize(":top:", use_aliases=True),
                             callback_data="/cheapest")],
                         [InlineKeyboardButton(
                             text="%s wallet balance" % emoji.emojize(":credit_card:", use_aliases=True),
                             callback_data="/walletbalance")],
                         [InlineKeyboardButton(
                             text="%s check bot health" % emoji.emojize(":battery:", use_aliases=True),
                             callback_data="/health")]] + back_button

    # TODO: handlers
    handlers = []
    handlers.append(CommandHandler('start', start))
    handlers.append(RegexHandler(pattern='^\d{6}$', callback=OTP_command))
    handlers.append(RegexHandler(pattern='^0$', callback=CancelOTP))
    handlers.append(CallbackQueryHandler(pattern='^/statistics', callback=stats))
    handlers.append(CallbackQueryHandler(pattern='^/users', callback=show_users))
    handlers.append(CallbackQueryHandler(pattern='^/start', callback=start))
    handlers.append(CallbackQueryHandler(pattern='^/health', callback=health_check))
    handlers.append(CallbackQueryHandler(pattern='^/restart', callback=restart))
    handlers.append(CallbackQueryHandler(pattern='^/pairs', callback=pairs))
    handlers.append(CallbackQueryHandler(pattern='^/cheapest', callback=cheapest))
    handlers.append(CallbackQueryHandler(pattern='^/hold_balance', callback=show_hold_balance))
    handlers.append(CallbackQueryHandler(pattern='^/actions', callback=unapproved_actions))
    handlers.append(CallbackQueryHandler(pattern='^/transfers', callback=transfers_show))
    handlers.append(CallbackQueryHandler(pattern='^/admin', callback=admin_functions))
    handlers.append(CallbackQueryHandler(pattern='^/contact', callback=contact))
    handlers.append(CallbackQueryHandler(pattern='^/invest', callback=invest))
    handlers.append(CallbackQueryHandler(pattern='^/walletbalance', callback=wallet_balance))
    handlers.append(CallbackQueryHandler(pattern='^/close_position', callback=close_position))
    handlers.append(CallbackQueryHandler(pattern='^a\d{1,3}$', callback=action_approve))
    handlers.append(CallbackQueryHandler(pattern='^ch\d{1,99}$', callback=user_stats))
    handlers.append(CallbackQueryHandler(pattern='^d\d{1,3}$', callback=action_disapprove))
    handlers.append(RegexHandler(pattern='^h\d{1,3}.\d{1,8}$', callback=hold_balance_update))
    handlers.append(RegexHandler(pattern='^l\d{1,3}.\d{1,8}$', callback=hold_loan_balance_update))
    handlers.append(RegexHandler(pattern='^u\d{1,3}.\d{1,8}$', callback=request_unhedge))
    handlers.append(RegexHandler(pattern='^t_(b|p)_([A-Z]{3,4})_(sell|buy)_(\d{1,9})(_*m*)$', callback=request_trade))
    handlers.append(CallbackQueryHandler(pattern='^/readtc\d', callback=readtc))

    for h in handlers:
        dispatcher.add_handler(h)

    dispatcher.add_error_handler(error_callback)

    updater.start_polling(clean=True, timeout=30, poll_interval=10, read_latency=5, bootstrap_retries=0)
