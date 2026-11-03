# Kolkata tram — V3 geometry model

## Latest revision: V3.6 flush glazing and rain shutters

Continue from `Kolkata_Tram_V3_6_Glazed_Windows.blend`. The proud passenger-window surrounds have been replaced on both carriages with thin black rubber gaskets seated into the body surface. Upper openings have pill-like rounded corners and fixed clear glazing; main openings have rounded top corners. The opening and seal meshes conform across the rear body fold.

Each of 34 passenger window bays has an interior sliding rain-glass panel, lower sash and guide tracks. In collection `13 Windows | rain shutter controls`, select a control and change its custom `closure` property: 0 raised, 1 closed. The saved presentation uses 0.15. This is a digital sliding assembly, not a validated functional mechanism for a 1:87 print.

Review `20_flush_glazed_windows.png`, `21_glazed_overview.png` and `22_rain_shutters_closed.png`. Material glazing should be excluded from opaque resin shell exports and fabricated separately if clear windows are desired. Earlier fabrication limitations still apply.

## Latest revision: V3.5 flush transition windows

Continue from `Kolkata_Tram_V3_5_Flush_Windows.blend`. The upper and lower surrounds on the trailer's second-last left window now bend at the body fold and follow the rear taper. The equivalent fold-crossing frames on the opposite side were corrected as well. Existing through-openings and already-conforming sash bars were retained. Close-up `18_flush_transition_window.png` was visually checked; `19_corrected_overview.png` shows the full model. Dull aluminium roof equipment and blue-white materials are retained.

## Latest revision: V3.4 dull aluminium roof equipment

Continue from `Kolkata_Tram_V3_4_Aluminium_Roof.blend`. The trolley pole, roof electrical mountings, resistance enclosure, louvres and associated fittings now use dull aluminium materials. Louvre recesses use darker aluminium rather than black. This is a material-only revision affecting 41 objects. Review `16_aluminium_overview.png` and `17_aluminium_cab.png`.

## Latest revision: V3.3 blue-and-white livery

`Kolkata_Tram_V3_3_Blue_White.blend` is the current coloured model. Mesh vertex/face counts were verified unchanged from V3.2. Materials use the modern palette from the supplied texture package: sky-blue lower panels, off-white upper panels, navy header, ochre roof rim and grey roof. Body bands are procedural and adapted to this model's heights; the package's drawn window/grille outlines were not overlaid on existing geometry. The supplied roof colour and normal maps are UV-mapped and packed into the blend file. Earlier geometry-only files remain available.

Review `13_modern_overview.png`, `14_modern_cab.png`, and `15_modern_opposite.png`. `livery_audit.json` records material sources and the geometry-preservation check. No fleet numbers, advertising, or operator lettering were added.

## Latest revision: V3.2 fascia and sharp edges

Continue from `Kolkata_Tram_V3_2_Fascia.blend`. The deeper rear taper is now 1.15 prototype metres (13.22 mm at 1:87), increased from 0.72 m at the user's request. The rear centre half-width is 0.90 m. The motor nose retains its prior overall proportions.

Body folds and main window openings/frames now use crisp corners with only small edge relief. The resistance enclosure is a folded trapezoidal box. The driver's rectangular entrance is 0.54 × 2.02 prototype metres, centred 1.075 m behind the front face; these are reference-based modelling choices, not independently dimensioned measurements. Its placement was adjusted to separate its jamb from the first passenger window frame.

The three front grille panels are perforated geometry aligned with their respective nose facets. Headlamps now have shallow rectangular housings, circular bezels, recessed lens discs and fixing details. Upper marker lamps align with the angled nose facets. Destination and roof-route lamp faces have distinct surrounds/insets. Circular and gently relieved edges remain on the lamps, mirrors and barrel roof where appropriate.

Review images 09–12 show this revision. `fascia_audit.json` records its topology check. Older images and blend files are checkpoints, not the current design. Print fit, optical details and reference accuracy remain subject to the limitations below.

## Latest revision: V3.1 end profiles

`Kolkata_Tram_V3_1_End_Profiles.blend` supersedes the original geometry file for continued work. The original remains a checkpoint.

The broad flat end treatment was replaced with distinct plan-derived shapes: a long motor-cab taper (approximately 1.55 prototype metres) and shorter trailer-tail taper (approximately 0.72 metres), with small softened joins. Width remains 2.90 metres. Taper depths were estimated proportionally from the supplied V2 plan; they are not explicit labelled dimensions. Roofs, floor edges, bumpers and front cheek windows now follow those profiles. The front screen uses a wire lattice consistent with the newly supplied photograph. The rear corner opening was cleaned to remove duplicate overlapping geometry.

Review `05_corrected_overview.png`, `06_corrected_plan.png`, `07_motor_nose.png`, and `08_trailer_tail.png`. Images 01–04 show the earlier revision and are retained only for comparison. `end_profile_audit.json` records the revised topology check and dimensional assumptions. This revision does not resolve the existing fabrication limitations listed below.

Saved model: `Kolkata_Tram_V3_Geometry.blend`. Built in the user's live Blender from the supplied V2 material only. Prior files were not edited.

## Scale and dimensional interpretation

The model uses millimetres at 1:87. The construction script uses provisional prototype metres and converts to model dimensions. This is an interpretation of contradictory drawings, not a measured historical reconstruction.

| Parameter | Prototype interpretation | Model |
|---|---:|---:|
| Length across nominal bumper faces | approximately 15.59 m | approximately 179.2 mm |
| Shell width | 2.90 m | 33.33 mm |
| Motor shell length | 7.85 m | 90.23 mm |
| Trailer shell length | 7.08 m | 81.38 mm |
| Gap between body shells | 0.42 m | 4.83 mm |
| Roof crown | 3.205 m | 36.84 mm above wheel contact |
| Resistance box top, approximately | 3.535 m | 40.63 mm |
| Display base | — | 202.30 × 51.15 × 3.91 mm |

Roof equipment, fenders and the raised trolley pole extend outside the nominal body envelope. The 3,300 mm height was not enforced on equipment because its reference endpoints are ambiguous. The drawing's 3,300 mm front width and bogie-span annotations were treated as suspect; 2,900 mm plan width and 15,590 mm overall length were the principal anchors. The guide's 16.8 m length, equal car lengths and 2.2 m width were not used.

## Included geometry

- Asymmetric side layouts: motor entrance side 5 + doorway + 2; trailer 2 + doorway + 5 regular aft bays + separate corner bay.
- Opposite side: nine regular motor bays plus cab window; ten regular trailer bays.
- Actual openings, rounded frames, sliding sash rails, safety bars, panel joints and selected fasteners.
- Curved hollow roofs, end fascia, resistance housing, trolley pole and fittings.
- Circular perforations in the front screen, central viewing opening, lamps, grab rails and safety fenders.
- Motor 1+2 transverse seats, driver controls and partition; trailer longitudinal benches.
- Separate floor and roof assemblies with preliminary locating features.
- Three bogies, six separate axle assemblies and twelve wheels, with axle bores and bearings.
- Separate display plinth with preliminary hidden restraint provision.

Collection `12 Assembly controls` provides roots for moving each roof and rotating each axle assembly about local Y. These are editing conveniences, not a physical simulation.

## Validation and remaining work

Four rendered views were visually inspected: overview, each side and roof-off interior. A failed trailer Boolean and a wheel parenting offset were found and corrected. The final audit reports no empty meshes and no non-manifold edges across 742 mesh components. Axle centres were checked after parenting.

This does **not** prove printable wall thickness, reliable wheel retention, collision-free assembly, or absolute dimensional accuracy. Fine features, screen thickness, pin fits and axle tolerances require adaptation to the chosen manufacturing process. Many decorative solids intersect their supporting parts and must be united within each intended printed component before export. The model has not been exported as a production STL.

Undocumented depths, cab equipment, concealed hardware, roof curvature and undercarriage details involve interpretation. Corner windows and the detailed undercarriage are not fully traced surface-for-surface from V2. These remain accuracy-review items; the model should not be described as a perfect replica.

## Files

- `01_overview.png`: assembled geometry.
- `02_entrance_side.png`, `03_opposite_side.png`: orthographic side review.
- `04_interior.png`: roofs hidden for inspection.
- `geometry_audit.json`: component topology and dimensional checks.
- `build_tram.py`: initial procedural construction, with the Boolean method corrected for future use.
- `refine_details.py`: additional fascia, perforated grille and assembly controls. Run after a fresh build, once only.
- `repair_and_audit.py`, `finalize_model.py`: repair history for the delivered file; do not run again on the final file.
- `blender_bridge.py`: local MCP command sender; only executes a supplied Python file in Blender.

The delivered `.blend` is authoritative. Build/refinement scripts preserve the construction history; they are not a packaged one-click manufacturing pipeline.

## V3.7 — white wire mesh, shutters and lit route holders

Latest: `Kolkata_Tram_V3_7_Mesh_And_Lighting.blend`.
Three cab screens now use individual thin white lattice wires instead of perforated plates. Passenger safety bars and driver-right guards are white. All 34 rain shutters are opaque white, retaining the `closure` controls. All 34 upper windows have smaller pill-shaped apertures, black seals and smoked-grey glazing; the body openings were rebuilt to match.

The route-board holders have separate recessed blank cards, protective glass and internal lighting. The top-centre headlight has a housing, seal, aluminium bezel and recessed lens. Select `Night lighting | enable control`, then set its custom `enabled` property from 0 (day, saved default) to 1 (illuminated). Route lettering remains unassigned. Roof equipment retains dull aluminium.

Renders: `23_wire_mesh_cab.png`, `24_white_shutters_grey_glazing.png`, `25_illuminated_route_holder.png`, `26_white_right_side_guards.png`. Geometry audit reports no empty or non-manifold meshes. Fine wire diameters remain appearance-led and need manufacturing adaptation before printing at 1:87.

## V3.8 — clean connection and manual retrieval rope

Latest: `Kolkata_Tram_V3_8_Clean_Rear_And_Rope.blend`.
Removed the two raised orange connection-end fascias; plain grey inset closures finish the exposed roof ends. Recessed overlapping lower roof/closure surfaces to remove corner flicker. The rear-facing centre window and its actual wall opening are 15% narrower, with unchanged height. Added a thicker black manual trolley-pole pull rope terminating at a central black retaining reel with wound rope. Reel dimensions are a visual approximation pending a close reference. This is a manual retrieval component, not an electrical cable. Roof electrical equipment remains dull aluminium.

Review renders: `27_clean_rear_manual_rope.png` and `28_clean_connection.png`. Prior blend revisions are preserved.

## V3.9 — passenger footwells and supplied route plate

Latest: `Kolkata_Tram_V3_9_Entrances_And_Route_Board.blend`.
Both passenger doorways have two grooved timber treads, closed timber risers, a timber standing landing, a thick white centre grab pillar, and two transverse guard panels with glazed windows. Geometry follows the supplied reference qualitatively; tread and guard dimensions remain inferred.

A separate hanging Route 25 plate sits outside the driver's chamfered cab panel. Its UVs sample the exact supplied Gariahat–Esplanade board photograph; the unaltered source image is packed into the blend and copied to `textures/route25_supplied_photo.png`. Original source resolution limits text sharpness. Existing roof destination holder remains separate.

Review: `29_two_step_entrance.png`, `30_hanging_route25_board.png`.

## V3.10 — rounded signature roof heads

Latest: `Kolkata_Tram_V3_10_Rounded_Signature_Heads.blend`.
Rebuilt both roof skins with dense curved end sections and a 0.38 m prototype-length rounded longitudinal transition. The driver-end box-shaped lamp pedestal is united with the gold head closure and roof mesh; its lens is recessed. Front and rear destination holders now sit in actual rounded header recesses with thin black seals and separate glass/card layers. Existing light-control material drivers are retained. Lower sheet-metal chamfers, entrance fittings, hanging Route 25 board and manual retrieval rope remain.

Preview renders: `31_rounded_driver_head.png`, `32_rounded_trailer_head.png`, `33_head_side_profile.png`. Mesh audit reports no non-manifold edges. Curvature radii are inferred from the supplied photograph, not dimensioned measurements.
