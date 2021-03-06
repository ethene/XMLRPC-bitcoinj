#!/home/strky/jython/bin/jython
#  -*- coding: utf-8 -*-
import sys

sys.path.append("bitcoinj-core-0.14.6-bundled.jar")
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
import os

level = logging.DEBUG

script_name = 'XMLRPC-bitcoinj'
efsfolder = os.getenv('EFSFOLDER', '.')
walletFolder = efsfolder + '/wallet'
logfolder = efsfolder + '/log/'

try:
    os.stat(efsfolder)
except:
    os.mkdir(efsfolder)

try:
    os.stat(walletFolder)
except:
    os.mkdir(walletFolder)

try:
    os.stat(logfolder)
except:
    os.mkdir(logfolder)

try:
    confirmationsRequired = int(os.getenv('CONFIRMATIONS'))
except:
    confirmationsRequired = 1

try:
    satoshi_per_b = int(os.getenv('SATOSHI_PER_B'))
except:
    satoshi_per_b = 60

formatter = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(script_name)
log_handler = logging.StreamHandler()
log_handler.setFormatter(formatter)
logger.addHandler(log_handler)

log_filename = logfolder + script_name + '.log'
log_handler = SizedTimedRotatingFileHandler(log_filename, maxBytes=0, backupCount=5, when='D',
                                            interval=1)  # encoding='bz2',  # uncomment for bz2 compression)
logger.addHandler(log_handler)
logger.setLevel(level)

params = None
filePrefix = None
network = os.getenv('BITCOIN_NETWORK', 'TEST')
if network == 'TEST':
    params = org.bitcoinj.params.TestNet3Params.get()
    filePrefix = 'bitcoinj-service-testnet'
elif network == 'PROD':
    params = org.bitcoinj.params.MainNetParams.get()
    filePrefix = 'bitcoinj-service-mainnet'

logger.info("Network: %s" % network)


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


# Restrict to a particular path.
class RequestHandler(SimpleXMLRPCRequestHandler):
    rpc_paths = ('/RPC2',)


# Create server
rpc_port = int(os.getenv('BTICOINJ_RPCPORT', 8010))
server = SimpleXMLRPCServer(("0.0.0.0", rpc_port),
                            requestHandler=RequestHandler)
server.register_introspection_functions()


# Register an instance; all the methods of the instance are
# published as XML-RPC methods (in this case, just 'div').
class RPCFunctions:
    def __init__(self, kit):
        self.kit = kit

    # TODO: getNewAddress
    def getNewAddress(self):
        address = self.kit.wallet().freshReceiveAddress()
        address_string = address.toString()
        logger.debug("new address requested %s" % (address_string))
        return address_string

    # TODO: getInputValue
    def getInputValue(self, address):
        logger.debug("getting txs for %s" % (address))
        transactions = self.kit.wallet().getTransactions(True)
        invalue = 0
        for t in transactions:
            confidence = t.getConfidence()
            depth = confidence.getDepthInBlocks()
            t_outputs = t.getOutputs()
            for to in t_outputs:
                toa = to.getAddressFromP2PKHScript(params)
                if toa:
                    to_addr = toa.toString()
                    if (to_addr == address) and (depth >= confirmationsRequired):
                        value = int(to.getValue().toString())
                        invalue += value

        logger.debug("address %s input value %.8f (%.8f BTC)" % (address, invalue, invalue / 1e8))
        return invalue

    # TODO: isTXconfirmed
    def isTXconfirmed(self, tx_id):
        transactions = self.kit.wallet().getTransactions(True)
        result = False
        for t in transactions:
            if tx_id == t.getHashAsString():
                confidence = t.getConfidence()
                depth = confidence.getDepthInBlocks()
                if depth >= confirmationsRequired:
                    result = True
                    break
        return result

    # TODO: getUnconfirmedTransactions
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

    # TODO: sendCoins
    def sendCoins(self, fromAddress, toAddress, amount):
        sr_tx = 0
        sent_value = 0
        change_value = 0
        bl = self.kit.wallet().getBalance()
        # balance = bl.getValue()
        invalue = self.getInputValue(fromAddress)
        legal = invalue - amount >= 0
        logger.debug("invalue: %d, to_send: %d, legal: %s " % (invalue, amount, legal))
        if legal:
            # old send procedure
            '''
            c = org.bitcoinj.core.Coin.valueOf(amount).subtract(org.bitcoinj.core.Transaction.DEFAULT_TX_FEE)
            pg = self.kit.peerGroup()
            toAddr = org.bitcoinj.core.Address.fromBase58(params, toAddress)
            sr = self.kit.wallet().sendCoins(pg, toAddr, c)
            sr_tx = sr.tx.getHashAsString()
            sent_value = sr.tx.getValueSentFromMe(self.kit.wallet()).getValue()
            change_value = sr.tx.getValueSentToMe(self.kit.wallet()).getValue()
            '''
            # new send procedure
            # max TX size (actually about 250)
            tx_bytes = 800
            tx_deduct_fee = tx_bytes * satoshi_per_b
            default_tx_fee = org.bitcoinj.core.Coin.valueOf(tx_deduct_fee)
            logger.debug("deducted default fee: %d sat (%.8f BTC)" % (tx_deduct_fee, tx_deduct_fee / 1e8))
            c = org.bitcoinj.core.Coin.valueOf(amount).subtract(default_tx_fee)
            toAddr = org.bitcoinj.core.Address.fromBase58(params, toAddress)
            send_request = org.bitcoinj.wallet.SendRequest.to(toAddr, c)
            fee_per_kb = satoshi_per_b * 1000
            send_request.feePerKb = org.bitcoinj.core.Coin.valueOf(fee_per_kb)
            logger.debug("set fee per kb: %d sat (%.8f BTC)" % (fee_per_kb, fee_per_kb / 1e8))
            sr = self.kit.wallet().sendCoins(pg, send_request)
            sr_tx = sr.tx.getHashAsString()
            sent_value = sr.tx.getValueSentFromMe(self.kit.wallet()).getValue()
            change_value = sr.tx.getValueSentToMe(self.kit.wallet()).getValue()
        return {'TX': sr_tx, 'value': sent_value - change_value}

    # TODO: sendCoinsAnyway
    def sendCoinsAnyway(self, toAddress, amount):
        sr_tx = 0
        sent_value = 0
        change_value = 0
        bl = self.kit.wallet().getBalance()
        # balance = bl.getValue()

        # old send procedure
        '''
        c = org.bitcoinj.core.Coin.valueOf(amount).subtract(org.bitcoinj.core.Transaction.DEFAULT_TX_FEE)
        pg = self.kit.peerGroup()
        toAddr = org.bitcoinj.core.Address.fromBase58(params, toAddress)
        sr = self.kit.wallet().sendCoins(pg, toAddr, c)
        sr_tx = sr.tx.getHashAsString()
        sent_value = sr.tx.getValueSentFromMe(self.kit.wallet()).getValue()
        change_value = sr.tx.getValueSentToMe(self.kit.wallet()).getValue()
        '''
        # new send procedure
        # max TX size (actually about 250)
        tx_bytes = 500
        tx_deduct_fee = tx_bytes * satoshi_per_b
        default_tx_fee = org.bitcoinj.core.Coin.valueOf(tx_deduct_fee)
        logger.debug("deducted default fee: %d sat (%.8f BTC)" % (tx_deduct_fee, tx_deduct_fee / 1e8))
        c = org.bitcoinj.core.Coin.valueOf(amount).subtract(default_tx_fee)
        toAddr = org.bitcoinj.core.Address.fromBase58(params, toAddress)
        send_request = org.bitcoinj.wallet.SendRequest.to(toAddr, c)
        fee_per_kb = satoshi_per_b * 1000
        send_request.feePerKb = org.bitcoinj.core.Coin.valueOf(fee_per_kb)
        logger.debug("set fee per kb: %d sat (%.8f BTC)" % (fee_per_kb, fee_per_kb / 1e8))
        sr = self.kit.wallet().sendCoins(pg, send_request)
        sr_tx = sr.tx.getHashAsString()
        sent_value = sr.tx.getValueSentFromMe(self.kit.wallet()).getValue()
        change_value = sr.tx.getValueSentToMe(self.kit.wallet()).getValue()
        return {'TX': sr_tx, 'value': sent_value - change_value}

    # TODO: getBalance
    def getWalletBalance(self):
        balance = self.kit.wallet().getBalance().getValue()
        return balance


class SenderListener(AbstractWalletEventListener):
    def __init__(self, pg):
        super(SenderListener, self).__init__()
        self.peerGroup = pg

    @loud_exceptions
    def onCoinsReceived(self, w, tx, pb, nb):
        v = tx.getValueSentToMe(w)
        logger.debug("tx received %s" % (tx))
        for to in tx.getOutputs():
            logger.debug(to)
            toa = to.getAddressFromP2PKHScript(params)
            if toa:
                addr = toa.toString()
                logger.debug("receiver address: %s" % addr)

        class myFutureCallback(FutureCallback):
            def __init__(self, tx):
                self.trx = tx

            @loud_exceptions
            def onSuccess(self, txn):
                valueConfirmed = v.getValue()
                logger.debug("confirmed: %s" % valueConfirmed)
                for to in self.trx.getOutputs():
                    rcv_address = to.getAddressFromP2PKHScript(params)
                    if rcv_address:
                        logger.debug("confirmed receiver address: %s" % rcv_address.toString())

        Futures.addCallback(tx.getConfidence().getDepthFuture(confirmationsRequired), myFutureCallback(tx))


# TODO: main loop
if __name__ == "__main__":
    if not params:
        logger.error("no network params defined per NETWORK env")
        sys.exit()
    f = File(walletFolder)
    kit = WalletAppKit(params, f, filePrefix)
    kit.setAutoSave(True)
    logger.info("initializing...")
    kit.startAsync()
    kit.awaitRunning()
    pg = kit.peerGroup()
    wallet = kit.wallet()

    balance = wallet.getBalance().getValue()
    logger.debug("balance: %.8f XBT" % (float(balance) / 1e8))
    sl = SenderListener(pg)

    transactions = kit.wallet().getTransactions(True)
    addr_balance = {}
    invalue = 0
    for t in transactions:
        confidence = t.getConfidence()
        depth = confidence.getDepthInBlocks()
        t_outputs = t.getOutputs()
        # check unspent txs:
        if depth < confirmationsRequired:
            logger.debug("unspent: %s" % t.getHashAsString())

        for to in t_outputs:
            toa = to.getAddressFromP2PKHScript(params)
            to_address = None
            if toa:
                to_address = toa.toString()
            value = int(to.getValue().toString())
            if to_address and (to_address in addr_balance):
                addr_balance[to_address] += value
            elif to_address:
                addr_balance[to_address] = value

    for a in addr_balance:
        logger.debug("addr: %s value %s" % (a, addr_balance[a]))

    wallet.addEventListener(sl)
    logger.info("finished initialisation - now in main event loop")

    server.register_instance(RPCFunctions(kit))

    # Run the server's main loop
    server.serve_forever()
