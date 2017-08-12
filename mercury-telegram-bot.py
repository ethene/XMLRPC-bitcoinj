#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-
import logging
import traceback
import xmlrpc.client

import coloredlogs
import matplotlib as mpl
import pandas as pd
from sqlalchemy import (create_engine, Table, Column, Integer,
                        String, Boolean, MetaData)
from sqlalchemy.sql import select
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler
from telegram.ext import Updater

mpl.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys

sys.path.insert(0, '../BitMEX-trader/db/')
from settings import MYSQL_CONNECTION, TELEGRAM_BOT_TOKEN
from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler


def error_callback(bot, update, error):
    try:
        raise error
    except TelegramError as e:
        logger.error(e)
        logger.error(traceback.format_exc())


XMLRPCServer = xmlrpc.client.ServerProxy('http://localhost:8000')

useraccounts_table = 'telegram_useraccounts'
balance_table = 'mercury_balance'
balance_diff_table = 'avg_balance_difference'
pic_folder = './pictures'
pic_1_filename = 'balance.png'
pic_2_filename = 'cumulative.png'

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

if not db_engine.dialect.has_table(db_engine, useraccounts_table):
    logger.debug("user accounts table does not exist")
    # Create a table with the appropriate Columns
    Table(useraccounts_table, metadata,
          Column('ID', Integer, primary_key=True, nullable=False),
          Column('firstname', String(255)), Column('lastname', String(255)),
          Column('username', String(255)), Column('isadmin', Boolean(), default=False), Column('address', String(40)))
    # Implement the creation
    metadata.create_all()

updater = Updater(token=TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher

'''
def userlist(bot, update):
    userfrom = update.effective_user
    username = userfrom.username
    userID = userfrom.id
    with db_engine.connect() as con:
        adminaccounts = Table(admin_table, metadata, autoload=True)
        stm = select([adminaccounts]).where(adminaccounts.c.ID == userID)
        rs = con.execute(stm)
        response = rs.fetchall()
        if len(response) == 0:
            bot.send_message(chat_id=update.message.chat_id,
                             text="Sorry, %s!\nYou have no authorisation to use this bot" % (username))
            return
        useraccounts = Table(useraccounts_table, metadata, autoload=True)
        stm = select([useraccounts])
        rs = con.execute(stm)
        response = rs.fetchall()
        message = ""
        for u in response:
            if u.address:
                invalue = XMLRPCServer.getInputValue(u.address)
                upd = useraccounts.update().values(invalue=invalue).where(useraccounts.c.ID == userID)
                con.execute(upd)
            message += "%s %s %s %s %.8f %.8f\n" % (
                u.username, u.firstname, u.lastname, u.address, u.invalue or 0, u.outvalue or 0)
        if len(response) > 0:
            bot.send_message(chat_id=update.message.chat_id,
                             text="User / InValue / OutValue\n" + message)

'''

def start(bot, update):
    with db_engine.connect() as con:
        useraccounts = Table(useraccounts_table, metadata, autoload=True)
        stm = select([useraccounts])
        rs = con.execute(stm)
        response = rs.fetchall()
        userfrom = update.effective_user
        logger.debug("userfrom : %s" % userfrom)
        userID = userfrom.id
        firstname = userfrom.first_name
        lastname = userfrom.last_name
        username = userfrom.username
        if len(response) == 0:
            logger.debug("user not found in db, creating new admin %s" % userfrom)
            ins = useraccounts.insert().values(ID=userID, firstname=firstname, lastname=lastname, username=username,
                                               isadmin=False)
            con.execute(ins)
            bot.send_message(chat_id=update.message.chat_id,
                             text="Hello, %s!\nYour new account has just created" % (username))
            return

        '''
        stm = select([adminaccounts]).where(adminaccounts.c.ID == userID)
        rs = con.execute(stm)
        response = rs.fetchall()
        if len(response) == 0:
            bot.send_message(chat_id=update.message.chat_id,
                             text="Sorry, %s!\nYou have no authorisation to use this bot" % (username))
            return
        else:
            bot.send_message(chat_id=update.message.chat_id,
                             text="Hello, %s!\nWelcome back to use the bot" % (username),
                             reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/statistics")]]))

        '''


def stats(bot, update):
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


start_handler = CommandHandler('start', start)
# stats_handler = CommandHandler('statistics', stats)
# userlist_handler = CommandHandler('userlist', userlist)
# dispatcher.add_handler(userlist_handler)
dispatcher.add_handler(start_handler)
#dispatcher.add_handler(stats_handler)

dispatcher.add_error_handler(error_callback)
updater.start_polling()
