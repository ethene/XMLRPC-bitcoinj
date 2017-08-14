import hashlib
import hmac
import time

from future.builtins import bytes
from future.standard_library import hooks
from requests.auth import AuthBase

with hooks():  # Python 2/3 compat
    from urllib.parse import urlparse


class APIKeyAuthWithExpires(AuthBase):
    """Attaches API Key Authentication to the given Request object. This implementation uses `expires`."""

    def __init__(self, apiKey, apiSecret):
        """Init with Key & Secret."""
        self.apiKey = apiKey
        self.apiSecret = apiSecret

    def __call__(self, r):
        """
        Called when forming a request - generates api key headers. This call uses `expires` instead of nonce.

        This way it will not collide with other processes using the same API Key if requests arrive out of order.
        For more details, see https://www.bitmex.com/app/apiKeys
        """
        # modify and return the request
        expires = int(round(time.time()) + 35)  # 5s grace period in case of clock skew
        r.headers['api-expires'] = str(expires)
        r.headers['api-key'] = self.apiKey
        signature = self.generate_signature(self.apiSecret, r.method, r.url, expires, r.body or '')
        # print (str(expires))
        # print (signature)
        r.headers['api-signature'] = signature

        return r

    # Generates an API signature.
    # A signature is HMAC_SHA256(secret, verb + path + nonce + data), hex encoded.
    # Verb must be uppercased, url is relative, nonce must be an increasing 64-bit integer
    # and the data, if present, must be JSON without whitespace between keys.
    #
    # For example, in psuedocode (and in real code below):
    #
    # verb=POST
    # url=/api/v1/order
    # nonce=1416993995705
    # data={"symbol":"XBTZ14","quantity":1,"price":395.01}
    # signature =
    #   HEX(HMAC_SHA256(secret, 'POST/api/v1/order1416993995705{"symbol":"XBTZ14","quantity":1,"price":395.01}'))
    def generate_signature(self, secret, verb, url, nonce, data):
        """Generate a request signature compatible with BitMEX."""
        # Parse the url so we can remove the base and extract just the path.
        parsedURL = urlparse(url)
        path = parsedURL.path
        if parsedURL.query:
            path = path + '?' + parsedURL.query

        try:
            data = data.decode()
        except AttributeError:
            pass
        '''
        print (type(verb))
        print(type(path))
        print(type(nonce))
        print(type(data))
        print(verb)
        print(path)
        print(nonce)
        print(data)

        message = bytes(verb, 'utf8') + bytes(path, 'utf8') + bytes(nonce) + bytes(data, 'utf8')
        message = verb + path + str(nonce) + data
        '''
        message = bytes(verb + path, 'utf8') + bytes(str(nonce), 'utf8') + bytes(data, 'utf8')

        signature = hmac.new(bytes(secret, 'utf8'), message, digestmod=hashlib.sha256).hexdigest()
        return signature
