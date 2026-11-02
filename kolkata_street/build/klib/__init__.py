"""klib - shared Blender build helpers for the Kolkata street project.

Four modules, deliberately small:
  mesh   geometry primitives: lofts, rings, boxes, tubes, revolves, booleans, wires
  mat    a material factory (car paint, chrome, glass, wet asphalt, plaster, ...)
  cam    named shots and a dolly rig
  sceneutil  scene reset, collections, saving, library linking

Everything is in metres. Nothing here knows about trams or taxis; the two model
builds and the street build are the only places that carry subject knowledge.
"""
