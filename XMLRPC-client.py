#!/home/strky/anaconda3/envs/py36/bin/python
# -*- coding: utf-8 -*-

import xmlrpc.client

s = xmlrpc.client.ServerProxy('http://localhost:8000')
# print("New address: %s " % (s.getNewAddress()))

# print("TX: %s " % (s.getUnconfirmedTransactions('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT')))

print(s.getInputValue('mitC6TC6r4Pfh3FVw6C4L7DKXJTvbj5UPT'))
print("Input value: %s" % s.getInputValue('mitC6TC6r4Pfh3FVw6C4L7DKXJTvbj5UPT'))

# sr = s.sendCoins('mqzTdGgk3rGvWPu47LFDMakCpJ3nS4HGXB', 'mitC6TC6r4Pfh3FVw6C4L7DKXJTvbj5UPT', 10000000)

#print("send: %s" % sr)

# Print list of available methods
print(s.system.listMethods())
