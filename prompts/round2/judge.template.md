You are measuring a 3D reconstruction. An AI model watched a video of a real scene and rebuilt it as a 3D scene; its output is in `submission/`. Compute the one number described below from that reconstruction.

You are not grading the reconstruction and you are not estimating the real value. Read the number off the reconstruction the way a ruler reads an object, even if the reconstruction is wrong.

## What to measure

{WHAT_TO_MEASURE}

::: som=yes
`som.png`, in this folder, is a set-of-mark image for this measurement: a picture of the scene with numbered marks on the things the description refers to.
:::

## Start with `submission/manifest.json`

`manifest.json` is the reconstruction model's own index of everything it built. Read it first, before you load the scene or open anything else. It tells you which objects exist, what they are called, how they nest, and where each one's geometry is.

- **Top level:** `scene_file`, `units`, `up_axis` (or an `up` vector), and `video_frame_0_scene_frame`, the scene frame that shows video frame 0.
- **`entities`:** one entry per object or part. Each gives:
  - `id`, `name` and `description`;
  - `parent`, the entity it is a part of, and `relations`, what it is on, in or attached to;
  - `scene_path`, where its geometry is in the scene file;
  - declared properties: `material`, `composition`, `density_kg_m3`, `mass_kg` and others.

The manifest can list thousands of entities, so read it with code rather than opening the file:
1. Print the top-level fields.
2. Print one line per entity: `id`, `name`, `parent` and `description`.
3. Find every entity the measurement above could refer to. Search names and descriptions for its words and their synonyms. Then follow `parent` to the parts nested under each match, and `relations` to what sits on or in it.
4. Note each candidate's `id` and `scene_path`. These are what you bind and measure in the steps below.

Use the manifest to decide what is what, and for declared values: mass, density, material, composition and temperature. Never report its geometric numbers (`bbox_m`, `landmarks`, `joints`, `volume_m3`, lengths, radii). Measure those from the geometry.

## What is in submission/

- **`manifest.json`:** the index described above. Start there.
- **The scene file** named by `manifest.scene_file`: a Blender `.blend`, an OpenUSD stage or a glTF `.glb`.
- **`camera.json`:** intrinsics `K` and `cam_to_world` for every video frame.
  - It uses the OpenCV convention: +z forward, +x right, +y down.
  - Pixel (0, 0) is the top-left corner of the image.
- **`particles/<id>.npz`** (optional): for moving liquids or granular material, `pos` (frames × particles × 3) and `volume_m3`.
- **`render.mp4`, `NOTES.md` and `src/`:** the model's own render, notes and code. Use them to understand what is what, but never take a number from them.

An entity's geometry is its scene object (Blender object, USD prim or glTF node) plus everything nested under it, with modifiers, transforms and animation applied at the frame you measure. Coordinates are world meters.

## How to work

1. **Read the manifest** as described above, and list the candidate entities.
2. **Load.** Load the scene with code: Blender with `blender --background --python`, OpenUSD with `pxr`, glTF with `trimesh`. If it cannot be loaded, or the manifest does not resolve to geometry, report `invalid`.
3. **Pick the frame.**
   - If the description names a frame, use it. Frames count from 0 in the video, and the manifest says which scene frame shows video frame 0.
   - If it names a moment ("at the end", "after the pour"), find that moment in the reconstruction's own timeline and record which frame you used.
   - Otherwise use frame 0, or the static state.
4. **Bind.** Decide which entities and which surface points the words refer to.
   - Start from the candidates you found in the manifest. Choose among them by their names, descriptions, parents and relations, then confirm with the geometry. When text is not enough, render the scene from a few views with each candidate in its own color, and look.
   - If nothing in the manifest matches, look through the scene file for an object the manifest did not index before you report `missing`.
::: som=yes
   - To match the marks in `som.png` to entities, render the reconstruction from a similar viewpoint and compare.
:::
   - "Above", "height", "vertical", "horizontal" and "lying flat" use the manifest's up direction: `up_axis`, or the `up` vector.
   - Directions tied to an object come from that object's geometry: "perpendicular to the desk", "along the cable", "the long side".
5. **Compute.** Write `measure.py` in this folder, the one that holds `submission/`. It loads the submission, computes the value from the bound geometry and prints it in the unit the description asks for. If the description names no unit, use meters, kilograms, milliliters, degrees or pixels, and say which. Run it. The value you report must be exactly what it prints.
6. **Report.** Write `result.json` in this folder, next to `submission/` (format below).

## How common measurements are computed

- **Distance between two points:** a straight line between two points on the surfaces.
- **Size of an object** (length, width, height, thickness, diameter, extent along a direction): the span of its geometry along that direction, from the smallest to the largest projection of its vertices.
  - Height is measured along the up direction.
  - If no direction is given, length, width and thickness are the sides of the object's minimum-volume oriented box, from longest to shortest.
- **Gap or clearance between two things:** the smallest surface-to-surface distance between them. It is 0 if they touch or overlap; mention any overlap in `notes`.
- **Height above a surface:** the distance along the up direction from the point to the named surface, or to the surface directly below the point.
- **Angle:** the angle at the vertex between the two arms, in degrees. For a hinge or joint, use the angle between the parts as the description says, measured from their geometry.
- **Length along something flexible** (cable, strap, cloth edge): the length along its centerline between the stated ends. Use the curve if it is a curve; otherwise extract the centerline from the mesh.
- **Volume:** the enclosed volume of a closed mesh.
  - A liquid or granular material: the volume of its own mesh.
  - A container's capacity: the volume of its interior up to the rim.
  - If the mesh is not closed, close the opening as simply as possible and mark the result `approximate`.
- **Mass or weight:** the sum of `mass_kg` over the entities the description covers, in the unit asked.
  - An entity's mass includes its parts but not its contents: a full bottle is the bottle plus the liquid.
  - If `mass_kg` is missing, use density × the volume of the geometry and mark the result `approximate`.
- **Declared properties** (temperature, material, composition): read the declared value from the manifest.
- **Pixel distance in a frame:** project both 3D points through `camera.json` at that frame and take the distance between them in pixels.
- **Visible pixel area in a frame:** the number of pixels at that frame whose nearest visible surface belongs to the object, so anything else in the scene can block it. Either cast one ray through each pixel center, at the video's resolution through `camera.json`, or render an object-index pass with no anti-aliasing.
- **Focal length:** `fx` of `K` at the frame, in pixels.
- **Anything else** (counts, ratios, fill level, percent, positions over time): compute it from the geometry and declared values exactly as described, combining the rules above.

## Rules

- **Only the submission counts.**
  - Do not open the original video or any file outside this folder.
  - Do not use your own knowledge of typical sizes or weights.
  - You do not know the true value. Do not guess it, and do not adjust toward what seems plausible.
::: som=yes
- **The marked image.** Use `som.png` only to tell which things are meant. Never measure anything on it.
:::
- **Geometry first.**
  - Distances, sizes, gaps, heights, angles, lengths, volumes and pixel measures come from the geometry and the camera.
  - Never take them from numbers written in `manifest.json` (`bbox_m`, `landmarks`, `joints`, `volume_m3`, lengths, radii), in `NOTES.md` or in the code.
  - Declared values count only for what geometry cannot show: mass, density, material, composition and temperature.
- **Your files.** Write everything (`measure.py`, `result.json`, renders, scratch files) in this folder. Never write inside `submission/` or outside this folder.
- **Do not repair the reconstruction.** Measure it as it is: do not move, rescale or remodel anything.
- **Missing things.**
  - If the object the measurement refers to is not in the reconstruction, report `missing` with value null.
::: parts=lenient
  - If the object is there but the named part or point was not modelled separately, find the matching location on the object's geometry and report `approximate`. For example, the end of a tape measure with no hook modelled stands in for the hook tip.
:::
::: parts=strict
  - If the description names a part (a hook, lid, plug, handle) and the object was not modelled with that part as its own entity, report `missing` with value null. Points that are features of an object's shape (a corner, an edge, the top face) are located on its geometry as usual.
:::
  - Never substitute a different object.
- **Ambiguity.** If the words could match more than one entity or point, choose the most plausible one, report `ambiguous`, explain your choice in `notes`, and still give the value.

## Output

`result.json`, in this folder:
```json
{
  "value": 41.7,
  "unit": "cm",
  "status": "ok",
  "frame": 0,
  "entities": ["tape_measure", "battery_pack"],
  "points_m": {"A": [0.181, -0.052, 0.763], "B": [0.534, 0.102, 0.766]},
  "method": "what you bound and how you computed it, in one or two sentences",
  "notes": ""
}
```

- **`unit`:** the unit of `value`.
- **`entities`:** the manifest `id` of every entity you measured or summed.
- **`status`:** one of
  - `ok`;
::: parts=lenient
  - `approximate`: a part or point was located on coarser geometry;
:::
::: parts=strict
  - `approximate`: a volume or mass needed a fallback (an unclosed mesh, a missing `mass_kg`);
:::
  - `ambiguous`;
  - `missing`: value null;
  - `invalid`: the submission cannot be loaded.

End your final message with one line, `VALUE: <number> <unit>`, or `VALUE: null`.
