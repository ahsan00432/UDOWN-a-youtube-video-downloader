from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).parent


def create_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (24, 61, 54, 255))
    draw = ImageDraw.Draw(image)
    scale = size / 256

    def point(value: int) -> int:
        return round(value * scale)

    margin = point(24)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=point(48), fill=(8, 127, 112, 255),
    )
    center = size // 2
    shaft_width = max(point(28), 2)
    draw.rounded_rectangle(
        (center - shaft_width // 2, point(54), center + shaft_width // 2, point(151)),
        radius=shaft_width // 2, fill=(255, 255, 255, 255),
    )
    draw.polygon(
        [(point(68), point(121)), (center, point(190)), (point(188), point(121))],
        fill=(255, 255, 255, 255),
    )
    draw.rounded_rectangle(
        (point(61), point(188), point(195), point(207)),
        radius=point(9), fill=(255, 255, 255, 255),
    )
    return image


def main() -> None:
    assets = ROOT / "assets"
    extension_icons = ROOT / "browser_extension" / "icons"
    assets.mkdir(exist_ok=True)
    extension_icons.mkdir(parents=True, exist_ok=True)

    create_icon(256).save(assets / "udown.ico", format="ICO", sizes=[(256, 256)])
    for size in (16, 32, 48, 128):
        create_icon(size).save(extension_icons / f"icon-{size}.png", format="PNG")


if __name__ == "__main__":
    main()