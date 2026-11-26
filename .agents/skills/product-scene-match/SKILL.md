---
name: product-scene-match
description: Integrate an existing product photograph into a reference scene. Use for reference-matched product photography, removing lettering and the previous subject, rebuilding scene perspective around a locked foreground, and exporting a high-resolution PNG with the original product proportions and pixel dimensions.
---

# Product Scene Match

Deliver an actual, readable high-resolution PNG. Use the reference to determine the environment and the user's product photo to determine the foreground. By default, preserve the dimensions of the visible product in pixels and allow only translation on the final canvas. If the user separately authorizes a target frame proportion or uniform scale, record it explicitly. Do not infer permission to warp the subject.

## 1. Identify the two inputs

- Distinguish the reference scene from the user's product. Prefer supplied images, links and transparent source assets. If asked to find a reference, search by setting, palette, support surface and camera position. Open the selected reference at a useful size. Choose assets cleared for public use when preparing public examples. Clarify only when the two roles remain genuinely ambiguous.
- Ask for the original product photo if the exact item is missing. An empty scene can be prepared separately. Do not substitute a similar product. Use supplied materials only for the requested work.
- Inspect the visible top and side faces, silhouette dimensions, base contact points, openings, markings and highlight direction. Preserve the source photo and original mask. Distinguish the source canvas from the bounding box of nonzero alpha.
- For a transparent PNG, inspect its holes, edges and residual shadows. For an opaque photo, extract a mask aligned to the original pixel grid. If an extraction tool redraws the product, use only the verified mask and composite the original RGB. Exclude the previous background and ground shadow. Inspect glass, perforations and glossy surfaces at full size. Ask for a better cutout or original layers when a baked-in background cannot be separated reliably.

## 2. Rebuild a text-free background

Use a reference-conditioned image editor, or reposition the camera in a supplied scene project and render. Supply the product photo to the editor only as a camera and lighting reference. Request an empty background without any product.

Build the editing instructions with the [scene direction guide](references/scene-direction.md). Retain recognizable materials, palette, support surface and key props. Remove the old subject, fragments, reflections, cast shadows, titles, digits, signs, labels and reflected lettering from the reference. Preserve markings on the user's own product. Rebuild the horizon, support plane edges and vanishing directions based on the visible faces of the product. Reconstruct distinct planes and occlusions in multi-depth scenes. Restrict a homography to a single plane.

Compare at least two relevant cues between the original reference and the rebuilt scene, such as the near and far plinth edges, a wall junction or the horizon. Revise the background if its camera angle disagrees with the product. One flat warp cannot resolve a viewpoint change across multiple depth layers.

## 3. Composite the original foreground

- Set the final canvas before positioning the product. Preserve the reference aspect ratio. Unless the user specifies a size, use a long edge of at least 3840 px, retaining a larger source plate at native size. Prefer a plate close to the delivery dimensions. Report any background upscaling and any limitations of the original product resolution.
- Find the actual support point and use it to calculate the top-left corner of the product's visible bounds in final-canvas coordinates. Reframe the surroundings or adjust the scene camera when the native-size product is a poor fit. Include the full silhouette, handles, cables and protrusions.
- Adapt scene lighting to the product highlights. On the background, match the shape, direction and softness of contact shadows and reflections to the base. Remove temporary stand-ins and check for ghost silhouettes. Exposing the whole product is the default. Confirm an intentional foreground occlusion if it would hide product details.
- Run [compose.py](scripts/compose.py) for the final lossless composite. It trims transparent padding and translates the product at integer coordinates without resampling its pixels. An RGB source can use a separate aligned grayscale mask, white for the product. Use an existing alpha channel directly. When using a layer editor, keep the original foreground layer and verify the same pixel and geometry requirements.
- Return to the original product pixels after generating the background. Treat any model-rendered substitute or empty background as an intermediate result.

Run from the skill directory with Python 3.9+ and Pillow 9.1+, replacing the sample paths and coordinates with those of the actual job.

```sh
python3 scripts/compose.py --product product.png --plate clean-plate.png \
  --x 1450 --y 1020 --output result.png --report geometry.json
```

`--x` and `--y` locate the top-left corner of the nonzero-alpha bounding box on the final canvas. Pass `--mask mask.png` for a separate mask, or `--long-edge 4096` to override output size. On a flat support surface, repeat `--shadow CX CY RX RY ANGLE BLUR OPACITY` to build soft elliptical shadows beneath the product. Coordinates, radii and blur are in final-canvas pixels. Angle is clockwise in degrees and opacity ranges from 0 to 1. Prepare complex reflections and shadows in the scene plate. Choose new output filenames. Use 8-bit RGB/RGBA stills or color-managed exports for the inputs. The script adapts the plate to the product color space.

## 4. Verify the exported image

1. Open the exported PNG and compare it with the source. Check the top ellipse, visible side widths, handle and button orientation, printed marks and small parts. Read the geometry report. Confirm native visible dimensions, scale 1, rotation 0 and exact values for opaque product pixels. Semi-transparent borders must blend at their original alpha.
2. Inspect contact edges, openings, light borders and reflections at 100%. Correct halos, floating bases, remnants of the previous object and inconsistent shadows.
3. Inspect the corners, walls, support surface, prop labels, reflections and small decorations for remaining reference text or pseudo-lettering. If OCR is available, use it outside the product area and visually review its findings. A blank OCR result alone cannot confirm cleanup. Repair the background and repeat the composite as needed.
4. Verify the actual format and dimensions, deliver a link to the final image, and state whether the background was enlarged. If a reliable mask, product source or background editing capability is missing, identify the affected step and label any partial output clearly.
