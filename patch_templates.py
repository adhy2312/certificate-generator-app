"""
patch_templates.py
------------------
Replaces MR. MELVIN JACOB (and his signature) in the centre signatory block
of all 5 certificate templates with DR. ADARSH S. J. and the new signature.

Only the PNG template files are modified – no codebase changes.
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SIG_SRC = os.path.join(ROOT, "Certificate Of  Merit.png")   # just used for reference
NEW_SIG_PATH = os.path.join(ROOT, "new_signature.png")      # the user-supplied signature

TEMPLATES = [
    "CERT TEMPLATE.png",
    "Certificate Of  Merit.png",
    "Certificate Of  Appreciation.png",
    "Certificate Of  Recognition.png",
    "Certificate Of  Volunteering.png",
]

# New label lines for the centre block
NEW_TITLE   = "DR. ADARSH S. J."
NEW_ROLE    = "Faculty Advisor"
NEW_DEPT    = "ISTE SC MBCET"

# ─── Helper: sample background colour around a point ─────────────────────────
def sample_bg(img, cx, cy, radius=6):
    """Return the median colour of a small ring around (cx,cy)."""
    arr = np.array(img.convert("RGB"))
    h, w = arr.shape[:2]
    samples = []
    for dy in range(-radius, radius+1):
        for dx in range(-radius, radius+1):
            nx, ny = cx+dx, cy+dy
            if 0 <= nx < w and 0 <= ny < h:
                samples.append(arr[ny, nx])
    med = np.median(samples, axis=0).astype(int)
    return tuple(med)


def find_font(size, bold=False):
    """Try common font paths; fall back to default."""
    candidates = [
        os.path.join(ROOT, "backend", "fonts", "georgiab.ttf" if bold else "georgia.ttf"),
        "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_white_bg_signature(sig_path, target_w, target_h):
    """
    Load the signature PNG (black ink on white/transparent), resize to fit
    within target_w x target_h while keeping aspect ratio, and return as RGBA.
    The white areas become transparent so it composites cleanly over the cert.
    """
    sig = Image.open(sig_path).convert("RGBA")

    # Make pure-white pixels transparent so the cert bg shows through
    data = np.array(sig)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    # Pixels that are very light → make transparent
    white_mask = (r > 200) & (g > 200) & (b > 200)
    data[white_mask, 3] = 0
    sig = Image.fromarray(data, "RGBA")

    # Crop to actual ink bounding box
    bbox = sig.getbbox()
    if bbox:
        sig = sig.crop(bbox)

    # Scale to fit in (target_w x target_h) preserving AR
    iw, ih = sig.size
    scale = min(target_w / iw, target_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    sig = sig.resize((new_w, new_h), Image.Resampling.LANCZOS)
    return sig


def patch_template(template_filename, new_sig):
    path = os.path.join(ROOT, template_filename)
    if not os.path.exists(path):
        print(f"  WARN Not found: {path}")
        return

    img = Image.open(path).convert("RGBA")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    # ── Locate the centre signatory column ──────────────────────────────────
    # The three signatories are roughly at x = 18%, 50%, 82% of width.
    # We only touch the centre column (around x=50%).
    cx = int(W * 0.50)

    # The signature block occupies roughly y = 72%–95% of height.
    # We'll erase a rectangle that covers the old signature + name lines.
    sig_top     = int(H * 0.71)
    sig_bottom  = int(H * 0.97)
    col_left    = int(W * 0.35)
    col_right   = int(W * 0.65)

    # ── Sample background colour from just above the block ──────────────────
    # Use a strip near the top-left of the erase zone that is surely bg
    bg_sample_x = cx
    bg_sample_y = int(H * 0.695)
    bg_colour   = sample_bg(img, bg_sample_x, bg_sample_y, radius=15)
    bg_rgba     = bg_colour + (255,)

    # ── Erase the old block ─────────────────────────────────────────────────
    erase_box = [col_left, sig_top, col_right, sig_bottom]
    draw.rectangle(erase_box, fill=bg_rgba)

    # ── Paste new signature ─────────────────────────────────────────────────
    # Target area for the signature image: roughly 22% wide, 12% tall
    sig_area_w = int(W * 0.22)
    sig_area_h = int(H * 0.11)

    sig_img = make_white_bg_signature(new_sig, sig_area_w, sig_area_h)
    sw, sh = sig_img.size

    # Centre the signature over cx, place bottom of sig at ~83% height
    sig_paste_x = cx - sw // 2
    sig_paste_y = int(H * 0.835) - sh

    img.paste(sig_img, (sig_paste_x, sig_paste_y), sig_img)

    # ── Draw the horizontal rule ────────────────────────────────────────────
    rule_y  = int(H * 0.840)
    rule_x1 = cx - int(W * 0.10)
    rule_x2 = cx + int(W * 0.10)
    draw.line([(rule_x1, rule_y), (rule_x2, rule_y)], fill=(30, 30, 30, 255), width=max(1, H//400))

    # ── Draw new text ───────────────────────────────────────────────────────
    title_size  = max(12, int(H * 0.022))
    sub_size    = max(10, int(H * 0.018))

    font_bold   = find_font(title_size, bold=True)
    font_normal = find_font(sub_size,   bold=False)

    text_colour      = (20, 20, 20, 255)
    sub_text_colour  = (60, 60, 60, 255)

    # Title line: DR. ADARSH S. J.
    title_y = rule_y + int(H * 0.012)
    bbox_t = draw.textbbox((0, 0), NEW_TITLE, font=font_bold)
    tw = bbox_t[2] - bbox_t[0]
    draw.text((cx - tw // 2, title_y), NEW_TITLE, fill=text_colour, font=font_bold)

    # Role line
    role_y = title_y + int(H * 0.028)
    bbox_r = draw.textbbox((0, 0), NEW_ROLE, font=font_normal)
    rw = bbox_r[2] - bbox_r[0]
    draw.text((cx - rw // 2, role_y), NEW_ROLE, fill=sub_text_colour, font=font_normal)

    # Dept line
    dept_y = role_y + int(H * 0.022)
    bbox_d = draw.textbbox((0, 0), NEW_DEPT, font=font_normal)
    dw = bbox_d[2] - bbox_d[0]
    draw.text((cx - dw // 2, dept_y), NEW_DEPT, fill=sub_text_colour, font=font_normal)

    # ── Save back ───────────────────────────────────────────────────────────
    out = img.convert("RGB")
    out.save(path, "PNG")
    print(f"  OK Patched: {template_filename}")


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not os.path.exists(NEW_SIG_PATH):
        print(f"ERROR: new_signature.png not found at {NEW_SIG_PATH}")
        sys.exit(1)

    print("Patching certificate templates ...\n")
    new_sig = NEW_SIG_PATH

    for tpl in TEMPLATES:
        print(f"  Processing: {tpl}")
        patch_template(tpl, new_sig)

    print("\nAll done!")
