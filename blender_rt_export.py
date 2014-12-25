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


def encode_string(strings, s):
	strings.append("'%s'" % s.replace("'","\\'"))

def encode_prop_array(strings, a):
	if len(a) > 1024:
		return
	for i in range(len(a)):
		b = a[i]
		type_name = type(b).__name__
		if type_name == 'bpy_prop_array':
			encode_prop_array(strings, b)
		elif type_name in ('string','str'):
			encode_string(strings, data)
			strings.append(",")
		elif type_name == 'bool':
			if b:
				strings.append("true,")
			else:
				strings.append("false,")
		else:
			strings.append(str(b))
			strings.append(",")
	return

def encode_tuple(strings, t):
	strings.append("{")
	for x in t:
		strings.append("%f," % x)
	strings.append("}")

def encode_property(strings, data, size):
	type_name = type(data).__name__
	if type_name == 'bool':
		if data:
			strings.append("true")
		else:
			strings.append("false")
	elif type_name in ('string','str'):
		encode_string(strings, data)
	elif type_name == 'tuple':
		encode_tuple(strings, data)
	elif type_name in ('float', 'int'):
		strings.append(str(data))
	elif type_name == "Vector":
		encode_tuple(strings, data.to_tuple())
	elif type_name == "Color":
		encode_tuple(strings, (data.r, data.g, data.b))
	elif type_name == "Matrix":
		out = ()
		if size == 16:
			out = data[0].to_tuple() + data[1].to_tuple() + data[2].to_tuple() + data[3].to_tuple()
		elif size == 9:
			out = data[0].to_tuple() + data[1].to_tuple() + data[2].to_tuple()
		elif size == 4:
			out = data[0].to_tuple() + data[1].to_tuple()
		encode_tuple(strings, out)
	elif type_name == "Quaternion":
		encode_tuple(strings, (data.x, data.y, data.z, data.w))
	elif type_name == "Euler":
		strings.append("{%f,%f,%f,%s}" % (data.x, data.y, data.z, data.order))
	elif type_name == "bpy_prop_array":
		strings.append("{")
		encode_prop_array(strings, data)
		strings.append("}")
	else:
		strings.append("nil")
	#TODO: 'set' types
	return


def encode_struct_inline(file, strings, structs, struct, data, item_count, data_map):
	struct_ = struct
	strings.append("{")
	while struct_:
		for prop in struct_.properties:
			if prop.identifier is None:
				continue
			data_next = getattr(data, prop.identifier, None)
			if data_next is None:
				continue
			if prop.fixed_type is not None:
				next_struct = structs.get(prop.fixed_type.identifier, None)
				if next_struct is None:
					continue
				inline = len(next_struct.references) == 1
				strings.append("['%s']=" % prop.identifier.replace("'","\\'"))
				if prop.type == "collection":
					strings.append("{")
					expected_int_key = 0
					for key, value in data_next.items():
						if inline:
							item_count = encode_struct_inline(file, strings, structs, next_struct, value, item_count, data_map)
							strings.append(",")
						else:
							index, item_count = encode_struct(file, structs, next_struct, value, item_count, data_map)
							if type(key).__name__ == 'int':
								if key == expected_int_key:
									strings.append("g[%d]," % index)
									expected_int_key = expected_int_key + 1
								else:
									strings.append("[%d]=g[%d]," % (key + 1, index))
									expected_int_key = key + 1
							else:
								strings.append("['%s']=g[%d]," % (key.replace("'","\\'"), index))
					strings.append("}")
				else:
					if inline:
						item_count = encode_struct_inline(file, strings, structs, next_struct, data_next, item_count, data_map)
					else:
						index, item_count = encode_struct(file, structs, next_struct, data_next, item_count, data_map)
						strings.append("g[%d]" % (index))
			else:
				strings.append("['%s']=" % prop.identifier.replace("'","\\'"))
				encode_property(strings, data_next, prop.array_length)
			strings.append(",")
		struct_ = struct_.base
	strings.append("}")
	return item_count


def encode_struct(file, structs, struct, data, item_count, data_map):
	if data.as_pointer() not in data_map:
		strings = []
		index = item_count
		data_map[data.as_pointer()] = index
		item_count = item_count + 1
		strings.append("g[%d]=" % index)
		item_count = encode_struct_inline(file, strings, structs, struct, data, item_count, data_map)
		for s in strings:
			file.write(s)
		file.write("\n")
	else:
		index = data_map[data.as_pointer()]
	return index, item_count

def save_brt(operator, context, filepath=""):
	structs_list, funcs, ops, props = rna_info.BuildRNAInfo()
	structs = {}

	#Convert list of structs into a dictionary
	for struct in structs_list.values():
		if struct.identifier not in ['KeyMapItem', 'Brush', 'WindowManager', 'Screen']:
			structs[struct.identifier] = struct

	file = open(filepath, "wt")

	#Write blend data as LUA script
	file.write("local g={}\n")
	data_map = {}
	item_count = 1
	meshes = []
	for x in context.scene.objects:
		try:
			mesh = x.to_mesh(context.scene, False, 'PREVIEW', False)
		except RuntimeError:
			mesh = None
		if mesh is None:
			continue
		meshes.append(mesh)
	root_index, item_count = encode_struct(file, structs, structs['BlendData'], context.blend_data, item_count, data_map)
	for mesh in meshes:
		bpy.data.meshes.remove(mesh)
	file.write("return g[%d]\n" % root_index);

	file.close()
	return {'FINISHED'}
