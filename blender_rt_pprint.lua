temp = loadfile("pprint.lua")
pprint = temp()

temp = loadfile(arg[1])
blend = temp()

out = pprint(blend)
print(out)
