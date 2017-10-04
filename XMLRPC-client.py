#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

import xmlrpc.client

s = xmlrpc.client.ServerProxy('http://localhost:8000')
# print("New address: %s " % (s.getNewAddress()))

print("TX: %s " % (s.getUnconfirmedTransactions('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT')))

print("Input value: %s" % s.getInputValue('ms4g4oBvhSM31kFrPNfXse8E4uRG7Xz2x4'))

# sr = s.sendCoins('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT', 'mwCwTceJvYV27KXBc3NJZys6CjsgsoeHmf', 10000000)

# print("send: %s" % sr)

# Print list of available methods
print(s.system.listMethods())
