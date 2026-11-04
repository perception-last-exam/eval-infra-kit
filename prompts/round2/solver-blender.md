Based on the video `input.mp4` in this folder, recreate {RECONSTRUCTION_BOUND} as a 3D scene in Blender. Model every object individually and place it in exactly the right location.

## Goal

Make the highest-quality, most fine-grained reconstruction you can. Reconstruct every object meticulously, true to its real shape, color, pattern, texture, transparency, reflectivity, size, material, composition, volume, mass, density, temperature, orientation, the opening of hinged parts, the bending of flexible things, and position relative to everything else, including how any of these change during the video. Metric accuracy comes first.

After you finish, hidden questions about this scene will be answered by measuring your reconstruction. They can be about any object or part within the bound. Anything missing from your reconstruction cannot be measured and counts as wrong.

## What to reconstruct

- **Objects.** Every object within the bound is its own object, never merged with another. Anything that is not bound or fixed to something else is a separate object. Things outside the bound are optional.
- **Parts.** Wherever the video shows them, model an object's parts as separate children of that object: lids, caps, handles, buttons, hooks, plugs, legs, drawers, doors, wheels. Small and thin things count.
- **Geometry.** Real 3D geometry at true scale. Solid things are closed (watertight) meshes. Containers have their real wall thickness and an open interior, so their capacity can be measured. Billboards, image planes, point clouds and Gaussian splats are not accepted as final geometry.
- **Placement.** Objects resting on something touch it, nothing floats or passes through anything else, and real gaps stay open.
- **Flexible things** (cables, cords, cloth, bags, paper). Model the shape they actually have, with their real length and thickness. Keep each cable, cord or strap as a curve along its centerline with a thickness, so its length can be read.
- **Liquids and granular materials** (water, coffee, oil, sand, rice, sugar). Each body is its own closed mesh that fills exactly the space it occupies: a liquid follows its container's inner wall up to its surface level. Small things you can count (drops, beads, pills, screws, grains) are modelled one by one. If a liquid or granular material moves during the video, also export it as particles that follow the material over time (format below).
- **Physical properties.** For every object and part, record its material, density and mass; for anything noticeably hotter or colder than the room, its temperature; for mixtures (drinks, food, alloys, fabric blends), its composition.
- **Joints.** For anything hinged, sliding or articulated, robots included, model the moving parts separately and record each joint: its type, axis, pivot and current value.
- **Camera.** Recover the camera's intrinsics and its pose at every frame of the video.
- **Motion.** If anything moves or changes shape during the video, animate it so that the scene matches the video at every frame.
- **Appearance.** Match each object's color, pattern, texture, transparency and reflectivity.

## Coordinate system

Choose whatever origin and horizontal orientation you find helpful. +Z must point straight up, against gravity. Use meters: 1 Blender unit = 1 m, unit scale 1.0. In the manifest, say what you put at the origin.

## Output

Write everything to `output/`:

```
output/
  scene.blend      the reconstruction
  manifest.json    every object and part, with physical properties
  camera.json      the camera at every video frame
  render.mp4       the scene rendered through that camera
  particles/       only for liquids or granular material that move
  src/             all the code you wrote; src/build.sh rebuilds output/ from scratch
  NOTES.md         what you did, your assumptions, and what you are least sure of
```

Keep intermediate files in `work/`, not in `output/`.

### scene.blend
- **Version.** Blender 4.2 or newer; record the version in the manifest.
- **Objects and parts.** Each object and part is a separate Blender object with a unique name. A part is parented to its object. Separate objects are never parented to each other, not even a liquid to its bottle; use `relations` in the manifest instead.
- **What counts as geometry.** An entity's geometry is its Blender object plus everything parented under it, evaluated with modifiers and animation applied. Displacement done in shaders does not count as geometry.
- **Timeline.** Blender frame 1 is video frame 0. Set the frame range to 1 … N (N = the video's frame count) and the frame rate to the video's.
- **Camera.** One camera, named `Camera`, matching `camera.json` at every frame.
- **Files.** Pack textures into the file (`bpy.ops.file.pack_all()`). Keep any baked cache (fluid, cloth, Alembic) inside `output/` with relative paths.

### manifest.json
```json
{
  "format": "r2s-manifest/1",
  "scene_file": "scene.blend",
  "software": ["Blender 4.5.3"],
  "units": "m",
  "up_axis": "+Z",
  "origin": "what is at (0, 0, 0), in words",
  "video_frame_0_scene_frame": 1,
  "n_frames": 887,
  "fps": 30,
  "room_temperature_c": 22,
  "entities": [
    {
      "id": "tape_measure",
      "name": "pink tape measure",
      "description": "pink retractable tape measure lying flat at the front left of the desk, hook pointing right",
      "parent": null,
      "scene_path": "tape_measure",
      "type": "rigid",
      "material": "pink ABS plastic case, steel tape and hook",
      "density_kg_m3": 1300,
      "mass_kg": 0.115,
      "bbox_m": {"min": [0.112, -0.083, 0.751], "max": [0.181, -0.020, 0.788]},
      "relations": [{"type": "on", "target": "desk_top"}]
    }
  ]
}
```
The values in the example are illustrative.

Every object and every part gets an entry, and every mesh in the scene belongs to exactly one entity.

Required for every entity:
- `id` (unique; lowercase letters, digits and underscores) and `name`.
- `description`: enough to tell this entity apart from every other one, such as its color, position and distinctive features.
- `parent`: the `id` of the object this is a part of, or `null` for a separate object.
- `scene_path`: the Blender object name.
- `type`: `rigid`, `articulated`, `deformable`, `cable`, `cloth`, `liquid`, `granular`, `robot`, or your own word.
- `material`.
- `mass_kg`: this entity together with its parts, without whatever it holds. A full bottle is the bottle entity plus the liquid entity.
- `density_kg_m3`: the density of its main material.
- `bbox_m`: the world-axis-aligned box of its geometry at video frame 0, computed from the geometry by code.

Add these when they apply:
- `temperature_c`.
- `composition`: mass fractions, e.g. `{"water": 0.9, "sugar": 0.1}`.
- `relations`: a list of `{type, target}`, where `type` is `on`, `inside`, `attached_to`, `plugged_into`, `touching`, `holding` or your own word.
- `joints`: a list of `{name, type, child, axis, pivot, value, values}`:
  - `type` is `revolute`, `prismatic` or `other`;
  - `child` is the part that moves;
  - `axis` and `pivot` are in world coordinates at frame 0;
  - `value` is in degrees or meters at frame 0;
  - `values` gives one value per video frame; add it if the joint moves.
- `particles`: the path of its particle file.
- `landmarks`: named points on its surface at frame 0, e.g. `{"hook_tip": [x, y, z]}`.
- `notes`.

### camera.json
```json
{
  "width": 1080,
  "height": 1920,
  "frames": [
    {"K": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
     "cam_to_world": [[r11, r12, r13, tx], [r21, r22, r23, ty], [r31, r32, r33, tz], [0, 0, 0, 1]]}
  ]
}
```
- **Frames.** One entry per video frame, in order, so entry i is video frame i.
- **Axes.** OpenCV convention: the camera looks along its +z, with +x right and +y down in the image.
- **Pixels.** Pixel (0, 0) is the top-left corner of the image, and the first pixel's center is at (0.5, 0.5).
- **Pose.** `cam_to_world` maps camera coordinates to world coordinates, in meters. Blender cameras look along their local −Z with +Y up, so convert.
- **Optional.** `"distortion": {"model": "opencv", "k1": ..., "k2": ..., "p1": ..., "p2": ..., "k3": ...}`.

### render.mp4
- **Source.** An H.264 MP4 rendered from the scene through `camera.json`, with Blender.
- **Match the input.** Same frame count, frame rate and resolution as `input.mp4`; check both with `ffprobe -count_frames`.
- **Engine.** Any render engine and quality.

### particles/<id>.npz
For each liquid or granular material that moves:
- `pos`: float32 array, shape (N_frames, N_particles, 3), in world meters, NaN where a particle does not exist at that frame. Column j is the same bit of material at every frame.
- `volume_m3`: float32 array, shape (N_particles,), the volume of material each particle stands for.

The material's closed mesh in the scene must still match it at every frame.

## Software

Use whatever helps, and install what is missing, preferably into a virtual environment rather than the system. Useful options:
- **3D and rendering:** Blender (`bpy`, `bmesh`, `mathutils`; headless: `blender --background --python script.py`); OpenUSD (`usd-core`: `pxr.Usd`, `UsdGeom`, `UsdPhysics`, `UsdShade`; `usdcat`, `usdchecker`, `usdrecord`); trimesh, Open3D, PyMeshLab, manifold3d, PyVista, Polyscope, Mitsuba 3, pyrender.
- **Video and images:** FFmpeg, FFprobe, ImageMagick, OpenCV, Pillow, imageio, PyAV.
- **Numerics and simulation:** NumPy, SciPy, PyTorch, scikit-image, Taichi, NVIDIA Warp, Genesis, MuJoCo, PyBullet, Blender physics (rigid body, cloth, Mantaflow fluids).
- **Vision:** COLMAP, GLOMAP, pycolmap, hloc, OpenMVS; VGGT, MASt3R, DUSt3R; Depth Anything, MoGe, UniDepth; SAM 2, Grounding DINO; CoTracker, RAFT; nerfstudio, gsplat.

## Rules

- **One source of information.** `input.mp4` is your only source of information about this scene. Work inside this folder, and do not read files elsewhere on this machine except installed software and its documentation.
- **Internet.** Use it only to install software and read documentation. Never look up the objects in this scene, their products or their specifications.
- **Work alone.** Nobody will answer questions, so make reasonable assumptions, write them in NOTES.md, and keep going until you are done.
- **Before finishing:**
  - compare renders of your scene against video frames from across the whole video, and fix what disagrees;
  - reopen the scene file in a fresh process and confirm that every manifest entity resolves to its geometry and that its `bbox_m` matches;
  - confirm that `camera.json` has one entry per video frame;
  - confirm that `render.mp4` matches `input.mp4` in frame count, frame rate and resolution.
