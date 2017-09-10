#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

# TODO: imports
import sys
sys.path.insert(0, '../BitMEX-trader/db/')
import gettext
import logging
import xmlrpc.client

import coloredlogs
import emoji
import telebot
from settings import MYSQL_CONNECTION, TELEGRAM_BOT_TOKEN
from sqlalchemy import (create_engine, Table, MetaData)
from sqlalchemy.sql import select
from time import sleep

# from telegram import InlineKeyboardButton, \
#    InlineKeyboardMarkup

from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler

en = gettext.translation('mercury-telegram', localedir='locale', languages=['en'])
en.install()

level = logging.DEBUG
script_name = 'tx-confirmation-checker'

db_engine = create_engine(MYSQL_CONNECTION, echo=False)
metadata = MetaData(db_engine)

XMLRPCServer = xmlrpc.client.ServerProxy('http://localhost:8000')

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(module)s - %(message)s', level=level)
logger = logging.getLogger(script_name)
log_filename = './log/' + script_name + '.log'
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

XMLRPCServer = xmlrpc.client.ServerProxy('http://localhost:8000')

CYCLE_WAIT = 60

if __name__ == "__main__":
    bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
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
