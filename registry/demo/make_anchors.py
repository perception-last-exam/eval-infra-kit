#!/usr/bin/env python3
"""Write the three difficulty-anchor example scenes (Yu Zhou) as scene.json files.
GT values and model runs are illustrative (demo: true), like the other demo records."""
import json
import os
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("R2S_EXAMPLES", KIT.parent / "registry-demo" / "_examples")) / "yuzhou"
RUNNERS = [("gpt-6.1-sol", "codex", 1), ("gpt-6.1-sol", "codex", 2),
           ("claude-opus-5-5", "claude-code", 1), ("claude-opus-5-5", "claude-code", 2)]


def q(scene, n, domain, kind, what, definition, gt, unit, unc, how, challenges, link, why, preds,
      point_a="", point_b="", point_c="", obj="", moment="", frame=None):
    assert unc <= 0.025 * abs(gt) + 1e-9, (scene, n, "uncertainty above 2.5%")
    assert all(abs(p - gt) / abs(gt) > 0.10 for p in preds), (scene, n, "an illustrative run is within 10%")
    qid = f"{scene}-q{n}"
    return {
        "query_id": qid, "metric_domain": domain, "kind": kind,
        "point_a": point_a, "point_b": point_b, "point_c": point_c, "object": obj,
        "definition": definition, "what_to_measure": what, "moment": moment, "frame_index": frame,
        "gt_value": gt, "gt_unit": unit, "gt_uncertainty": unc, "how_measured": how, "evidence": [],
        "challenges": challenges, "robotics_link": link, "why_hard": why, "pilot": [],
        "results": [{"model": m, "harness": h, "effort": "max", "attempt": a, "prompt_version": "example",
                     "predicted": p, "run_id": f"example-{qid}-{i}"} for i, ((m, h, a), p) in enumerate(zip(RUNNERS, preds))],
    }


def scene(sid, env, summary, scope, dynamic, video, n_frames, duration, queries):
    return {
        "schema": "r2s-scene/0.1", "demo": True, "difficulty_anchor": True, "scene_id": sid, "collector": "Yu Zhou",
        "status": "tested", "environment": env, "summary": summary, "scope": scope, "dynamic": dynamic,
        "input_video": f"input/{video}", "device": "iPhone 16 Pro Max", "resolution": [1080, 1920], "fps": 30,
        "duration_s": duration, "n_frames": n_frames, "calibration_video": None, "evidence_dir": "evidence/",
        "notes": "Difficulty anchor for Round 2: a deliberately hard scene other collectors can compare theirs against. "
                 "Ground-truth values and model runs are illustrative (example data).",
        "queries": queries,
    }


S2 = "demo-yuzhou-s02"
s2 = scene(S2, "home",
    "A standing desk crowded with produce, supplement jars, chocolate bars, a tangled pink soft tape measure, wipes and a water bottle; halfway through, the phone turns sideways.",
    "the desk top and every object on it, including the monitor, the laptop on its stand and the keyboard", False,
    "IMG_1580.MOV", 1073, 35.767, [
    q(S2, 1, "object_weight", "mass",
      "The total mass in grams of the bunch of yellow bananas lying next to the black water bottle.",
      "total mass of the banana bunch", 486, "g", 1, "kitchen scale (0.1 g), bunch weighed whole after filming",
      ["irregular_shape", "clutter_stacking", "frame_format"],
      "grip force for lifting a bunch of fruit without dropping or bruising it",
      "produce has no catalog weight; the bunch is seen mostly from above and while the phone is sideways",
      [612, 395, 560, 701], obj="bunch of yellow bananas"),
    q(S2, 2, "rigid_distance", "extent",
      "The length in cm of the green papaya along its long axis, from the stem end to the blossom end.",
      "length of the papaya along its long axis", 23.4, "cm", 0.2, "caliper jaws on both ends, 3 readings 23.3 / 23.4 / 23.4 cm",
      ["irregular_shape", "occlusion", "clutter_stacking"],
      "gripper opening and approach for an irregular fruit",
      "no straight edges, partly hidden behind the tissue box, and nothing of known size next to it",
      [18.9, 28.1, 19.6, 30.2], obj="green papaya"),
    q(S2, 3, "deformable_distance", "distance",
      "The straight-line distance in cm between the two metal end tabs of the pink soft tape measure, as it lies tangled on the desk.",
      "straight-line distance between the two ends of the tangled tape as placed", 38.6, "cm", 0.3,
      "steel ruler between the two end tabs before touching the tape",
      ["deformable", "small_or_thin", "clutter_stacking", "occlusion"],
      "finding both ends before untangling a cable or strap",
      "the ends are a few millimetres wide and buried in loops of the same pink tape",
      [52.0, 27.4, 47.9, 22.8], point_a="metal end tab at the start of the pink soft tape measure",
      point_b="metal end tab at the other end of the same tape"),
    q(S2, 4, "rigid_distance", "gap",
      "The vertical clearance in cm between the desk surface and the lowest point of the laptop's front edge on its stand.",
      "clearance under the front edge of the laptop", 11.8, "cm", 0.1, "steel ruler standing on the desk, read at the laptop edge",
      ["physical_gap", "fit_affordance", "occlusion"],
      "whether an object can be slid under the laptop without lifting it",
      "the stand's thin arms and the dark gap under the laptop are hard to see against the white desk",
      [8.9, 15.4, 9.7, 14.6], point_a="desk surface under the laptop's front edge", point_b="lowest point of the laptop's front edge"),
    q(S2, 5, "liquid_volume", "volume",
      "The capacity in mL of the white mug with the cartoon print, filled to the brim.",
      "capacity of the white mug, filled to the brim", 350, "mL", 3, "filled with water to the brim, poured into a measuring cylinder",
      ["fit_affordance", "occlusion", "reflection_mirror"],
      "pouring a drink without overflowing",
      "the inside of the mug is visible for only a few frames and its wall thickness is unknown",
      [270, 455, 300, 420], obj="white mug with a cartoon print"),
    q(S2, 6, "image_frame", "px_distance",
      "In frame 570 of the video (frames count from 0), the pixel distance between the top of the red apple's stem and the top-left corner of the Clorox canister's lid.",
      "pixel distance between A and B in frame 570", 1288, "px", 3, "two clicks on frame 570, checked at 200% zoom",
      ["frame_format", "fast_or_shaky_camera"],
      "projecting a grasp target into the image after the camera rotates",
      "the phone is sideways at this frame, so camera pose and intrinsics must survive the rotation",
      [1496, 1075, 1462, 1131], point_a="top of the red apple's stem", point_b="top-left corner of the Clorox canister's lid", frame=570),
])

S3 = "demo-yuzhou-s03"
s3 = scene(S3, "kitchen",
    "A French-door fridge opened by hand: door bins with sauces, a lemon and an orange carton; shelves of bagged vegetables, meat and kiwis; the freezer drawer is pulled out near the end and everything is closed again.",
    "the refrigerator, both French doors, the freezer drawer and everything inside them", True,
    "IMG_1583.MOV", 1629, 54.31, [
    q(S3, 1, "temperature", "declared",
      "The air temperature in °C at the center of the middle shelf of the fresh-food compartment, 15 minutes after the doors were closed.",
      "air temperature at the center of the middle shelf, doors closed", 3.6, "degC", 0.05,
      "calibrated probe thermometer left on the middle shelf, read after 15 minutes with the doors closed",
      ["imagined_state", "visual_illusion", "dynamic_scene"],
      "food-safety monitoring by a home robot",
      "the door display reads 42 °F (5.6 °C), which is the setpoint, not the measured air temperature",
      [5.6, 4.4, 5.6, 2.9], obj="air on the middle shelf", moment="after the doors are closed"),
    q(S3, 2, "rigid_distance", "angle",
      "The largest opening angle in degrees of the left fresh-food door during the video, between its closed and open positions about the hinge.",
      "largest opening angle of the left door", 118, "deg", 1, "protractor at the hinge, door pushed to the same stop as in the video",
      ["dynamic_scene", "fast_or_shaky_camera", "reflection_mirror"],
      "opening an articulated door with a robot arm",
      "the door is moving and only partly in frame at its widest; stainless steel reflects the room",
      [95, 140, 100, 90], obj="left fresh-food door", moment="widest opening"),
    q(S3, 3, "liquid_volume", "volume",
      "The volume in mL of juice left in the orange-labelled carton in the lower bin of the right door.",
      "volume of juice left in the carton", 610, "mL", 5, "carton emptied into a measuring cylinder after filming",
      ["occlusion", "imagined_state"],
      "kitchen inventory and pouring the right amount",
      "the carton is opaque; the fill level can only be inferred, e.g. from how it moves when the door swings",
      [946, 473, 880, 1000], obj="orange-labelled carton in the right door's lower bin"),
    q(S3, 4, "rigid_distance", "gap",
      "The vertical clearance in cm between the top shelf and the ceiling of the fresh-food compartment.",
      "clearance above the top shelf", 24.5, "cm", 0.2, "tape measure from the shelf surface to the ceiling liner",
      ["fit_affordance", "physical_gap", "occlusion"],
      "whether a tall bottle fits upright on the top shelf",
      "the ceiling is lit from above and seen at a steep angle; items on the shelf hide its surface",
      [30.0, 19.5, 31.2, 20.1], point_a="top surface of the top shelf", point_b="ceiling of the fresh-food compartment"),
    q(S3, 5, "object_weight", "mass",
      "The total mass in grams of all the kiwis in the bottom crisper drawer.",
      "total mass of the kiwis in the crisper drawer", 2214, "g", 2, "kiwis weighed together on a kitchen scale",
      ["clutter_stacking", "occlusion", "irregular_shape"],
      "payload when lifting a full drawer or a box of produce",
      "the kiwis are packed in layers and only the top layer is visible",
      [1450, 2900, 1650, 3100], obj="kiwis in the bottom crisper drawer"),
    q(S3, 6, "rigid_distance", "distance",
      "How far in cm the freezer drawer is pulled out at its furthest during the video, measured at the drawer front from its closed position.",
      "pull-out distance of the freezer drawer at its furthest", 46.5, "cm", 0.3, "tape measure along the drawer side at the same stop",
      ["dynamic_scene", "fast_or_shaky_camera", "long_context"],
      "pulling a drawer the right distance before reaching in",
      "the drawer opens late in a long video, mostly seen from above with motion blur",
      [36.0, 58.2, 38.5, 60.0], obj="freezer drawer", moment="furthest pull-out"),
])

S4 = "demo-yuzhou-s04"
s4 = scene(S4, "kitchen",
    "A crowded drying rack with glass lids, knives and utensils next to a steel kettle and a rice cooker; the dishwasher is opened, both racks are pulled out to show stacked bowls, pans and spatulas, then it is closed again.",
    "the drying rack and everything in it, the kettle, the rice cooker, and the dishwasher with both racks and every dish in them", True,
    "IMG_1587.MOV", 1242, 41.407, [
    q(S4, 1, "rigid_distance", "gap",
      "The gap in mm between the two glass pot lids standing in the drying rack, at their closest point.",
      "closest gap between the two glass lids", 14, "mm", 0.3, "feeler gauge set between the lid rims",
      ["transparency", "reflection_mirror", "physical_gap", "clutter_stacking"],
      "pulling one lid out of a rack without knocking the other",
      "both lids are transparent and reflective, so their rims are the only visible edges",
      [25, 8, 22, 6], point_a="the larger glass lid", point_b="the smaller glass lid"),
    q(S4, 2, "liquid_volume", "volume",
      "The capacity in mL of the large white scalloped ceramic bowl in the dishwasher's lower rack, filled to the rim.",
      "capacity of the scalloped bowl, filled to the rim", 2140, "mL", 10, "filled with water to the rim, poured into a measuring jug",
      ["irregular_shape", "occlusion", "clutter_stacking"],
      "serving or pouring into a bowl without overflowing",
      "the scalloped rim and the bowl's depth are seen only from above, inside a crowded rack",
      [1500, 2900, 1650, 3050], obj="large white scalloped ceramic bowl"),
    q(S4, 3, "object_weight", "mass",
      "The total mass in kg of all the dishes and utensils in the dishwasher's upper rack.",
      "total mass of everything in the upper rack", 3.42, "kg", 0.01, "every item weighed on a kitchen scale and summed",
      ["clutter_stacking", "occlusion", "dynamic_scene"],
      "payload and grip force when a robot unloads a dishwasher rack",
      "items are stacked and overlapping, and their materials (ceramic, steel, plastic) differ",
      [2.4, 4.6, 2.6, 4.9], obj="everything in the upper rack"),
    q(S4, 4, "rigid_distance", "gap",
      "With both racks pushed in, the gap in mm between the top of the tallest item in the lower rack and the underside of the upper rack.",
      "clearance between the lower-rack items and the upper rack, racks pushed in", 18, "mm", 0.4,
      "racks pushed in, ruler through the gap at the tallest item",
      ["imagined_state", "physical_gap", "fit_affordance"],
      "loading a dishwasher without collisions",
      "in the video the racks are pulled out; the pushed-in state is never shown",
      [35, 0, 30, 6], point_a="top of the tallest item in the lower rack", point_b="underside of the upper rack", moment="racks pushed in"),
    q(S4, 5, "material_composition", "declared",
      "By mass, the percentage of everything in the drying rack (not the rack itself) that is stainless steel.",
      "stainless-steel share by mass of the drying rack's contents", 61, "percent", 1,
      "every item weighed and sorted by material (steel, glass, plastic, wood)",
      ["transparency", "clutter_stacking", "color"],
      "sorting cookware by material for washing or recycling",
      "steel and glass reflect each other, and mass by material needs volume and density for every item",
      [40, 78, 45, 80], obj="contents of the drying rack"),
    q(S4, 6, "image_frame", "px_area",
      "In frame 450 of the video (frames count from 0), the number of pixels covered by the visible part of the lime-green colander.",
      "visible pixel area of the lime-green colander in frame 450", 18900, "px", 300, "mask from one click, edges corrected by hand",
      ["occlusion", "color"],
      "checking that an item is visible and graspable before a pick",
      "partly hidden behind the black basket, and its holes leave gaps in the mask",
      [26400, 13100, 24800, 12600], obj="lime-green colander (visible part)", frame=450),
])

for s in (s2, s3, s4):
    d = OUT / s["scene_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "scene.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n")
    print(d / "scene.json", len(s["queries"]), "queries")
