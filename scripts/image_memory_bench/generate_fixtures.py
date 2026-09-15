"""Generate seeded fixtures outside the measured application process."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw


def generate(output: Path, seed: int) -> list[dict]:
    """Create ten inputs for one paired experiment seed.

    Args:
        output: New directory for this seed's fixtures.
        seed: Stable seed for pixel generation.

    Returns:
        On-disk hashes and decoded image metadata.
    """
    output.mkdir(parents=True, exist_ok=False)
    rng = random.Random(seed)
    records = []
    for kind in ("png", "jpeg", "webp", "gif", "screenshot"):
        for stress in (False, True):
            name = f"{kind}-{'stress' if stress else 'ordinary'}"
            options = {}
            if kind in ("png", "webp"):
                size = (1280, 1280) if stress else (320, 240)
                image = (
                    Image.frombytes("RGBA", size, rng.randbytes(size[0] * size[1] * 4))
                    if stress
                    else Image.new("RGBA", size, (40, 120, 200, 127))
                )
                image_format = kind.upper()
                options = {"lossless": stress} if kind == "webp" else {}
            elif kind == "jpeg":
                size = (4000, 3000) if stress else (640, 480)
                image = Image.frombytes(
                    "RGB", size, rng.randbytes(size[0] * size[1] * 3)
                )
                image_format = "JPEG"
                options = {"quality": 95 if stress else 75}
                if stress:
                    exif = image.getexif()
                    exif[274] = 6
                    options["exif"] = exif
            elif kind == "gif":
                image = Image.new("RGB", (320, 240), (seed % 255, 0, 255))
                image_format = "GIF"
                frames = []
                for frame in range(24 if stress else 3):
                    extra = Image.new("RGB", image.size, (frame * 9, 80, 20))
                    ImageDraw.Draw(extra).rectangle(
                        (frame * 5, 10, frame * 5 + 30, 50), fill="white"
                    )
                    frames.append(extra)
                options = {
                    "save_all": True,
                    "append_images": frames,
                    "duration": 80,
                    "loop": 0,
                }
            else:
                image = Image.new(
                    "RGB", (3840, 2160) if stress else (1920, 1080), "#202124"
                )
                image_format = "PNG"
                draw = ImageDraw.Draw(image)
                for row in range(image.height // 20):
                    draw.text(
                        (100, row * 20),
                        f"coordinate (100, {row * 20}) seed={seed} command --verbose "
                        * 4,
                        fill="#e8eaed",
                    )
                draw.rectangle((20, 20, 70, 70), outline="red", width=3)
            path = output / f"{name}.{image_format.lower()}"
            try:
                image.save(path, image_format, **options)
            finally:
                image.close()
                for frame_image in options.get("append_images", []):
                    frame_image.close()
            # Reopen the saved bytes: in-memory Image.format and frame counts
            # do not describe what the encoder actually persisted.
            with Image.open(path) as saved:
                record = {
                    "path": path.name,
                    "kind": kind,
                    "stress": stress,
                    "seed": seed,
                    "format": saved.format,
                    "width": saved.width,
                    "height": saved.height,
                    "mode": saved.mode,
                    "frames": getattr(saved, "n_frames", 1),
                    "orientation": saved.getexif().get(274, 1),
                    "has_alpha": saved.mode in ("RGBA", "LA")
                    or "transparency" in saved.info,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            records.append(record)
    (output / "manifest.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )
    return records


def main() -> int:
    """Generate three paired seeds unless explicitly overridden."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 19, 43])
    args = parser.parse_args()
    for seed in args.seeds:
        records = generate(args.output / str(seed), seed)
        print(json.dumps({"seed": seed, "count": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
