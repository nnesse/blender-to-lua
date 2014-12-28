bl_info = {
	"name": "Blend RT",
	"author": "Neils Nesse",
	"blender": (2, 69, 0),
	"location": "File > Import-Export",
	"description": "Write blend data to a LUA script + a binary blob",
	"warning": "",
	"wiki_url": "",
	"tracker_url": "",
	"support": 'TESTING',
	"category": "Import-Export"}

import bpy
import mathutils
import array
import bmesh
from bpy.props import (StringProperty)
from bpy_extras.io_utils import (ExportHelper)

#
# root table:
#
# 	meshes = {[mesh_name] = mesh, ...}
# 	actions = {[action_name] = action, ...}
#	armatures = {[armature_name] = armature, ...}
#
# mesh table:
#
#	num_triangles             : Number of triangles in mesh
#	num_vertices              : Number of verticies in mesh
#	normals                   : true if normals are stored in the mesh data
#	num_uv_layers             : Number of uv layers stored in mesh data
#	num_vertex_weights        : Total number of vertex weights stored in mesh data
#	blob_offset               : Offset of mesh data in binary blob
#
# mesh blob data:
#
#	uint16_t triangle_indicies[num_triangles][3];
#	struct {
#		float coord[3];
#		float normal[normals ? 3 : 0];
#		float uv[num_uv_layers][2];
#	} vertex_data[num_verticies];
#	uint8_t vertex_weight_counts[num_verticies];       // Number of vertex weights for each vertex
#	uint16_t vertex_group_groups[num_vertex_weights];  // Group number for each vertex weight
#	uint16_t vertex_group_weights[num_vertex_weights]; // Fixed point weight of each vertex with 15 fractional bits
#	                                                   // i.e. maximum weight is 2.0f
#
#	Weights for vertex N will be stored at the index: sum(vertex_weight_counts[i] for i in 0..(N-1)).
#
# action table:
#
#	frame_start            : First frame of action
#       frame_end              : Last frame of action
#       step                   : Frames between samples (float)
#       num_samples            : Number of samples in action
#       num_fcurves            : Number of fcurves
#	blob_offset            : Offset of action data in binary blob
#	{fcurve, fcurve, ...}
#
# action blob data:
#
#	float samples[num_samples][num_fcurves];
#
# fcurve table:
#
#	path                   : Path of property controlled by the curve
#	array_index            : Array index within property (for vector/matrix types)
#
# armature table:
#	bones = {['bone_name'] = {bone}, ...}
#
# bone table:
#	tail   : location of tail of bone in object space (vec3)
#	matrix : Bone to object space transform
#	parent : Name of parent bone or nil of the bone has no parent
#

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


def mesh_triangulate(me):
	bm = bmesh.new()
	bm.from_mesh(me)
	bmesh.ops.triangulate(bm, faces=bm.faces)
	bm.to_mesh(me)
	bm.free()

def lua_string(s):
	return "'%s'" % s.replace("'","\\'")

def lua_vec3(v):
	return "{%f,%f,%f}" % v.to_tuple()

def lua_vec4(v):
	return "{%f,%f,%f,%f}" % v.to_tuple()

def lua_mat4(m):
	return "{%s, %s, %s, %s}" % tuple(lua_vec4(m[i]) for i in range(4))

def write_action(write, blob_file, action):
	write("\t[%s]={\n" % lua_string(action.name))
	frame_start = action.frame_range[0]
	frame_end = action.frame_range[1]
	write("\t\tframe_start=%d,\n" % frame_start)
	write("\t\tframe_end=%d,\n" % frame_end)
	write("\t\tstep=1.0,\n")
	write("\t\tblob_offset=%d,\n" % blob_file.tell())
	write("\t\tnum_fcurves=%d,\n" % len(action.fcurves))
	for fcurve in action.fcurves:
		write("\t\t{path=%s,array_index=%d},\n" % (lua_string(fcurve.data_path), fcurve.array_index))

	samples_array = array.array('f')
	frame = frame_start
	num_samples = 0
	while frame <= frame_end:
		for fcurve in action.fcurves:
			samples_array.append(fcurve.evaluate(frame))
		frame += 1.0
		num_samples = num_samples + 1
	samples_array.tofile(blob_file)
	write("\t\tnum_samples=%d\n" % num_samples)
	write("\t},\n")

def write_mesh(write, blob_file, name, mesh):
	mesh_triangulate(mesh)
	mesh.calc_normals_split()
	smooth_groups, num_groups = mesh.calc_smooth_groups()

	if len(mesh.polygons) == 0:
		return

	vertex_dict = {} #Dictionary to identify when a vertex is shared by multiple triangles
	loop_to_vertex_num = [None] * len(mesh.loops) #Vertex index in output array for a loop
	index_array = array.array('H')  #Vertex index triplets for mesh triangles
	vertex_array = array.array('f') #Per vertex floating point data (interleaved)
	vertex_weight_counts = array.array('B') # Number of weights in each vertex
	vertex_group_weights = array.array('H') # Vertex weights
	vertex_group_groups = array.array('H')  # Vertex weight group #'s
	vertex_count = 0

	for polygon_index, polygon in enumerate(mesh.polygons):
		for loop_index in polygon.loop_indices:
			vertex_key_l = [mesh.loops[loop_index].vertex_index, smooth_groups[polygon_index]]
			for uv_layer in mesh.uv_layers:
				vertex_key_l.extend(uv_layer.data[loop_index].uv)
			vertex_key = tuple(vertex_key_l)

			if vertex_key in vertex_dict:
				vertex_num = vertex_dict[vertex_key]
			else:
				mesh_loop = mesh.loops[loop_index]
				vertex = mesh.vertices[mesh_loop.vertex_index]
				vertex_dict[vertex_key] = vertex_count
				vertex_num = vertex_count
				vertex_count = vertex_count + 1
				vertex_array.extend(vertex.undeformed_co)
				vertex_array.extend(mesh_loop.normal)

				for uv_layer in mesh.uv_layers:
					vertex_array.extend(uv_layer.data[loop_index].uv)

				for elem in vertex.groups:
					vertex_group_groups.append(elem.group)
					vertex_group_weights.append(int(elem.weight * 256 * 128))
				vertex_weight_counts.append(len(vertex.groups))
			loop_to_vertex_num[loop_index] = vertex_num

	write("\t['%s'] = {\n" % name)
	write("\t\tblob_offset = %d,\n" % blob_file.tell())
	write("\t\tnum_triangles = %d,\n" % len(mesh.polygons))
	write("\t\tnum_verticies = %d,\n" % vertex_count)
	write("\t\tnormals = true,\n")
	write("\t\tnum_uv_layers = %d,\n" % len(mesh.uv_layers))
	write("\t\tuv_layers = {")
	for uv_layer in mesh.uv_layers:
		write("%s," % lua_string(uv_layer.name))
	write("},\n");
	write("\t\tnum_vertex_weights = %d\n" %  len(vertex_group_groups))
	write("\t},\n");

	for polygon_index, polygon in enumerate(mesh.polygons):
		for loop_index in polygon.loop_indices:
			index_array.append(loop_to_vertex_num[loop_index])

	index_array.tofile(blob_file)
	vertex_array.tofile(blob_file)
	vertex_weight_counts.tofile(blob_file)
	vertex_group_groups.tofile(blob_file)
	vertex_group_weights.tofile(blob_file)
	return

def write_bone(write, blob_file, bone):
	write("\t\t\t[%s] = {\n" % lua_string(bone.name))
	write("\t\t\t\ttail=%s,\n" % lua_vec3(bone.tail_local))
	write("\t\t\t\tmatrix=%s,\n" % lua_mat4(bone.matrix_local))
	if bone.parent:
		write("\t\t\t\tparent=%s,\n" % lua_string(bone.parent.name))
	write("\t\t\t},\n")
	return

def write_armature(write, blob_file, armature):
	write("\t[%s] = {\n" % lua_string(armature.name))
	write("\t\tbones = {")
	for bone in armature.bones:
		write_bone(write, blob_file, bone)
	write("\t\t}")
	write("\t}\n")
	return

def save_brt(operator, context, filepath=""):
	lua_file = open(filepath + ".lua", "wt")
	blob_file = open(filepath + ".blob", "wb")

	def write_lua(s):
		lua_file.write(s)

	file = open(filepath, "wt")

	#Write blend data as LUA script
	write_lua("return {\n")

	write_lua("meshes={\n")
	arrays = []
	for x in context.scene.objects:
		try:
			mesh = x.to_mesh(context.scene, False, 'PREVIEW', False)
		except RuntimeError:
			mesh = None
		if mesh is None:
			continue
		write_mesh(write_lua, blob_file, x.name, mesh)
		bpy.data.meshes.remove(mesh)
	write_lua("},\n")
	write_lua("actions={\n")
	for action in context.blend_data.actions:
		write_action(write_lua, blob_file, action)
	write_lua("},\n")
	write_lua("armatures={\n")
	for armature in context.blend_data.armatures:
		write_armature(write_lua, blob_file, armature)
	write_lua("},\n")

	write_lua("}\n")

	lua_file.close()
	blob_file.close()
	return {'FINISHED'}
