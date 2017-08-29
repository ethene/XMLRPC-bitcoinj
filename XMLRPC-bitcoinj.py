#!/home/strky/jython/bin/jython
# -*- coding: utf-8 -*-
import sys

sys.path.append("bitcoinj-core-0.14.4-bundled.jar")
sys.path.append("slf4j-log4j12-1.7.25.jar")
sys.path.append("log4j-1.2.17.jar")

from org.apache.log4j import *

PropertyConfigurator.configure(sys.path[0] + "/log4j.properties")

from org.bitcoinj.core import *
from java.io import File

import org.bitcoinj.params.MainNetParams
from org.bitcoinj.kits import WalletAppKit
from org.bitcoinj.wallet.listeners import AbstractWalletEventListener

from com.google.common.util.concurrent import FutureCallback
from com.google.common.util.concurrent import Futures

from SimpleXMLRPCServer import SimpleXMLRPCServer
from SimpleXMLRPCServer import SimpleXMLRPCRequestHandler

from SizedTimedRotatingFileHandler import SizedTimedRotatingFileHandler

import logging
import traceback

level = logging.DEBUG

script_name = 'XMLRPC-bitcoinj'
walletFolder = '.'
confirmationsRequired = 1

params = org.bitcoinj.params.TestNet3Params.get()
filePrefix = 'bitcoinj-service-testnet'

formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(script_name)
log_handler = logging.StreamHandler()
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)

log_filename = './log/' + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
logger.setLevel(level)


def loud_exceptions(*args):
    def _trace(func):
        def wrapper(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.error("** python exception %s " % e)
                logger.error(traceback.format_exc())
                raise
            except java.lang.Exception as e:
                logger.error("** java exception %s " % e)
                logger.error(traceback.format_exc())
                raise

        return wrapper

    if len(args) == 1 and callable(args[0]):
        return _trace(args[0])
    else:
        return _trace


# 0 for instant send, 1 for a more realistic example
# if the wallet has no btc in it, then set to 1.
# if it has a confirmed balance in it, then you can set it to 0.
confirm_wait = 1


# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)


# Create server
server = SimpleXMLRPCServer(("localhost", 8000),
                            requestHandler=RequestHandler)
server.register_introspection_functions()


# Register an instance; all the methods of the instance are
# published as XML-RPC methods (in this case, just 'div').
class RPCFunctions:
    def __init__(self, kit):
        self.kit = kit

    def getNewAddress(self):
        address = self.kit.wallet().freshReceiveAddress()
        address_string = address.toString()
        logger.debug("new address requested %s" % (address_string))
        return address_string

    def getInputValue(self, address):
        transactions = self.kit.wallet().getTransactions(True)
        invalue = 0
        for t in transactions:
            confidence = t.getConfidence()
            depth = confidence.getDepthInBlocks()
            t_outputs = t.getOutputs()
            for to in t_outputs:
                to_addr = to.getAddressFromP2PKHScript(params).toString()
                if (to_addr == address) and (depth > confirm_wait):
                    value = int(to.getValue().toString())
                    invalue += value

        logger.debug("address %s input value %.8f" % (address, invalue))
        return invalue

    def getUnconfirmedTransactions(self, address):
        txs = []
        transactions = self.kit.wallet().getTransactions(True)
        for t in transactions:
            confidence = t.getConfidence()
            depth = confidence.getDepthInBlocks()
            t_outputs = t.getOutputs()
            for to in t_outputs:
                to_addr = to.getAddressFromP2PKHScript(params).toString()
                if to_addr == address:
                    tx_id = t.getHashAsString()
                    value = int(to.getValue().toString())
                    logger.debug("tx: %s depth: %s" % (tx_id, depth))
                    if depth < confirmationsRequired:
                        txs.append({'ID': tx_id, 'value': value})
        return txs

    def sendCoins(self, fromAddress, toAddress, amount):
        sr = None
        bl = self.kit.wallet().getBalance()
        balance = bl.getValue()
        invalue = self.getInputValue(fromAddress)
        legal = invalue - amount > org.bitcoinj.core.Transaction.REFERENCE_DEFAULT_MIN_TX_FEE.getValue()
        logger.debug("invalue: %d, to_send: %d, legal: %s " % (invalue, amount, legal))
        if legal:
            c = org.bitcoinj.core.Coin.valueOf(amount)
            logger.debug(c)
        pg = self.kit.peerGroup()
        # sr = self.kit.wallet().sendCoins(pg, address, Coin(amount).subtract())
        return sr

    '''
    def getLatestTransactions(self):
        try:
            addresses = wallet.getIssuedReceiveAddresses()
            addresses_s = []
            address_value = {}
            for a in addresses:
                address_s = a.toString()
                addresses_s.append(address_s)
                #logger.debug("address used: %s" % address_s)
            transactions = wallet.getTransactions(True)
            for t in transactions:
                confidence = t.getConfidence()
                depth = confidence.getDepthInBlocks()
                t_outputs = t.getOutputs()
                for to in t_outputs:
                    to_addr = to.getAddressFromP2PKHScript(params).toString()
                    # logger.debug("tx addr: %s" % to_addr)
                    if (to_addr in addresses_s) and (depth > confirm_wait):
                        value = int(to.getValue().toString()) / 1e8
                        #logger.debug("address %s add_value %s depth %s" % (to_addr, value, depth))
                        address_value[to_addr] = value if to_addr not in address_value.keys() else address_value[
                                                                                                       to_addr] + value
            for a in address_value:
                logger.debug("addr: %s val %.8f" % (a, address_value[a]))
                with self.db_engine.connect() as con:
                    useraccounts = Table(useraccounts_table, self.metadata, autoload=True)
                    upd = useraccounts.update().values(invalue=address_value[a]).where(useraccounts.c.address == a)
                    con.execute(upd)
            return True
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(e)
            return False
    '''

class SenderListener(AbstractWalletEventListener):
    def __init__(self, pg):
        super(SenderListener, self).__init__()
        self.peerGroup = pg

        # self.address = address

    @loud_exceptions
    def onCoinsReceived(self, w, tx, pb, nb):
        v = tx.getValueSentToMe(w)
        logger.debug("tx received %s" % (tx))
        for to in tx.getOutputs():
            addr = to.getAddressFromP2PKHScript(params).toString()
            logger.debug("receiver address: %s" % addr)

        class myFutureCallback(FutureCallback):
            def __init__(self, tx):
                self.tx = tx

            @loud_exceptions
            def onSuccess(selfx, txn):
                valueConfirmed = v.getValue()
                logger.debug("confirmed: %s" % valueConfirmed)
                for to in tx.getOutputs():
                    addr = to.getAddressFromP2PKHScript(params).toString()
                    logger.debug("receiver address: %s" % addr)

        Futures.addCallback(tx.getConfidence().getDepthFuture(confirm_wait), myFutureCallback(tx))


f = File(walletFolder)
kit = WalletAppKit(params, f, filePrefix)
kit.setAutoSave(True)
logger.debug("initializing...")
kit.startAsync()
kit.awaitRunning()
pg = kit.peerGroup()
wallet = kit.wallet()

balance = wallet.getBalance().getValue()
logger.debug("balance: %.8f XBT" % (float(balance) / 1e8))
sl = SenderListener(pg)

transactions = kit.wallet().getTransactions(True)

'''
invalue = 0
for t in transactions:
    confidence = t.getConfidence()
    depth = confidence.getDepthInBlocks()
    t_outputs = t.getOutputs()
    for to in t_outputs:
        to_addr = to.getAddressFromP2PKHScript(params).toString()
        logger.debug("addr: %s" % to_addr)
        logger.debug("confidence: %s" % depth)

'''

wallet.addEventListener(sl)
logger.debug("finished initialisation - now in main event loop")

server.register_instance(RPCFunctions(kit))

# Run the server's main loop
server.serve_forever()
