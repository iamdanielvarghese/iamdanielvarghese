"""
Convert a background-removed portrait into an ASCII character grid.

Pipeline:
  1. Load RGBA cutout, apply the chosen crop box.
  2. Convert to grayscale, apply CLAHE (local contrast) so fabric/features
     don't collapse into flat blobs.
  3. Downsample to a target character grid using area averaging (so each
     cell reflects the true average brightness of that block, not a single
     sampled pixel).
  4. Map brightness -> density character. Alpha-transparent cells become
     blank (space), preserving the cutout silhouette.
"""
import cv2
import numpy as np
from PIL import Image

SOURCE = "portrait_nobg.png"
CROP_BOX = (290, 355, 830, 1130)  # left, top, right, bottom - waist up
# Grid dims chosen so COLS/ROWS accounts for monospace char cell aspect
# (~0.5 width:height) against the crop's pixel aspect (540:775), so the
# rendered portrait isn't stretched/squished.
COLS = 96
ROWS = 68
ALPHA_THRESHOLD = 60

# Density ramp: index 0 = lightest/least ink, last = darkest/most ink.
RAMP = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
# Trim to a shorter, cleaner ramp for legibility at small sizes.
RAMP = " .:-=+*#%@"


def main():
    img = Image.open(SOURCE).convert("RGBA")
    img = img.crop(CROP_BOX)

    rgba = np.array(img)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]

    # Clean up the segmentation mask: rembg often leaves small holes in
    # fine hair strands, which show up as speckled gaps in the ASCII grid.
    # Morphological closing fills those; opening removes stray fragments.
    alpha_bin = (alpha > 50).astype(np.uint8) * 255
    close_kernel = np.ones((9, 9), np.uint8)
    open_kernel = np.ones((3, 3), np.uint8)
    alpha_clean = cv2.morphologyEx(alpha_bin, cv2.MORPH_CLOSE, close_kernel)
    alpha_clean = cv2.morphologyEx(alpha_clean, cv2.MORPH_OPEN, open_kernel)
    # Feather the cleaned mask slightly so edges stay smooth, not stair-stepped.
    alpha_clean = cv2.GaussianBlur(alpha_clean, (5, 5), 0)
    alpha = alpha_clean

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Denoise slightly before contrast enhancement so we don't amplify
    # sensor/JPEG noise in flat dark regions (hair) into fake texture.
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Local contrast (CLAHE) so the light-blue shirt renders as fabric
    # with visible stripes/folds rather than a flat mid-tone slab.
    # Gentler clipLimit than before - the earlier 2.5 over-amplified noise
    # in low-detail dark regions like hair into speckled artifacts.
    clahe = cv2.createCLAHE(clipLimit=1.3, tileGridSize=(8, 8))
    gray_eq = clahe.apply(gray)

    h, w = gray_eq.shape
    cell_w = w / COLS
    cell_h = h / ROWS

    grid_chars = []
    grid_brightness = []  # normalized 0-1, for later SVG color use
    for row in range(ROWS):
        y0 = int(row * cell_h)
        y1 = max(y0 + 1, int((row + 1) * cell_h))
        char_row = []
        bright_row = []
        for col in range(COLS):
            x0 = int(col * cell_w)
            x1 = max(x0 + 1, int((col + 1) * cell_w))

            cell_alpha = alpha[y0:y1, x0:x1]
            if cell_alpha.mean() < ALPHA_THRESHOLD:
                char_row.append(" ")
                bright_row.append(0.0)
                continue

            cell_gray = gray_eq[y0:y1, x0:x1]
            avg = cell_gray.mean()  # 0..255, higher = brighter
            # darker pixel -> denser char
            density = 1.0 - (avg / 255.0)
            idx = min(len(RAMP) - 1, int(density * len(RAMP)))
            char_row.append(RAMP[idx])
            bright_row.append(avg / 255.0)
        grid_chars.append(char_row)
        grid_brightness.append(bright_row)

    # Write plain-text preview
    with open("portrait.txt", "w") as f:
        for row in grid_chars:
            f.write("".join(row) + "\n")

    # Write brightness grid alongside (for SVG color shading later)
    with open("portrait_brightness.txt", "w") as f:
        for row in grid_brightness:
            f.write(",".join(f"{v:.3f}" for v in row) + "\n")

    print(f"Wrote portrait.txt ({COLS}x{ROWS})")


if __name__ == "__main__":
    main()
