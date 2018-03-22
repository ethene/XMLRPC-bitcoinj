#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

# TODO: imports
import sys
sys.path.insert(0, '../BitMEX-trader/db/')
import gettext
import logging
import xmlrpc.client
import os

import coloredlogs
import emoji
import telebot
# from settings import MYSQL_CONNECTION, TELEGRAM_BOT_TOKEN
from sqlalchemy import (create_engine, Table, MetaData)
from sqlalchemy.sql import select
from time import sleep
from utils.dotdict import dotdict

# from telegram import InlineKeyboardButton, \
#    InlineKeyboardMarkup

from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler

en = gettext.translation('mercury-telegram', localedir='locale', languages=['en'])
en.install()

level = logging.DEBUG
script_name = 'tx-confirmation-checker'

bitcoinj_host = os.getenv('BITCOINJ_HOST', 'localhost')
bitcoinj_port = os.getenv('BTICOINJ_RPCPORT', '8010')

mysql_host = os.getenv('MYSQL_HOST', 'localhost')
mysql_port = os.getenv('MYSQL_PORT', '3306')
mysql_user = os.getenv('MYSQL_USER', 'user')
mysql_pass = os.getenv('MYSQL_PASS', 'pass')
mysql_db = os.getenv('MYSQL_DB', 'cryptomarkets')

efsfolder = os.getenv('EFSFOLDER', '.')
logfolder = efsfolder + '/log/'

try:
    os.stat(efsfolder)
except:
    os.mkdir(efsfolder)

try:
    os.stat(logfolder)
except:
    os.mkdir(logfolder)

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

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', level=level)
logger = logging.getLogger(script_name)
log_filename = logfolder + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
coloredlogs.install(level=level)

XBt_TO_XBT = 100000000
transactions_table = 'bitcoinj_transactions'
useraccounts_table = 'telegram_useraccounts'
bitcoinj_transactions = Table(transactions_table, metadata, autoload=True)
useraccounts = Table(useraccounts_table, metadata, autoload=True)

btn = telebot.types.InlineKeyboardButton(text="%s" % emoji.emojize(":arrow_up_small: go home", use_aliases=True),
                                         callback_data="/start")

XMLRPCServer = xmlrpc.client.ServerProxy('http://' + bitcoinj_host + ':' + bitcoinj_port)

CYCLE_WAIT = 60

if __name__ == "__main__":
    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
    while (True):
        with db_engine.connect() as con:
            j = bitcoinj_transactions.join(useraccounts)
            q = select([bitcoinj_transactions, useraccounts]).where(
                bitcoinj_transactions.c.confirmed == False).select_from(
                j)
            txs = con.execute(q).fetchall()
            for t in txs:
                user_id = t.userID
                tx_id = t.TXID
                value = t.value
                confirmed = XMLRPCServer.isTXconfirmed(tx_id)
                logger.debug("tx id: %s, user_id: %s, confirmed: %s" % (tx_id, user_id, confirmed))
                if confirmed:
                    upd = bitcoinj_transactions.update().values(confirmed=True).where(
                        bitcoinj_transactions.c.TXID == tx_id)
                    con.execute(upd)
                    keyboard = telebot.types.InlineKeyboardMarkup()
                    keyboard.add(btn)
                    bot.send_message(chat_id=user_id,
                                     text="Transaction for\n*%.8f* _BTC_\nis now confirmed\n" % (value / XBt_TO_XBT),
                                     parse_mode='Markdown',
                                     reply_markup=keyboard)
        logger.debug("Sleeping for %s s" % CYCLE_WAIT)
        sleep(CYCLE_WAIT)
