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
                        String, Boolean, MetaData)
from sqlalchemy.sql import select
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler, RegexHandler
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

useraccounts_table = 'telegram_useraccounts'
positions_table = 'mercury_positions'
balance_table = 'mercury_balance'
balance_diff_table = 'avg_balance_difference'
pic_folder = './pictures'
pic_1_filename = 'balance.png'
pic_2_filename = 'cumulative.png'

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
    logger.debug("user accounts table does not exist")
    # Create a table with the appropriate Columns
    Table(useraccounts_table, metadata,
          Column('ID', Integer, primary_key=True, nullable=False),
          Column('firstname', String(255)), Column('lastname', String(255)),
          Column('username', String(255)), Column('isadmin', Boolean(), default=False), Column('address', String(40)),
          Column('withdrawn', BigInteger(), default=0))
    # Implement the creation
    metadata.create_all()

if not db_engine.dialect.has_table(db_engine, positions_table):
    logger.debug("positions table does not exist")
    # Create a table with the appropriate Columns
    Table(positions_table, metadata,
          Column('userID', Integer, ForeignKey("useraccounts_table.ID")),
          Column('position', BigInteger(), default=0)), Column('timestamp', DateTime, default=datetime.utcnow)
    # Implement the creation
    metadata.create_all()

updater = Updater(token=TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher


#
# Helpers
#

def getUTCtime():
    d = datetime.utcnow()
    unixtime = calendar.timegm(d.utctimetuple())
    return unixtime * 1000

def start(bot, update):
    with db_engine.connect() as con:
        userfrom = update.effective_user
        logger.debug("userfrom : %s" % userfrom)
        userID = userfrom.id
        firstname = userfrom.first_name
        lastname = userfrom.last_name
        username = userfrom.username

        useraccounts = Table(useraccounts_table, metadata, autoload=True)
        stm = select([useraccounts]).where(useraccounts.c.ID == userID)
        rs = con.execute(stm)
        response = rs.fetchall()
        isadmin = False
        freshuser = False
        message = None
        keyboard = None

        if len(response) == 0:
            logger.debug("user not found in db, creating new user %s" % userfrom)
            try:
                address = XMLRPCServer.getNewAddress()
                ins = useraccounts.insert().values(ID=userID, firstname=firstname, lastname=lastname, username=username,
                                                   isadmin=False, address=address)
                con.execute(ins)
                message = "Hello, %s!\nYour new account has just created\nYour address is\n%s\n" % (username, address)

                keyboard = user_keyboard
                freshuser = True
            except:
                message = "Failed to create new user, please contact admin"
                keyboard = user_keyboard
        else:
            for u in response:
                isadmin = u.isadmin == 1
                logger.debug("user found in db, admin: %s" % isadmin)

            if isadmin:
                message = "Hello, admin %s!\nWelcome back to use the bot" % (username)
                keyboard = admin_keyboard
            elif not freshuser:
                message = "Hello, %s!\nWelcome back to use the bot\n" % (username)
                address = response[0].address
                position = response[0].position
                withdrawn = response[0].withdrawn

                try:
                    balance = XMLRPCServer.getInputValue(address) - withdrawn
                    message += "Your balance is %.8f\n" % (int(balance) / 1e8)
                    message += "Your position is %.8f\n" % (int(position) / 1e8)
                    message += "Your address is\n%s\n" % address
                except:
                    message += "Balance is unavailable, please contact admin"
                keyboard = user_keyboard

        if message and keyboard:
            bot.send_message(chat_id=update.message.chat_id, text=message,
                             reply_markup=ReplyKeyboardMarkup(keyboard=keyboard))

def stats(bot, update):
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    df = pd.read_sql_query(sql='SELECT * FROM ' + balance_table, con=db_engine, index_col='index')
    df_groupped = df.groupby(df.timestamp.dt.date)['totalbalance'].mean()
    daily_pc = df_groupped.pct_change().dropna() * 365 * 100
    cumulative_pc = ((df_groupped - df_groupped.ix[0]) / df_groupped.ix[0]) * 100

    plot_graph(daily_pc, pic_1_filename, 'Yearly %')
    plot_graph(cumulative_pc, pic_2_filename, 'Cumulative growth %')

    picture_1 = open(pic_folder + '/' + pic_1_filename, 'rb')
    bot.send_photo(chat_id=update.message.chat_id, photo=picture_1)
    picture_2 = open(pic_folder + '/' + pic_2_filename, 'rb')
    bot.send_photo(chat_id=update.message.chat_id, photo=picture_2)


def OTP_command(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return
    OTP = update.message.text
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
            message = 'BitMEX -> Polo transfer created, ID: %s' % result['transactID']

        if message:
            bot.send_message(chat_id=update.message.chat_id, text=message, reply_markup=ReplyKeyboardMarkup(
            keyboard=admin_keyboard))

    last_command = None
    last_args = None

def CancelOTP(bot, update):
    global last_command
    global last_args
    isadmin = check_admin_privilege(update)
    if not isadmin:
        return

    last_command = None
    last_args = None
    message = "Command cancelled"
    bot.send_message(chat_id=update.message.chat_id, text=message, reply_markup=ReplyKeyboardMarkup(
        keyboard=admin_keyboard))

def transfers_show(bot, update):
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

    message = "BitMEX %s Poloniex %.6f\n" % (direction, abs(transfer_diff))
    result = bitmex.min_withdrawal_fee()
    logger.debug(result)
    message += "Min fee is: %s\n" % (result['fee'] / XBt_TO_XBT)

    message += "Current UTC now is %s\n" % (datetime.utcnow().strftime("%H:%M:%S"))
    message += "send OTP to confirm or 0 to cancel"
    bot.send_message(chat_id=update.message.chat_id, text=message, reply_markup=ReplyKeyboardRemove())
    last_command = 'BW'
    last_args = transfer_diff

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
        message += "bot pid: %s\n" % pid
    else:
        message += "bot is not running!\n"
    message += "virtual memory used %d%%\n" % psutil.virtual_memory().percent
    message += "swap memory used %d%%\n" % psutil.swap_memory().percent

    freeG = shutil.disk_usage('/').free / 1e9
    message += "free disk space: %.2f Gb\n" % freeG
    health_df = pd.read_sql_table('mercury_health', con=db_engine)
    health_record = health_df.to_dict(orient='records')
    for r in health_record[0]:
        if r not in ['index', 'timestamp']:
            message += "%s is alive: %s\n" % (r, health_record[0][r] == 1)
    message += "updated %d s ago\n" % ((getUTCtime() - health_record[0]['index']) / 1000)

    logger.debug(message)
    bot.send_message(chat_id=update.message.chat_id, text=message)

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


admin_keyboard = [[KeyboardButton(text="/statistics"), KeyboardButton(text="/transfers"),
                   KeyboardButton(text="/health")]]
user_keyboard = [[KeyboardButton(text="/statistics")]]

start_handler = CommandHandler('start', start)
stats_handler = CommandHandler('statistics', stats)
health_handler = CommandHandler('health', health_check)
transfers_show_handler = CommandHandler('transfers', transfers_show)
OTP_handler = RegexHandler(pattern='^\d{6}$', callback=OTP_command)
OTP_cancel_handler = RegexHandler(pattern='^0$', callback=CancelOTP)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(stats_handler)
dispatcher.add_handler(health_handler)
dispatcher.add_handler(transfers_show_handler)
dispatcher.add_handler(OTP_handler)
dispatcher.add_handler(OTP_cancel_handler)

dispatcher.add_error_handler(error_callback)
updater.start_polling()