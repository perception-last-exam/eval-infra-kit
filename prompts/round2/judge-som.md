You are measuring a 3D reconstruction. An AI model watched a video of a real scene and rebuilt it as a 3D scene; its output is in `submission/`. Compute the one number described below from that reconstruction.

You are not grading the reconstruction and you are not estimating the real value. Read the number off the reconstruction the way a ruler reads an object, even if the reconstruction is wrong.

## What to measure

{WHAT_TO_MEASURE}

`som.png`, in this folder, is a set-of-mark image for this measurement: a picture of the scene with numbered marks on the things the description refers to.

## What is in submission/

- **`manifest.json`** indexes every object and part. For each entity it gives:
  - `id`, `name`, `description`, `parent` and `relations`;
  - `scene_path`, where its geometry is in the scene file;
  - material, density, mass and other declared properties.

  It also gives the up direction, the units, and how scene frames map to video frames.
- **The scene file** named by `manifest.scene_file`: a Blender `.blend`, an OpenUSD stage or a glTF `.glb`.
- **`camera.json`:** intrinsics `K` and `cam_to_world` for every video frame.
  - It uses the OpenCV convention: +z forward, +x right, +y down.
  - Pixel (0, 0) is the top-left corner of the image.
- **`particles/<id>.npz`** (optional): for moving liquids or granular material, `pos` (frames × particles × 3) and `volume_m3`.
- **`render.mp4`, `NOTES.md` and `src/`:** the model's own render, notes and code. Use them to understand what is what, but never take a number from them.

An entity's geometry is its scene object (Blender object, USD prim or glTF node) plus everything nested under it, with modifiers, transforms and animation applied at the frame you measure. Coordinates are world meters.

## How to work

1. **Load.** Load the scene with code: Blender with `blender --background --python`, OpenUSD with `pxr`, glTF with `trimesh`. If it cannot be loaded, or the manifest does not resolve to geometry, report `invalid`.
2. **Pick the frame.**
   - If the description names a frame, use it. Frames count from 0 in the video, and the manifest says which scene frame shows video frame 0.
   - If it names a moment ("at the end", "after the pour"), find that moment in the reconstruction's own timeline and record which frame you used.
   - Otherwise use frame 0, or the static state.
3. **Bind.** Decide which entities and which surface points the words refer to.
   - Use the manifest's names, descriptions and relations, and the geometry itself. When text is not enough, render the scene from a few views with each entity in its own color, and look.
   - To match the marks in `som.png` to entities, render the reconstruction from a similar viewpoint and compare.
   - "Above", "height", "vertical", "horizontal" and "lying flat" use the manifest's up direction: `up_axis`, or the `up` vector.
   - Directions tied to an object come from that object's geometry: "perpendicular to the desk", "along the cable", "the long side".
4. **Compute.** Write `measure.py`. It loads the submission, computes the value from the bound geometry and prints it in the unit the description asks for. If the description names no unit, use meters, kilograms, milliliters, degrees or pixels, and say which. Run it. The value you report must be exactly what it prints.
5. **Report.** Write `result.json` (format below).

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
- **The marked image.** Use `som.png` only to tell which things are meant. Never measure anything on it.
- **Geometry first.**
  - Distances, sizes, gaps, heights, angles, lengths, volumes and pixel measures come from the geometry and the camera.
  - Never take them from numbers written in `manifest.json` (`bbox_m`, `landmarks`, `joints`), in `NOTES.md` or in the code.
  - Declared values count only for what geometry cannot show: mass, density, material, composition and temperature.
- **Do not repair the reconstruction.** Measure it as it is: do not move, rescale or remodel anything.
- **Missing things.**
  - If the object the measurement refers to is not in the reconstruction, report `missing` with value null.
  - If the object is there but the named part or point was not modelled separately, find the matching location on the object's geometry and report `approximate`. For example, the end of a tape measure with no hook modelled stands in for the hook tip.
  - Never substitute a different object.
- **Ambiguity.** If the words could match more than one entity or point, choose the most plausible one, report `ambiguous`, explain your choice in `notes`, and still give the value.

## Output

`result.json`:
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
- **`status`:** one of
  - `ok`;
  - `approximate`: a part or point was located on coarser geometry;
  - `ambiguous`;
  - `missing`: value null;
  - `invalid`: the submission cannot be loaded.

End your final message with one line, `VALUE: <number> <unit>`, or `VALUE: null`.
