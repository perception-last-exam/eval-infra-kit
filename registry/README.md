# Scene registry

Live page: https://claude.ai/artifact/D1iSfGBnq3Zr8h8RXBYUfx. Source: `index.html` in this folder; republish it to
the same URL with Claude Code.

`index.html` ("Round 2 Data Collection") is the viewer: a scene list, scene detail with video and frame stepping, an
All-queries table, a Drive tab, and JSON/CSV export. `dashboard-v1.html` is the earlier, fuller version kept for later: stats, verdict charts, field checks,
and a scene.json builder with a Claude wording check. It is not published.

## How data flows

```
collectors ──upload──► Google Drive: Second-Round-Data-Collection/<name>/...  (videos, evidence, scene.json)
                                   │
              Check Drive + Import (page button)  ·  playback copies (Claude Code)
                                   ▼
             registry database: scenes/<scene_id>  (scene.json + thumb_asset + drive info)
                                meta/sync          (last Drive check: per-folder status, counts)
                                   ▼
                       registry page (anyone with the link who is signed in reads it)
```

- Visitors who aren't in the owner's organization can read but never write, so collectors write to Drive, not to
  the page.
- **Check Drive** (top bar, and on the Drive tab) runs in the browser on the viewer's own Google Drive connector
  (`search_files`, `download_file_content`). It walks the root folder, marks every scene folder New / Updated on
  Drive / ID already taken / scene.json problem / Video, no scene.json / Gone from Drive / Not on Drive / In registry, and saves the
  result to `meta/sync` so every viewer sees the latest check. Only people with Google Drive connected in claude.ai
  see the button; only editors (the owner) can import or save.
- **Import** copies a scene.json, plus a `thumbnail.*` in the same folder, into `scenes/<scene_id>` and records the
  Drive location in `drive`. It never overwrites a scene that is linked to another Drive folder that still exists.
  A registry copy is treated as the same scene (keeping its playable video) only when `input_video` and
  `collector` match.
- After a check, the owner picks one of two bulk actions on the Drive tab:
  - **Import N new** adds only scenes that aren't in the registry yet (rows marked New). A row marked Updated on
    Drive has its own Update button.
  - **Sync all with Drive** rescans Drive, then lists what it will do and waits for **Sync now** / **Sync and
    remove N**: import every new scene, re-read every linked scene from its scene.json on Drive (keeping the
    thumbnail and playable video unless the Drive files behind them changed), and delete the registry scenes that
    are no longer on Drive. Those are scenes whose scene.json is gone ("Gone from Drive") and scenes that no Drive
    folder holds ("Not on Drive"). Scenes whose Drive copy is broken or has a clashing ID are left as they are.
    Nothing is removed if the Drive listing was cut short, if Drive sent back no scene.json files at all, or if the
    sync stopped on a connector error. Removal deletes only the `scenes/<id>` document; its thumbnail and video
    assets stay in the asset store, and nothing on Drive changes.
- Playable video copies still need Claude Code (ffmpeg); the Drive tab counts imported scenes still waiting for one.

Drive layout: each folder at the top of Second-Round-Data-Collection is one person (its name becomes the scene's
`collector`; a different name written in scene.json is kept as `collector_as_written`). Files directly at the top are
ignored. The viewer's scene header shows only Reconstruction scope and Video input; scenes carry no origin, axis or
capture fields because the agent defines its own coordinate system.

## Playback copies and full sync (Claude Code)

Run this when the Drive tab says imported scenes have no playable video, or to do the whole sync without the page.

1. Walk the folder tree from the root (`search_files` with `parentId = '<id>'`), recording per top-level folder the
   number of videos, photos and files, its `scene.json` count, and its newest `modifiedTime`.
2. For each `scene.json`, `download_file_content`, decode base64, parse JSON. On a parse failure, record
   `{path, error}` in `meta/sync.errors` and skip.
3. Use `scene_id` from the file, or else the folder name. Keep every field as written.
4. Thumbnail: use a `thumbnail.jpg` in the scene folder if present; otherwise grab a frame from the video.
   Upload it as an artifact asset and set `thumb_asset`.
   Playable video: download the input video. The Drive folder is link-shared, so `gdown` works; the connector's
   base64 download doesn't suit large files. Make a playback copy and upload it as an asset (20 MiB cap), then
   set `video_asset`. The copy is an upright 720p H.264 MP4 with no audio, at a constant frame rate equal to the
   scene's fps so frame numbers line up. For iPhone HDR (HLG), tone-map, or colors come out washed out:
   `-an -vf "scale=720:-2,zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p" -fps_mode cfr -r <fps> -c:v libx264 -preset veryfast -crf 26 -g <fps> -movflags +faststart -map_metadata -1`.
   Before uploading, look through frames of the whole video for faces, reflections and personal details: the page
   may be public.
5. Write `scenes/<scene_id>` with `drive: {folder_id, folder_url, path, scene_json_id, modified, thumb_id,
   thumb_modified, videos: [{id, title, size, url}], imported_at}` (the same shape the page's Import writes). The page
   owns `meta/sync`: `{checked_at, root, root_url, n_folders, n_files, counts, items: [...], folders: [...]}`.
6. When syncing from Claude Code, don't delete a scene document because it is missing from Drive; set
   `drive.missing: true` instead. Deleting is left to the page's Sync all, which asks the owner first.

Example records (`demo: true`, IDs `demo-*`, eight of them) can be deleted in one batch once real data arrives. Three of them, `demo-yuzhou-s02`–`s04` (cluttered desk IMG_1580, fridge IMG_1583, dishwasher IMG_1587), also carry `difficulty_anchor: true`; the viewer tags them "Difficulty anchor". They are deliberately hard reference scenes with six metrics each across the domains and challenges, and illustrative GT and runs. They are generated by `registry/demo/make_anchors.py`; it writes to `$R2S_EXAMPLES/yuzhou/`, by default `../registry-demo/_examples/yuzhou/` next to this checkout. Their
Drive copies are in `../registry-demo/_examples/` next to this checkout (upload that folder into the root).
