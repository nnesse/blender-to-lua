#!/usr/bin/python3
import pprint
import pickle
import sys

if len(sys.argv)> 1:
	file = open(sys.argv[1], 'rb')
	data = pickle.load(file)
	pprint.pprint(data)
