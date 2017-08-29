import xmlrpc.client

s = xmlrpc.client.ServerProxy('http://localhost:8000')
# print("New address: %s " % (s.getNewAddress()))

# print("TX: %s " % (s.getUnconfirmedTransactions('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT')))

tx = s.sendCoins('myt8kNqVm6p8s1F9fp3e4vYQuLCZ8cw3mT', 'mwCwTceJvYV27KXBc3NJZys6CjsgsoeHmf', 50000000)
if tx > 0:
    print("send: %s" % tx)

# Print list of available methods
print(s.system.listMethods())
