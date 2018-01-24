#!/home/strky/anaconda3/envs/py36/bin/python
#  -*- coding: utf-8 -*-

import xmlrpc.client

s = xmlrpc.client.ServerProxy('http://localhost:8000')
# print("New address: %s " % (s.getNewAddress()))
# print("TX: %s " % (s.getUnconfirmedTransactions('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT')))

# sr = s.sendCoins('mr8jVeCUr8gHMUzzs79PHoD5VG14oG3oPi', '2N8hwP1WmJrFF5QWABn38y63uYLhnJYJYTF', 10000000)

# print("send: %s" % sr)

# Print list of available methods
print(s.system.listMethods())

print(s.getWalletBalance())
