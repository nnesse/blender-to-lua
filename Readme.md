Blender to Lua
==============

The blender to lua exporter generates a pair of files, a LUA fragment with the extension '.b2l'
and a binary file with the extension '.b2l.bin'.  The LUA file describes the blend's scene
graph along with meta data neccisary to intepret the binary file. The binary file stores arrays
of numerical data such as vertex data, object, and bone transforms. The byte offsets of these
arrays are stored in the LUA tables for easy location. This allows the output to be efficiently
processed from C/C++ code as well as eliminates rounding errors inherent to binary conversions.

The exact format of the files is described in a comment section at the top of the export script.
In most cases fields exported in the LUA data have a 1-1 mapping to the representation
in the Blender Python API. Field's that are either not well documented or poorly suited for
real-time rendering are ommitted.


Material data
-------------

Since material data is generally not very portable across different renderers the B2L format omits
material details and only stores the material names and which submeshes they apply to. To render
your models you will need to reconstruct the material data in a form suitable for your renderer.

Animation
---------

For now function curves and action data is not directly stored in the B2L files. Instead bone and
object transforms are stored for every frame for objects that are animated. Basic NLA track and
strip data are stored to make it easy for external tools to assocated animation frames with specific
actions.
