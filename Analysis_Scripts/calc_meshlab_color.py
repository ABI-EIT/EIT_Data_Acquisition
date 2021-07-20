import struct
"""
abi pyeit provides a method for reading meshes in .ply format and interpreting the r,g,b,a color fields as bytes of a
32 bit float representing permitivity/conductivity.

This script calculates the color fields required to represent a given float. These can then be set on the mesh in meshlab
"""

perm_float = 100.0

perm_bytes = struct.pack(">f", perm_float)

print(f"For a perm float value of: {perm_float}, set the following color values:\n"
      f" Red: {perm_bytes[0]}\n Green: {perm_bytes[1]}\n Blue: {perm_bytes[2]}\n Alpha: {perm_bytes[3]}")
