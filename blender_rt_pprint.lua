temp = loadfile("pprint.lua")
pprint = temp()

temp, err = loadfile(arg[1])
if temp == nil then
	print(err)
	return
end
blend = temp()

out = pprint(blend)
print(out)
