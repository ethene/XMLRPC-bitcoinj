import xmlrpc.client

s = xmlrpc.client.ServerProxy('http://localhost:8000')
print("New address: %s " % (s.getNewAddress()))

# Print list of available methods
print(s.system.listMethods())
