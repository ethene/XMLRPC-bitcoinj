"""Poloniex API Connector."""
from __future__ import absolute_import

from threading import Lock
from time import sleep

import poloniex

class synchronized(object):
    """ Class enapsulating a lock and a function
    allowing it to be used as a synchronizing
    decorator making the wrapped function
    thread-safe """

    def __init__(self, *args):
        self.lock = Lock()

    def __call__(self, f):
        def lockedfunc(*args, **kwargs):
            try:
                self.lock.acquire()
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    raise e
            finally:
                self.lock.release()

        return lockedfunc


def retry(exceptions=None, tries=None):
    if exceptions:
        exceptions = tuple(exceptions)

    def wrapper(fun):
        def retry_calls(*args, **kwargs):
            if tries:
                for _ in range(tries):
                    try:
                        return fun(*args, **kwargs)
                    except exceptions:
                        sleep(10)
                        pass
                    except:
                        sleep(10)
                        pass
            else:
                while True:
                    try:
                        return fun(*args, **kwargs)
                    except exceptions:
                        sleep(10)
                        pass
                    except:
                        sleep(10)
                        pass

        return retry_calls

    return wrapper


# https://www.bitmex.com/api/explorer/
class Poloniex(object):
    """Poloniex API Connector."""

    def __init__(self, apiKey=None, apiSecret=None):
        """Init connector."""

        self.apiKey = apiKey
        self.apiSecret = apiSecret

        myCoach = poloniex.Coach(callLimit=1)
        self.polo = poloniex.Poloniex(coach=myCoach, key=self.apiKey, secret=self.apiSecret, timeout=180)

    #
    # Public methods
    #

    def getBTCPrice(self):
        return self.polo.returnOrderBook(symbol='USDT_BTC', depth=5)['bid'][0]

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def orderbook(self, symbol, depth=100):
        """Get an instrument's details."""
        orderbook = self.polo.returnOrderBook(symbol, depth=depth)
        return orderbook

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def funds(self, account='margin', currency='BTC'):
        """Get your current balance."""
        balance = self.polo.returnAvailableAccountBalances()
        if account in balance:
            if currency in balance[account]:
                return float(balance[account][currency])
            else:
                return 0.0
        else:
            return 0.0

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def getMarginPosition(self):
        return self.polo.getMarginPosition()

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def getBalances(self, account='exchange'):
        """Get your current balance."""
        balances = self.polo.returnAvailableAccountBalances()
        self.logger.debug("balances: %s" % balances)
        if account in balances:
            self.balances = balances[account]
        sleep(1)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def position(self, symbol):
        """Get your open position."""
        position = self.polo.getMarginPosition()
        if symbol in position:
            return float(position[symbol]['amount'])
        else:
            return 0.0

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def returnLoanOrders(self, symbol='BTC'):
        """Get a list of loan orders."""
        loan_orders = self.polo.returnLoanOrders(symbol)
        return loan_orders

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def returnActiveLoans(self):
        """Get your active loans."""
        activeLoans = self.polo.returnActiveLoans()
        return activeLoans

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def createLoanOffer(self, symbol='BTC', amount=0, lendingRate=0, duration=2):
        """Create new loan offer."""
        self.polo.createLoanOffer(currency=symbol, amount=amount, lendingRate=lendingRate, autoRenew=0,
                                  duration=duration)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def cancelLoanOffer(self, id):
        """Cancel loan offer."""
        self.polo.cancelLoanOffer(orderNumber=id)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def returnOpenLoanOffers(self):
        """Get your open loan offers."""
        loanOffers = self.polo.returnOpenLoanOffers()
        return loanOffers

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def Buy(self, quantity, price, symbol):
        self.logger.debug("buy %s %s %s" % (symbol, price, quantity))
        """Place a buy order.
        Returns:
        {"orderNumber":31226040,"resultingTrades":[{"amount":"338.8732","date":"2014-10-18 23:03:21","rate":"0.00000173","total":"0.00058625","tradeID":"16164","type":"buy"}]}
        """
        result = self.polo.buy(currencyPair=symbol, rate=price, amount=quantity, orderType='fillOrKill')
        return result

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def Sell(self, quantity, price, symbol):
        self.logger.debug("sell %s %s %s" % (symbol, price, quantity))
        """Place a buy order.
        Returns:
        {"orderNumber":31226040,"resultingTrades":[{"amount":"338.8732","date":"2014-10-18 23:03:21","rate":"0.00000173","total":"0.00058625","tradeID":"16164","type":"buy"}]}
        """
        result = self.polo.sell(currencyPair=symbol, rate=price, amount=quantity, orderType='fillOrKill')
        return result

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def marginBuy(self, quantity, price, symbol, lendingRate=0.02):
        self.logger.debug("margin buy %s %s %s %s" % (symbol, price, quantity, lendingRate))
        """Place a buy order.

        Returns order object. ID: orderID
        """
        return self.polo.marginBuy(currencyPair=symbol, rate=price, amount=quantity, lendingRate=lendingRate)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def marginSell(self, quantity, price, symbol, lendingRate=0.02):
        self.logger.debug("margin sell %s %s %s %s" % (symbol, price, quantity, lendingRate))
        """Place a buy order.

        Returns order object. ID: orderID
        """
        result = self.polo.marginSell(currencyPair=symbol, rate=price, amount=quantity, lendingRate=lendingRate)
        return result

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def closeMarginPosition(self, symbol):
        """Closing Margin position"""

        return self.polo.closeMarginPosition(symbol)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def getFeeInfo(self):
        """Returns fee info

        """
        return self.polo.returnFeeInfo()

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def cancel(self, orderID):
        """Cancel an existing order."""
        return self.polo.cancelOrder(orderID)

    @synchronized()
    @retry([poloniex.PoloniexError], 10)
    def transfer(self, amount, fromAccount='exchange', toAccount='margin', currency='BTC'):
        """transfer funds between accounts."""
        self.logger.debug("transfer %s  %s -> %s  %s" % (currency, fromAccount, toAccount, amount))
        result = self.polo.transferBalance(currency=currency, fromAccount=fromAccount, toAccount=toAccount,
                                           amount=amount)
        self.logger.debug("result: %s" % result)
        return result
