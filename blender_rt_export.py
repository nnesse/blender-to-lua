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
	out = ()
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
	#TODO: we need another solution for BPY prop array, this is too slow
	#elif type_name == "bpy_prop_array":
	#	out = encode_prop_array(data, size)
	else:
		out = "unknown:" + type_name
	#TODO: 'set' types
	return out

def struct_has_base(base, struct):
	return base in struct.get_bases()

def encode_property(structs, prop, data, in_id, data_list, data_map):
	out = ()
	if prop.fixed_type is None:
		out = encode_basic_property(data, prop.array_length)
	else:
		next_struct = structs.get(prop.fixed_type.identifier, None)
		if next_struct is None:
			return None
		if prop.type == "collection":
			out = {}
			for key, value in data.items():
				out[key] = encode_struct(structs, next_struct, value, in_id, data_list, data_map)
		else:
			out = encode_struct(structs, next_struct, data, in_id, data_list, data_map)
	return out

def encode_struct(structs, struct, data, in_id, data_list, data_map):
	this_is_id = (struct.base and struct.base.identifier == 'ID') or struct.identifier == 'ID'
	if this_is_id and in_id:
		return data.name
	elif data.as_pointer() in data_map:
		return data_map[data.as_pointer()]
	else:
		out = {}
		next_data_list = data_list
		inline = len(struct.references) == 1 and in_id
		if not inline:
			if data_list.get(struct.identifier, None) is None:
				data_list[struct.identifier] = []
			data_map[data.as_pointer()] = len(data_list[struct.identifier])
			data_list[struct.identifier].append(out)
		if this_is_id:
			out['z_list'] = {}
			next_data_list = out['z_list']

		struct_ = struct
		while struct_:
			for prop in struct_.properties:
				if prop.identifier is None or (prop.is_readonly and prop.type != "collection"):
					continue
				data_next = getattr(data, prop.identifier, None)
				if data_next is None:
					continue
				value = encode_property(structs, prop, data_next, in_id or this_is_id, next_data_list, data_map)
				if value is not None:
					out[prop.identifier] = value
			struct_ = struct_.base

		if inline:
			return out
		else:
			return (len(data_list[struct.identifier]) - 1)


def save_brt(operator, context, filepath=""):
	structs_list, funcs, ops, props = rna_info.BuildRNAInfo()
	structs = {}

	#Convert list of structs into a dictionary
	for struct in structs_list.values():
		structs[struct.identifier] = struct

	#Remove blacklisted struct types
	blacklist = ['KeyMapItem', 'Brush', 'WindowManager', 'Screen']
	for x in blacklist:
		if x in structs:
			del structs[x]


	file = open(filepath, "wb")

	#Encode blend data as dictionaries, tuples, and sequences only
	data_map = {}
	data_list = {'z_data': {}}
	data_list['data'] = encode_struct(structs, structs['BlendData'], context.blend_data, False, data_list['z_data'], data_map)
	for x in context.scene.objects:
		try:
			mesh = x.to_mesh(context.scene, False, 'PREVIEW', False)
		except RuntimeError:
			mesh = None
		if mesh is None:
			continue
		encode_struct(structs, structs['Mesh'], mesh, False, data_list['z_data'], data_map)
		bpy.data.meshes.remove(mesh)
	pickle.dump(data_list, file, 2)
	file.close()
	return {'FINISHED'}
