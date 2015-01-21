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
# table:
#
#	scene     : scene_table
#
# 	meshes    : {[mesh_name] = mesh, ...}
#
# 	actions   : {[action_name] = action, ...}
#
#	armatures : {[armature_name] = armature, ...}
#
# scene table
#
#	frame_start : first frame of animation
#
#	frame_end   : last frame of animation
#
#	frame_step  : Number of frames per "step"
#
#	object_table, object_table, ...
#
# object table:
#
#	type                : Type of data this object refers to. One of ‘MESH’, ‘CURVE’, ‘SURFACE’, ‘META’,
#	                      ‘FONT’, ‘ARMATURE’, ‘LATTICE’, ‘EMPTY’, ‘CAMERA’, ‘LAMP’, ‘SPEAKER’
#
#	data                : Name of data this object refers to. Data will be found in it's corresponding
#	                      type specific table inside the root table.
#
#	vertex_groups = {group_name, group_name, ... } : Names of the vertex groups for this object.
#
#	bone_names = {bone_name, bone_name, ... }      : Name of the bones for pose data
#
#	animated = true | false                        : 'true' if this object has an animation block i.e. there may be per frame pose
#	                                                 and object transform data
#
#	transform_array_offset                         : Array of transforms including object local transforms and pose bone transforms
#	                                                 Transforms are stored as 4x4 column major order matricies. Pose bone transforms
#                                                        are in object local space. (blob)
#
#		float transform_array[animated ? <frame steps in scene> : 1][1 + #bone_names][16]
#
#		Object transforms are stored at 'transform[frame_step][0]' and pose bone transforms are
#		stored in transform[frame_step][i] where i one based index into 'bone_names'
#
#	nla_tracks = {nla_track, nla_track, ...}       : Array of NLA tracks in bottom up order
#
# NLA track table:
#
#	name   : Name of NLA track
#
#	nla_strip, nla_strip, ...
#
# NLA strip table:
#
#	name               : Name of NLA strip
#
#	action             : Name of action referenced by this strip
#
#	frame_start        : First frame of strip
#
#	frame_end          : Last frame of strip
#
#	action_frame_start : First frame referenced from action
#
#	action_frame_end   : Last frame referenced from action
#
# mesh table:
#
#	num_triangles                 : Number of triangles in mesh
#
#	num_vertices                  : Number of verticies in mesh
#
#	uv_layers = {layer_name, ...} : Names of UV layers
#
#	num_vertex_weights            : Total number of vertex weights stored in mesh data
#
#	index_array_offset            : Vertex array indicies for mesh triangles (blob)
#
#		uint16_t index_array[num_triangles][3]; //Indicies into vertex arrays
#
#	vertex_co_array_offset        : Vertex coordinates (blob)
#
#		float coord_array[num_verticies][3];
#
#	vertex_normal_array_offset    : Vertex normals (blob)
#
#		float normal_array[num_verticies][3];
#
#	uv_array_offset               : UV coordinate arrays (blob)
#
#		float uv[num_verticies][#uv_layers][2];
#
#	weight_count_array_offset     : Number of weights in for each vertex (blob)
#
#		uint8_t weight_count_array[num_verticies];
#
#	weight_array_offset           : Vertex weights for all verticies concatenated in order (blob)
#
# 		uint16_t weight_array[num_vertex_weights]; //15 bit unsigned fixed point weights (i.e. 2.0f max)
#
#	group_index_array_offset      : Group indicies for vertex weight's
#
#		uint16_t group_index_array[num_vertex_weights]; //Indicies into vertex group array
#
# action table:
#
#	frame_start            : First frame of action
#
#       frame_end              : Last frame of action
#
#       step                   : Frames between samples (float)
#
#       num_samples            : Number of fcurve samples in action
#
#	id_root                : Data type this action should be applied to ('MESH', 'OBJECT', etc)
#
#       total_num_fcurves      : Total number of fcurves
#
#	fcurve_array_offset    : FCurve samples (blob)
#
#		float samples[num_samples][num_fcurves];
#
#	fcurve_group, fcurve_group, ... : Function curve groups
#
# fcurve_group:
#
#	path        : Path to property controlled by the curves in this group
#
#	num_fcurves : Number of fcurves in this group
#
# fcurve table:
#
#	path                   : Path of property controlled by the curve
#
#	array_index            : Array index within property (for vector/matrix types)
#
# armature table:
#
#	tail_array_offset      : Array of bone tail positions in object local (blob)
#
#		float tail_array[#armature][3]
#
#	transform_array_offset : Array of bone transforms in object local space. Stored as 4x4 column
#	                         major order matricies. Position (0,0,0) in bone space is the location
#	                         of the head of the bone (blob)
#
#		float transform_array[#armature][16]
#
#	bone, bone, ...
#
# bone table:
#
#	name   : Name of the bone
#
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
	return

def lua_string(s):
	return "'%s'" % s.replace("'","\\'")

def lua_vec3(v):
	return "{%f,%f,%f}" % v.to_tuple()

def lua_vec4(v):
	return "{%f,%f,%f,%f}" % v.to_tuple()

def lua_mat4(m):
	return "{%s,%s,%s,%s}" % tuple(lua_vec4(m[i]) for i in range(4))

def lua_array3f(a):
	return "{%f,%f,%f}" % (a[0],a[1],a[2])

def lua_array4f(a):
	return "{%f,%f,%f,%f}" % (a[0],a[1],a[2],a[3])

#def write_transform(write, indent, obj):
#	write("%slocation = %s,\n" % (indent, lua_vec3(obj.location)))
#	write("%sscale = %s,\n" % (indent, lua_vec3(obj.scale)))
#	write("%srotation_mode = %s,\n" % (indent, lua_string(obj.rotation_mode)))
#	if obj.rotation_mode == 'QUATERNION':
#		write("%srotation_quaternion = %s,\n" % (indent, lua_array4f(obj.rotation_quaternion)))
#	elif obj.rotation_mode == 'AXIS_ANGLE':
#		write("%srotation_axis_angle = %s,\n" % (indent, lua_array4f(obj.rotation_axis_angle)))
#	else:
#		write("%srotation_euler = %s,\n" % (indent, lua_array3f(obj.rotation_euler)))

def write_action(write, blob_file, action):
	write("\t[%s]={\n" % lua_string(action.name))
	frame_start = action.frame_range[0]
	frame_end = action.frame_range[1]
	write("\t\tframe_start=%d,\n" % frame_start)
	write("\t\tframe_end=%d,\n" % frame_end)
	write("\t\tid_root=%s,\n" % lua_string(action.id_root))
	write("\t\tstep=1.0,\n")
	write("\t\tfcurve_array_offset=%d,\n" % blob_file.tell())
	write("\t\ttotal_num_fcurves=%d,\n" % len(action.fcurves))
	path = ""
	num_elem = 0
	for fcurve in action.fcurves:
		if fcurve.data_path != path:
			if num_elem != 0:
				write("\t\t{path=%s,num_fcurves=%d},\n" % (lua_string(path), num_elem))
			path = fcurve.data_path
			num_elem = 1
		else:
			num_elem = num_elem + 1
	if path != "" and num_elem != 0:
		write("\t\t{path=%s,num_fcurves=%d},\n" % (lua_string(path), num_elem))

	fcurve_array = array.array('f')
	frame = frame_start
	num_samples = 0
	while frame <= frame_end:
		for fcurve in action.fcurves:
			fcurve_array.append(fcurve.evaluate(frame))
		frame += 1.0
		num_samples = num_samples + 1
	fcurve_array.tofile(blob_file)
	write("\t\tnum_samples=%d\n" % num_samples)
	write("\t},\n")

def write_mesh(write, blob_file, name, mesh):
	mesh = mesh.copy() #Make a copy of the mesh so we can alter it
	mesh_triangulate(mesh)
	mesh.calc_normals_split()
	smooth_groups, num_groups = mesh.calc_smooth_groups()

	if len(mesh.polygons) == 0:
		return

	vertex_dict = {} #Dictionary to identify when a vertex is shared by multiple triangles
	loop_to_vertex_num = [None] * len(mesh.loops) #Vertex index in output array for a loop
	index_array = array.array('H')  #Vertex index triplets for mesh triangles
	vertex_co_array = array.array('f') #Vertex coordinates
	vertex_normal_array = array.array('f') #Vertex normals
	uv_array = array.array('f') #Vertex normals
	weight_count_array = array.array('B') # Number of weights in each vertex
	weight_array = array.array('H') # Vertex weights
	group_index_array = array.array('H') # Vertex group indicies
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
				vertex_co_array.extend(vertex.undeformed_co)
				vertex_normal_array.extend(mesh_loop.normal)

				for uv_layer in mesh.uv_layers:
					uv_array.extend(uv_layer.data[loop_index].uv)

				for elem in vertex.groups:
					group_index_array.append(elem.group)
					weight_array.append(int(elem.weight * 256 * 128))
				weight_count_array.append(len(vertex.groups))
			loop_to_vertex_num[loop_index] = vertex_num

	write("\t['%s'] = {\n" % name)
	write("\t\tnum_triangles = %d,\n" % len(mesh.polygons))
	write("\t\tnum_verticies = %d,\n" % vertex_count)
	write("\t\tuv_layers = {")
	for uv_layer in mesh.uv_layers:
		write("%s," % lua_string(uv_layer.name))
	write("},\n");
	write("\t\tnum_vertex_weights = %d,\n" %  len(weight_array))

	for polygon_index, polygon in enumerate(mesh.polygons):
		for loop_index in polygon.loop_indices:
			index_array.append(loop_to_vertex_num[loop_index])

	write("\t\tindex_array_offset = %d,\n" % blob_file.tell())
	index_array.tofile(blob_file)
	write("\t\tvertex_co_array_offset = %d,\n" % blob_file.tell())
	vertex_co_array.tofile(blob_file)
	write("\t\tvertex_normal_array_offset = %d,\n" % blob_file.tell())
	vertex_normal_array.tofile(blob_file)
	write("\t\tuv_array_offset = %d,\n" % blob_file.tell())
	uv_array.tofile(blob_file)
	write("\t\tweight_count_array_offset = %d,\n" % blob_file.tell())
	weight_count_array.tofile(blob_file)
	write("\t\tweight_array_offset = %d,\n" % blob_file.tell())
	weight_array.tofile(blob_file)
	write("\t\tgroup_index_array_offset = %d,\n" % blob_file.tell())
	group_index_array.tofile(blob_file)
	write("\t},\n");
	bpy.data.meshes.remove(mesh)
	return

def write_armature(write, blob_file, armature):
	tail_array = array.array('f')
	transform_array = array.array('f')
	def write_bone(write, blob_file, bone):
		write("\t\t{\n")
		write("\t\t\tname = %s,\n" % lua_string(bone.name))
		if bone.parent:
			write("\t\t\tparent=%s,\n" % lua_string(bone.parent.name))
		flatten_4x4mat(transform_array, bone.matrix_local)
		tail_array.append(bone.tail_local[0])
		tail_array.append(bone.tail_local[1])
		tail_array.append(bone.tail_local[2])
		write("\t\t},\n")
		return

	write("\t[%s] = {\n" % lua_string(armature.name))
	for bone in armature.bones:
		write_bone(write, blob_file, bone)
	write("\t\ttail_array_offset = %d,\n" % blob_file.tell())
	tail_array.tofile(blob_file)
	write("\t\ttransform_array_offset = %d,\n" % blob_file.tell())
	transform_array.tofile(blob_file)
	write("\t}\n")
	return

def flatten_4x4mat(dest, src):
	for i in range(4):
		for j in range(4):
			dest.append(src[i][j])

def write_object(scene, write, blob_file, obj):
	write("\t[%s] = {\n" % lua_string(obj.name))
	if obj.parent:
		write("\t\tparent = %s,\n" % lua_string(obj.parent.name))
		write("\t\tparent_type = %s,\n" % lua_string(obj.parent_type))
		if obj.parent_type == 'BONE':
			write("\t\tparent_bone = %s,\n" % lua_string(obj.parent_type))
		elif obj.parent_type == 'VERTEX':
			write("\t\tparent_vertex = %d,\n" % obj.parent_verticies[0])
		elif obj.parent_type == 'VERTEX_3':
			write("\t\tparent_vertices = {%d,%d,%d},\n" % (obj.parent_verticies[0], obj.parent_verticies[1],obj.parent_verticies[2]))
	write("\t\ttype = %s,\n" % lua_string(obj.type))
	if obj.data:
		write("\t\tdata = %s,\n" % lua_string(obj.data.name))

	if len(obj.vertex_groups) > 0:
		write("\t\tvertex_groups = {\n")
		for group in obj.vertex_groups:
			write("\t\t\t%s,\n" % lua_string(group.name))
		write("\t\t},\n")

	transform_array = array.array('f') #Vertex coordinates
	write("\t\ttransform_array_offset = %d,\n" % blob_file.tell())

	def write_object_frame():
		flatten_4x4mat(transform_array, obj.matrix_local)
		if obj.pose:
			for pbone in obj.pose.bones:
				flatten_4x4mat(transform_array, pbone.matrix)

	if obj.pose is not None:
		write("\t\tbone_names = {\n")
		for pbone in obj.pose.bones:
			write("\t\t\t%s,\n" % lua_string(pbone.bone.name))
		write("\t\t},\n")

	if obj.animation_data is not None:
		write("\t\tanimated = true,\n")
		write_object_frame()

		def write_nla_strip(strip):
			if strip.mute is True:
				return
			write("\t\t\t\t{\n")
			write("\t\t\t\t\tname = %s,\n" % lua_string(strip.name))
			write("\t\t\t\t\taction = %s,\n" % lua_string(strip.action.name))
			write("\t\t\t\t\tframe_start = %d,\n" % strip.frame_start)
			write("\t\t\t\t\tframe_end = %d,\n" % strip.frame_end)
			write("\t\t\t\t\taction_frame_start = %d,\n" % strip.action_frame_start)
			write("\t\t\t\t\taction_frame_end = %d,\n" % strip.action_frame_end)
			write("\t\t\t\t},\n")

		def write_nla_track(track):
			if track.mute is True:
				return
			write("\t\t\t{\n")
			write("\t\t\t\tname = %s,\n" % lua_string(track.name))
			for strip in track.strips:
				write_nla_strip(strip)
			write("\t\t\t},\n")

		write("\t\tnla_tracks = {\n")
		for track in obj.animation_data.nla_tracks:
			write_nla_track(track)
		write("\t\t},\n")
	else:
		write("\t\tanimated = false,\n")
		frame = scene.frame_start
		while frame < scene.frame_end:
			scene.frame_set(frame)
			write_object_frame()
			frame = frame + scene.frame_step
	write("\t},\n")
	transform_array.tofile(blob_file)

def save_brt(operator, context, filepath=""):
	lua_file = open(filepath, "wt")
	blob_file = open(filepath + ".bin", "wb")

	def write_lua(s):
		lua_file.write(s)

	file = open(filepath, "wt")

	#Write blend data as LUA script
	write_lua("return {\n")

	scene = context.scene

	write_lua("scene = {\n")
	write_lua("\tframe_start = %f,\n" % scene.frame_start)
	write_lua("\tframe_end= %f,\n" % scene.frame_end)
	write_lua("\tframe_step = %f,\n" % scene.frame_step)
	for obj in scene.objects:
		write_object(context.scene, write_lua, blob_file, obj)
	write_lua("},\n")

	write_lua("meshes={\n")
	arrays = []
	for mesh in context.blend_data.meshes:
		write_mesh(write_lua, blob_file, mesh.name, mesh)
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
