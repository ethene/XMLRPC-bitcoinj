#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-
import logging
import traceback
import xmlrpc.client

import coloredlogs
from sqlalchemy import (create_engine, Table, Column, Integer,
                        String, MetaData)
from sqlalchemy.sql import select
from telegram import ReplyKeyboardMarkup, KeyboardButton
from telegram.error import (TelegramError)
from telegram.ext import CommandHandler
from telegram.ext import Updater


def error_callback(bot, update, error):
    try:
        raise error
    except TelegramError as e:
        logger.error(e)
        logger.error(traceback.format_exc())


XMLRPCServer = xmlrpc.client.ServerProxy('http://localhost:8000')

import sys

sys.path.insert(0, '../BitMEX-trader/db/')
from settings import MYSQL_CONNECTION, TELEGRAM_BOT_TOKEN

# MYSQL_CONNECTION = 'mysql+mysqlconnector://mercurybot:123QWEasdzxc@localhost:3306/mercury_db'
level = logging.DEBUG
# TELEGRAM_BOT_TOKEN = '410462581:AAGhrsRrw2pn0-nrr2HVUVjNoFzxamQsLZc'

formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger('admin-telegram-bot')
logger.setLevel(level)

coloredlogs.install(level=level)

db_engine = create_engine(MYSQL_CONNECTION, echo=False)

useraccounts_table = 'useraccounts'
admin_table = 'adminusers'
metadata = MetaData(db_engine)

if not db_engine.dialect.has_table(db_engine, admin_table):
    logger.debug("admin accounts table does not exist")
    # Create a table with the appropriate Columns
    Table(admin_table, metadata,
          Column('ID', Integer, primary_key=True, nullable=False),
          Column('firstname', String(255)), Column('lastname', String(255)),
          Column('username', String(255)))
    # Implement the creation
    metadata.create_all()

updater = Updater(token=TELEGRAM_BOT_TOKEN)
dispatcher = updater.dispatcher


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


def start(bot, update):
    with db_engine.connect() as con:
        adminaccounts = Table(admin_table, metadata, autoload=True)
        stm = select([adminaccounts])
        rs = con.execute(stm)
        response = rs.fetchall()
        userfrom = update.effective_user
        logger.debug("userfrom : %s" % userfrom)
        userID = userfrom.id
        firstname = userfrom.first_name
        lastname = userfrom.last_name
        username = userfrom.username
        if len(response) == 0:
            logger.debug("admins not found in db, creating new admin %s" % userfrom)
            ins = adminaccounts.insert().values(ID=userID, firstname=firstname, lastname=lastname, username=username)
            con.execute(ins)
            return

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
                             reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/userlist")]]))


start_handler = CommandHandler('start', start)
userlist_handler = CommandHandler('userlist', userlist)
dispatcher.add_handler(start_handler)
dispatcher.add_handler(userlist_handler)

dispatcher.add_error_handler(error_callback)

updater.start_polling()
