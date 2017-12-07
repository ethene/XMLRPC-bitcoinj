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
        if fee:
            postdict = {
                'amount': amount,
                'fee': fee,
                'currency': 'XBt',
                'address': address,
                'otpToken': otptoken
            }
        else:
            postdict = {
                'amount': amount,
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

    def _curl_bitmex(self, api, query=None, postdict=None, timeout=10, verb=None, rethrow_errors=True):
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

            # Unknown Error
            else:
                self.logger.error("Unhandled Error: %s: %s" % (e, response.text))
                self.logger.error("Endpoint was: %s %s: %s" % (verb, api, json.dumps(postdict)))
                maybe_exit(e)
                return response.text

        except Exception as e:
            return str(e)
        return response.json()
