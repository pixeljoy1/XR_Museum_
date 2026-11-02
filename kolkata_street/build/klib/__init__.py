"""klib - shared Blender build helpers for the Kolkata street project.

Three modules, deliberately small:
  mesh   geometry primitives: lofts, rings, boxes, tubes, revolves, booleans
  mat    a material factory (car paint, chrome, glass, wet asphalt, plaster, ...)
  sceneutil  scene reset, collections, saving, library linking

Everything is in metres. Nothing here knows about trams or taxis; the two model
builds and the street build are the only places that carry subject knowledge.
"""
