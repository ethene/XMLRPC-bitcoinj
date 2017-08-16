import calendar
import json
from datetime import datetime
from time import sleep

import requests

from auth import AccessTokenAuth, APIKeyAuthWithExpires


def getUTCtime():
    d = datetime.utcnow()
    unixtime = calendar.timegm(d.utctimetuple())
    return unixtime


#
# Authentication required methods
#

class AuthenticationError(Exception):
    pass


def authentication_required(function):
    """Annotation for methods that require auth."""

    def wrapped(self, *args, **kwargs):
        if not (self.apiKey):
            msg = "You must be authenticated to use this method"
            raise AuthenticationError(msg)
        else:
            return function(self, *args, **kwargs)

    return wrapped


class BitMEX(object):
    def __init__(self, base_url=None, apiKey=None, apiSecret=None, logger=None):
        self.logger = logger
        self.pending_requests = 0
        self.base_url = base_url
        self.apiKey = apiKey
        self.apiSecret = apiSecret
        self.token = None
        self.remaining = 300
        self.reset = getUTCtime() + self.remaining

        # Prepare HTTPS session
        self.session = requests.Session()
        # These headers are always sent
        self.session.headers.update({'user-agent': 'telebot-0.1'})
        self.session.headers.update({'content-type': 'application/json'})
        self.session.headers.update({'accept': 'application/json'})

    @authentication_required
    def withdraw(self, amount, address, otptoken, fee=None):
        api = "user/requestWithdrawal"
        postdict = {
            'amount': amount,
            'fee': fee,
            'currency': 'XBt',
            'address': address,
            'otpToken': otptoken
        }
        return self._curl_bitmex(api=api, postdict=postdict, verb="POST")

    @authentication_required
    def min_withdrawal_fee(self):
        api = "user/minWithdrawalFee"
        postdict = {}
        return self._curl_bitmex(api=api, postdict=postdict, verb="GET")

    def _curl_bitmex(self, api, query=None, postdict=None, timeout=3, verb=None, rethrow_errors=False):
        """Send a request to BitMEX Servers."""
        # Handle URL
        url = self.base_url + api

        # Default to POST if data is attached, GET otherwise
        if not verb:
            verb = 'POST' if postdict else 'GET'

        # Auth: Use Access Token by default, API Key/Secret if provided
        auth = AccessTokenAuth(self.token)
        if self.apiKey:
            auth = APIKeyAuthWithExpires(self.apiKey, self.apiSecret)

        def maybe_exit(e):
            if rethrow_errors:
                raise e
            else:
                exit(1)

        # Make the request

        try:
            self.pending_requests += 1
            now = getUTCtime()
            # Rate limiting in bursts
            diff = self.reset - now
            if not self.remaining:
                self.remaining = 0.001
                diff = 180
            if (diff / self.remaining) > 1:
                # self.logger.debug("remaining: %s / till reset: %s" % (self.remaining, diff))
                delay = round(diff - self.remaining) + self.pending_requests + 1
                # self.logger.debug("sleep delay %d pending %d" % (delay, self.pending_requests))
                sleep(delay)
            req = requests.Request(verb, url, json=postdict, auth=auth, params=query)
            self.pending_requests -= 1
            prepped = self.session.prepare_request(req)
            response = self.session.send(prepped, timeout=timeout)
            self.remaining = float(
                response.headers[
                    'X-RateLimit-Remaining']) - 0.01 if 'X-RateLimit-Remaining' in response.headers else 0.001
            self.reset = int(
                response.headers['X-RateLimit-Reset']) if 'X-RateLimit-Reset' in response.headers else now + 180

            # Make non-200s throw
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            # 401 - Auth error. This is fatal with API keys.
            if (response.json()['error'] and response.json()['error'][
                'message'] == '2FA Token is required and did not match.'):
                return response.json()
            elif response.status_code == 401:
                self.logger.error("Login information or API Key incorrect, please check and restart.")
                self.logger.error("Error: " + response.text)
                if postdict:
                    self.logger.error(postdict)
                # Always exit, even if rethrow_errors, because this is fatal

                raise e
                return response.text
                # return self._curl_bitmex(api, query, postdict, timeout, verb)

            # 404, can be thrown if order canceled does not exist.
            elif response.status_code == 404:
                if verb == 'DELETE':
                    self.logger.error("Order not found: %s" % postdict['orderID'])
                    return
                self.logger.error("Unable to contact the BitMEX API (404). " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                maybe_exit(e)

            # 429, ratelimit
            elif response.status_code == 429:
                self.logger.error("Ratelimited on current request. Sleeping, then trying again. Try fewer " +
                                  "order pairs or contact support@bitmex.com to raise your limits. " +
                                  "Request: %s \n %s" % (url, json.dumps(postdict)))
                if 'Retry-After' in response.headers:
                    sleep(int(response.headers['Retry-After']) + 1)
                else:
                    self.logger.warn("no retry-after, sleeping 30s headers: %s" % response.headers)
                    sleep(30)

                sleep(1)
                return self._curl_bitmex(api, query, postdict, timeout, verb)

            # 503 - BitMEX temporary downtime, likely due to a deploy. Try again
            elif response.status_code == 503:
                self.logger.warning("Unable to contact the BitMEX API (503), retrying. " +
                                    "Request: %s \n %s" % (url, json.dumps(postdict)))
                sleep(1)
                return self._curl_bitmex(api, query, postdict, timeout, verb)

            # Duplicate clOrdID: that's fine, probably a deploy, go get the order and return it
            elif (response.status_code == 400 and
                      response.json()['error'] and
                          response.json()['error']['message'] == 'Duplicate clOrdID'):

                order = self._curl_bitmex('/order',
                                          query={'filter': json.dumps({'clOrdID': postdict['clOrdID']})},
                                          verb='GET')[0]
                if (
                                    order['orderQty'] != postdict['quantity'] or
                                    order['price'] != postdict['price'] or
                                order['symbol'] != postdict['symbol']):
                    raise Exception('Attempted to recover from duplicate clOrdID, but order returned from API ' +
                                    'did not match POST.\nPOST data: %s\nReturned order: %s' % (
                                        json.dumps(postdict), json.dumps(order)))
                # All good
                return order

            # Unknown Error
            else:
                self.logger.error("Unhandled Error: %s: %s" % (e, response.text))
                self.logger.error("Endpoint was: %s %s: %s" % (verb, api, json.dumps(postdict)))
                maybe_exit(e)

        except requests.exceptions.Timeout as e:
            # Timeout, re-run this request
            self.logger.warning("Timed out, retrying...")
            return self._curl_bitmex(api, query, postdict, timeout, verb)

        except requests.exceptions.ConnectionError as e:
            self.logger.warning("Unable to contact the BitMEX API (ConnectionError). Please check the URL. Retrying. " +
                                "Request: %s \n %s" % (url, json.dumps(postdict)))
            sleep(1)
            return self._curl_bitmex(api, query, postdict, timeout, verb)
        return response.json()
