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

def dearray(a):
	b = []
	for i in range(len(a)):
		if type(a[i]).__name__ == 'bpy_prop_array':
			b.append(dearray(a[i]))
		else:
			b.append(a[i])
	return b

def encode_struct(structs, struct, data):
	out = {}

	for prop in struct.properties:
		if prop.identifier is None:
			continue
		data_next = getattr(data, prop.identifier, None)
		if data_next is None:
			continue
		if prop.fixed_type is None:
			type_name = type(data_next).__name__
			if type_name in ('bool','float','string','str', 'int', 'tuple'):
				out[prop.identifier] = data_next
			elif type_name == "Vector":
				out[prop.identifier] = data_next.to_tuple()
			elif type_name == "Color":
				out[prop.identifier] = (data_next.r, data_next.g, data_next.b)
			elif type_name == "Matrix":
				if prop.array_length == 16:
					out[prop.identifier] = data_next[0].to_tuple() + data_next[1].to_tuple() + data_next[2].to_tuple() + data_next[3].to_tuple()
				elif prop.array_length == 9:
					out[prop.identifier] = data_next[0].to_tuple() + data_next[1].to_tuple() + data_next[2].to_tuple()
				elif prop.array_length == 4:
					out[prop.identifier] = data_next[0].to_tuple() + data_next[1].to_tuple()
			elif type_name == "Quaternion":
				out[prop.identifier] = (data_next.x, data_next.y, data_next.z, data_next.w)
			elif type_name == "bpy_prop_array":
				out[prop.identifier] = dearray(data_next)
			else:
				out[prop.identifier] = "unknown:" + type_name
			#TODO: handle 'Euler' and 'set' types
		else:
			if prop.type == "collection":
				collection = {}
				out[prop.identifier] = collection
				for key, value in data_next.items():
					collection[key] = encode_struct(structs, structs[prop.fixed_type.identifier], value)
			else:
				out[prop.identifier] = encode_struct(structs, structs[prop.fixed_type.identifier], data_next)
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
