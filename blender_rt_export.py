bl_info = {
	"name": "Blend RT",
	"author": "Neils Nesse",
	"blender": (2, 69, 0),
	"location": "File > Import-Export",
	"description": "Format storing a subset of blender RNA data for use in real-time renderers",
	"warning": "",
	"wiki_url": "",
	"tracker_url": "",
	"support": 'TESTING',
	"category": "Import-Export"}

import bpy
import rna_info
import pickle
from bpy.props import (StringProperty)
from bpy_extras.io_utils import (ExportHelper)

class export_BRT(bpy.types.Operator, ExportHelper):
	"""Save a BRT File"""
	bl_idname = "export_scene.brt"
	bl_label = 'Export BRT'
	bl_options = {'PRESET'}
	filename_ext = ".brt"
	filter_glob = StringProperty(default="*.BRT", options={'HIDDEN'})
	check_extension = True

	def execute(self, context):
		keywords = self.as_keywords(ignore=("filter_glob", "check_existing"))
		return save_brt(self, context, **keywords)

def menu_func_export(self, context):
	self.layout.operator(export_BRT.bl_idname, text="Blend RT (.brt)")

def register():
	bpy.utils.register_module(__name__)
	bpy.types.INFO_MT_file_export.append(menu_func_export)

def unregister():
	bpy.utils.unregister_module(__name__)
	bpy.types.INFO_MT_file_export.remove(menu_func_export)


def encode_prop_array(a, size):
	b = []
	for i in range(len(a)):
		b.append(encode_basic_property(a[i], size/len(a)))
	return b

def encode_basic_property(data, size):
	type_name = type(data).__name__
	if type_name in ('bool','float','string','str', 'int', 'tuple'):
		out = data
	elif type_name == "Vector":
		out = data.to_tuple()
	elif type_name == "Color":
		out = (data.r, data.g, data.b)
	elif type_name == "Matrix":
		if size == 16:
			out = data[0].to_tuple() + data[1].to_tuple() + data[2].to_tuple() + data[3].to_tuple()
		elif size == 9:
			out = data[0].to_tuple() + data[1].to_tuple() + data[2].to_tuple()
		elif size == 4:
			out = data[0].to_tuple() + data[1].to_tuple()
	elif type_name == "Quaternion":
		out = (data.x, data.y, data.z, data.w)
	elif type_name == "Euler":
		out = (data.x, data.y, data.z, data.order)
	elif type_name == "bpy_prop_array":
		out = encode_prop_array(data, size)
	else:
		out = "unknown:" + type_name
	#TODO: 'set' types
	return out

def encode_property(structs, prop, data):
	out = ()
	if prop.fixed_type is None:
		out = encode_basic_property(data, prop.array_length)
	else:
		if prop.type == "collection":
			out = {}
			for key, value in data.items():
				out[key] = encode_struct(structs, structs[prop.fixed_type.identifier], value)
		else:
			out = encode_struct(structs, structs[prop.fixed_type.identifier], data)
	return out

def encode_struct(structs, struct, data):
	out = {}

	for prop in struct.properties:
		if prop.identifier is None:
			continue
		data_next = getattr(data, prop.identifier, None)
		if data_next is None:
			continue
		out[prop.identifier] = encode_property(structs, prop, data_next)
	return out


def save_brt(operator, context, filepath=""):
	structs_list, funcs, ops, props = rna_info.BuildRNAInfo()
	structs = {}

	#Convert list of structs into a dictionary
	for struct in structs_list.values():
		structs[struct.identifier] = struct

	file = open(filepath, "wb")

	#Encode blend data as dictionaries, tuples, and builtin's only
	out = encode_struct(structs, structs['BlendData'], context.blend_data)
	pickle.dump(out, file, 2)
	file.close()
	return {'FINISHED'}
