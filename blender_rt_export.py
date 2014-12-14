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

def encode_struct(structs, struct, data):
	out = {}
	for prop in struct.properties:
		#TODO: Look at base class properties as well
		if prop.identifier is None:
			continue
		data_next = getattr(data, prop.identifier, None)
		if data_next is None:
			continue
		if prop.fixed_type is None:
			if type(data_next).__name__ in ('bool','float','string','tuple'):
				out[prop.identifier] = data_next
			#TODO: Handle blender classes Vector, Color, etc so we actually get all the data
		if prop.fixed_type:
			if prop.type == "collection":
				collection = {}
				out[prop.identifier] = collection
				for key, value in data_next.items():
					collection[key] = encode_struct(structs, structs[prop.fixed_type.identifier], value)
			else:
				out[prop.identifier] = encode_struct(structs, structs[prop.fixed_type.identifier], data_next)
	return out


def save_brt(operator, context, filepath=""):
	scene = context.scene
	structs_list, funcs, ops, props = rna_info.BuildRNAInfo()
	structs = {}

	#Convert list of structs into a dictionary
	for struct in structs_list.values():
		structs[struct.identifier] = struct

	file = open(filepath, "wb")

	#Encode blend data as structs and tuples
	out = encode_struct(structs, structs['BlendData'], context.blend_data)
	pickle.dump(out, file, 2)
	file.close()
	return {'FINISHED'}
