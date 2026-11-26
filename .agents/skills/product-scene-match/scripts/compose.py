#!/usr/bin/env python3
"""Place original product pixels over an opaque, camera-matched background plate."""
import argparse
import io
import json
import math
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageFilter, ImageOps


def read_image(path):
    with Image.open(path) as src:
        if getattr(src, "n_frames", 1) != 1:
            raise ValueError(f"{path.name}: export a single still image.")
        if src.mode not in ("RGB", "RGBA", "L", "LA", "P", "1"):
            raise ValueError(f"{path.name}: use an 8-bit RGB/sRGB image or a grayscale mask.")
        return ImageOps.exif_transpose(src).copy()


def profile_from(data):
    return ImageCms.ImageCmsProfile(io.BytesIO(data)) if data else ImageCms.createProfile("sRGB")


def read_product(path, mask_path):
    source = read_image(path)
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    if mask_path:
        if alpha.getextrema()[0] != 255:
            raise ValueError("Use either the existing product alpha or a separate mask, not both.")
        mask = read_image(mask_path)
        if mask.size != rgba.size:
            raise ValueError("Mask and product must have identical, orientation-corrected pixel dimensions.")
        if mask.mode not in ("L", "1"):
            raise ValueError("Export the mask as 8-bit grayscale, white product on black background.")
        alpha = mask.convert("L")
        rgba.putalpha(alpha)
    if alpha.getextrema()[0] == 255:
        raise ValueError("Product is fully opaque. Supply a grayscale silhouette mask or an RGBA cutout.")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("The mask contains no visible product pixels.")
    return rgba.crop(bbox), bbox, source.size, source.info.get("icc_profile")


def prepare_plate(path, long_edge, product_icc):
    raw = read_image(path)
    if raw.convert("RGBA").getchannel("A").getextrema()[0] != 255:
        raise ValueError("The background plate must be opaque across the entire canvas.")
    plate_icc = raw.info.get("icc_profile")
    plate = raw.convert("RGB")
    if plate_icc != product_icc:
        # Preserve encoded RGB values of the product; adapt the scene instead.
        plate = ImageCms.profileToProfile(plate, profile_from(plate_icc), profile_from(product_icc),
                                          outputMode="RGB")
    original_size = plate.size
    target = long_edge if long_edge is not None else max(3840, *original_size)
    if target <= 0:
        raise ValueError("The requested long edge must be a positive pixel count.")
    dims = tuple(max(1, round(side * target / max(original_size))) for side in original_size)
    if dims[0] * dims[1] > 85_000_000:
        raise ValueError("Requested output exceeds this tool's 85 MP limit.")
    if dims != original_size:
        plate = plate.resize(dims, Image.Resampling.LANCZOS)
    return plate, original_size


def add_ground_shadow(plate, params):
    """Darken a local patch of the background with a soft rotated ellipse."""
    cx, cy, rx, ry, angle, blur, opacity = params
    if not all(math.isfinite(v) for v in params):
        raise ValueError("Shadow parameters must be finite.")
    if not (0 <= cx < plate.width and 0 <= cy < plate.height and
            0 < rx <= plate.width and 0 < ry <= plate.height and
            0 <= blur <= max(plate.size) / 4 and 0 <= opacity <= 1):
        raise ValueError("Check shadow center, radii, blur and opacity (0 through 1).")
    a = math.radians(angle)
    spread_x = math.hypot(rx * math.cos(a), ry * math.sin(a)) + 3 * blur + 2
    spread_y = math.hypot(rx * math.sin(a), ry * math.cos(a)) + 3 * blur + 2
    left, top = max(0, math.floor(cx - spread_x)), max(0, math.floor(cy - spread_y))
    right, bottom = min(plate.width, math.ceil(cx + spread_x)), min(plate.height, math.ceil(cy + spread_y))
    mask = Image.new("L", (right - left, bottom - top))
    points = []
    for step in range(160):
        t = 2 * math.pi * step / 160
        x, y = rx * math.cos(t), ry * math.sin(t)
        points.append((cx - left + x * math.cos(a) - y * math.sin(a),
                       cy - top + x * math.sin(a) + y * math.cos(a)))
    ImageDraw.Draw(mask).polygon(points, fill=round(255 * opacity))
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    plate.paste((0, 0, 0), (left, top, right, bottom), mask)


def publish_new(temp, destination):
    # Both paths are in one directory. A hard link makes the completed file visible
    # atomically and cannot clobber another process's result.
    os.link(temp, destination)


def compose(args):
    if args.output.suffix.lower() != ".png":
        raise ValueError("Output must be a PNG file.")
    if args.report and args.report.suffix.lower() != ".json":
        raise ValueError("The optional report must be a separate JSON file.")
    targets = [args.output] + ([args.report] if args.report else [])
    for target in targets:
        if target.exists() or target.is_symlink():
            raise ValueError(f"Output already exists: {target}. Choose a new filename.")
        target.parent.mkdir(parents=True, exist_ok=True)
    product, source_box, source_size, product_icc = read_product(args.product, args.mask)
    plate, plate_size = prepare_plate(args.plate, args.long_edge, product_icc)
    x, y = args.x, args.y
    w, h = product.size
    if x < 0 or y < 0 or x + w > plate.width or y + h > plate.height:
        raise ValueError(f"The {w} × {h} product does not fit at ({x}, {y}) on {plate.size}. Reframe the scene.")
    for params in args.shadow:
        add_ground_shadow(plate, params)
    rectangle = (x, y, x + w, y + h)
    alpha = product.getchannel("A")
    foreground = product.convert("RGB")
    expected = Image.composite(foreground, plate.crop(rectangle), alpha)
    plate.paste(expected, rectangle)
    opaque = alpha.point(lambda value: 255 if value == 255 else 0)
    coverage = alpha.histogram()
    metadata = {
        "canvas_px": list(plate.size), "plate_native_px": list(plate_size),
        "plate_upscaled": max(plate.size) > max(plate_size),
        "product_source_canvas_px": list(source_size),
        "product_source_bbox_xyxy": list(source_box), "product_output_bbox_xyxy": list(rectangle),
        "product_visible_size_px": [w, h], "product_scale": 1, "product_rotation_deg": 0,
        "ground_shadows_xy_radii_angle_blur_opacity": args.shadow,
        "opaque_pixels_checked": coverage[255], "blended_pixels_checked": sum(coverage[1:255]),
        "flattened_crop_exact": True,
    }
    with tempfile.TemporaryDirectory(dir=args.output.parent) as temp:
        tmp_png = Path(temp) / "verified.png"
        kwargs = {"icc_profile": product_icc} if product_icc else {}
        plate.save(tmp_png, "PNG", **kwargs)
        with Image.open(tmp_png) as actual:
            patch = actual.convert("RGB").crop(rectangle)
        if ImageChops.difference(patch, expected).getbbox():
            raise ValueError("The exported pixels differ from the expected alpha composite.")
        diff = ImageChops.difference(patch, foreground)
        if Image.composite(diff, Image.new("RGB", product.size), opaque).getbbox():
            raise ValueError("An opaque product pixel changed during export.")
        if args.report:
            with tempfile.TemporaryDirectory(dir=args.report.parent) as report_dir:
                tmp_json = Path(report_dir) / "qa.json"
                tmp_json.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
                publish_new(tmp_png, args.output)
                try:
                    publish_new(tmp_json, args.report)
                except OSError:
                    args.output.unlink()
                    raise
        else:
            publish_new(tmp_png, args.output)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, required=True, help="Original RGBA cutout or source RGB with --mask")
    parser.add_argument("--mask", type=Path, help="Original-size L/1 mask aligned to the source")
    parser.add_argument("--plate", type=Path, required=True, help="Opaque, text-free, camera-matched background")
    parser.add_argument("--x", type=int, required=True, help="Left edge of the visible product on the FINAL canvas")
    parser.add_argument("--y", type=int, required=True, help="Top edge of the visible product on the FINAL canvas")
    parser.add_argument("--long-edge", type=int, help="Final long edge; default keeps or increases the plate to 3840 px")
    parser.add_argument("--shadow", nargs=7, type=float, action="append", default=[],
                        metavar=("CX", "CY", "RX", "RY", "ANGLE", "BLUR", "OPACITY"),
                        help="Optional flat-surface shadow in final-canvas pixels; angle clockwise, opacity 0..1. Repeatable.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    try:
        print(json.dumps(compose(parser.parse_args()), ensure_ascii=False))
    except (OSError, ValueError, Image.DecompressionBombError, ImageCms.PyCMSError) as err:
        parser.exit(2, f"compose: {err}\n")


if __name__ == "__main__":
    main()
