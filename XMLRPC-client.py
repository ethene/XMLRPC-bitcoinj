#!/home/strky/anaconda3/envs/py36/bin/python
#  -*- coding: utf-8 -*-

import os
import xmlrpc.client


def get_bitcoinj_XMLRPC():
    XMLRPCServer_bitcoinj = xmlrpc.client.ServerProxy('http://' + bitcoinj_host + ':' + bitcoinj_port)
    return XMLRPCServer_bitcoinj


bitcoinj_host = os.getenv('BITCOINJ_HOST', 'localhost')
bitcoinj_port = os.getenv('BITCOINJ_PORT', '8010')

# print("New address: %s " % (s.getNewAddress()))
# print("TX: %s " % (s.getUnconfirmedTransactions('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT')))
# sr = s.sendCoins('mr8jVeCUr8gHMUzzs79PHoD5VG14oG3oPi', '2N8hwP1WmJrFF5QWABn38y63uYLhnJYJYTF', 10000000)
# print("send: %s" % sr)

b = get_bitcoinj_XMLRPC()

# Print list of available methods
print(b.system.listMethods())
print(b.getWalletBalance())
