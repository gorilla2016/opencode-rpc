#!/usr/bin/env python3
"""Generate opencode-rpc mascot GIFs (a little terminal creature) and upload them."""
import io
import math
import os
import urllib.request
import uuid

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUT, exist_ok=True)

CYAN = (96, 205, 255, 255)
CYAN_DIM = (60, 140, 190, 255)
DARK = (16, 18, 26, 255)
SCREEN = (8, 10, 16, 255)
WHITE = (225, 245, 255, 255)
RED = (255, 84, 84, 255)
GREEN = (96, 230, 150, 255)


def new_frame():
    return Image.new("RGBA", (128, 128), (0, 0, 0, 0))


def draw_body(d, outline=CYAN, fill=DARK):
    d.rounded_rectangle([28, 34, 100, 104], radius=16, fill=fill, outline=outline, width=3)
    d.rounded_rectangle([36, 42, 92, 88], radius=7, fill=SCREEN, outline=outline, width=1)


def draw_antenna(d, glow=1.0):
    d.line([(64, 22), (64, 34)], fill=CYAN, width=3)
    r = 3 + int(2 * glow)
    d.ellipse([64 - r, 18 - r, 64 + r, 18 + r], fill=CYAN if glow > 0.5 else CYAN_DIM)


def draw_eyes(d, mode="open", color=CYAN, shift=0):
    for x in (70, 82):
        if mode == "open":
            d.rectangle([x, 50 + shift, x + 6, 56 + shift], fill=color)
        elif mode == "blink":
            d.rectangle([x, 53, x + 6, 55], fill=color)
        elif mode == "up":
            d.rectangle([x, 48 + shift, x + 6, 54 + shift], fill=color)
        elif mode == "x":
            d.line([(x, 50), (x + 6, 56)], fill=color, width=2)
            d.line([(x + 6, 50), (x, 56)], fill=color, width=2)
        elif mode == "happy":
            d.line([(x, 54), (x + 3, 50), (x + 6, 54)], fill=color, width=2)


def draw_prompt(d, cursor=True, color=CYAN):
    d.line([(44, 56), (54, 66), (44, 76)], fill=color, width=4)
    if cursor:
        d.rectangle([58, 72, 72, 76], fill=color)


def draw_arms(d, dy_left=0, dy_right=0, color=CYAN_DIM):
    d.rounded_rectangle([18, 60 + dy_left, 28, 72 + dy_left], radius=4, fill=color)
    d.rounded_rectangle([100, 60 + dy_right, 110, 72 + dy_right], radius=4, fill=color)


def draw_feet(d, color=CYAN_DIM):
    d.rounded_rectangle([44, 104, 58, 112], radius=3, fill=color)
    d.rounded_rectangle([70, 104, 84, 112], radius=3, fill=color)


def frames_idle():
    out = []
    for i in range(16):
        im = new_frame(); d = ImageDraw.Draw(im)
        draw_body(d); draw_antenna(d, 0.5 + 0.5 * math.sin(i / 16 * 2 * math.pi))
        eyes = "blink" if i in (7, 8) else "open"
        draw_eyes(d, eyes)
        draw_prompt(d, cursor=(i % 8) < 4)
        draw_arms(d); draw_feet(d)
        out.append(im)
    return out, 90


def frames_working():
    out = []
    for i in range(12):
        im = new_frame(); d = ImageDraw.Draw(im)
        draw_body(d); draw_antenna(d, 1.0)
        draw_eyes(d, "open")
        draw_prompt(d, cursor=(i % 2) == 0)
        lift = 4 if (i // 2) % 2 == 0 else 0
        draw_arms(d, -lift, lift)
        draw_feet(d)
        out.append(im)
    return out, 70


def frames_thinking():
    out = []
    for i in range(16):
        im = new_frame(); d = ImageDraw.Draw(im)
        draw_body(d); draw_antenna(d, 0.5 + 0.5 * math.sin(i / 16 * 2 * math.pi))
        draw_eyes(d, "up", shift=-2)
        draw_prompt(d, cursor=False)
        draw_arms(d); draw_feet(d)
        for k in range(3):
            on = (i // 2) % 3 == k
            x = 50 + k * 12
            y = 26 - (2 if on else 0)
            r = 3 if on else 2
            d.ellipse([x - r, y - r, x + r, y + r], fill=CYAN if on else CYAN_DIM)
        out.append(im)
    return out, 90


def frames_error():
    out = []
    for i in range(8):
        im = new_frame(); d = ImageDraw.Draw(im)
        dx = 2 if i % 2 == 0 else -2
        body = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        bd = ImageDraw.Draw(body)
        draw_body(bd, outline=RED)
        draw_antenna(bd, 1.0)
        draw_eyes(bd, "x", color=RED)
        draw_prompt(bd, cursor=True, color=RED)
        draw_arms(bd, color=RED); draw_feet(bd, color=RED)
        im.alpha_composite(body, (dx, 0))
        out.append(im)
    return out, 130


def frames_done():
    out = []
    for i in range(14):
        im = new_frame(); d = ImageDraw.Draw(im)
        draw_body(d, outline=GREEN); draw_antenna(d, 1.0)
        draw_eyes(d, "happy", color=GREEN)
        draw_prompt(d, cursor=(i % 4) < 2, color=GREEN)
        draw_arms(d, color=GREEN); draw_feet(d, color=GREEN)
        for k in range(4):
            ang = (i / 14 * 2 * math.pi) + k * math.pi / 2
            x = 64 + int(48 * math.cos(ang)); y = 64 + int(48 * math.sin(ang))
            d.line([(x - 2, y), (x + 2, y)], fill=GREEN, width=2)
            d.line([(x, y - 2), (x, y + 2)], fill=GREEN, width=2)
        out.append(im)
    return out, 80


def to_p_frames(frames):
    pf = []
    for im in frames:
        q = im.convert("P", palette=Image.ADAPTIVE, colors=255)
        alpha = im.split()[3]
        q.paste(255, mask=alpha.point(lambda a: 255 if a < 128 else 0))
        q.info["transparency"] = 255
        pf.append(q)
    return pf


def save_gif(name, frames, duration):
    pf = to_p_frames(frames)
    path = os.path.join(OUT, name)
    pf[0].save(path, save_all=True, append_images=pf[1:], duration=duration,
               loop=0, transparency=255, disposal=2, optimize=True)
    return path


def upload(path):
    data = open(path, "rb").read()
    boundary = "----b" + uuid.uuid4().hex
    body = b""

    def part(hdr, val=b""):
        return (f"--{boundary}\r\n{hdr}\r\n\r\n").encode() + val + b"\r\n"

    body += part('Content-Disposition: form-data; name="reqtype"', b"fileupload")
    body += part(f'Content-Disposition: form-data; name="fileToUpload"; filename="{os.path.basename(path)}"\r\nContent-Type: image/gif', data)
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request("https://catbox.moe/user/api.php", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "opencode-rpc/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode().strip()


def main():
    specs = {
        "idle": frames_idle,
        "working": frames_working,
        "thinking": frames_thinking,
        "error": frames_error,
        "done": frames_done,
    }
    urls = {}
    for name, fn in specs.items():
        frames, dur = fn()
        path = save_gif(f"opencode-{name}.gif", frames, dur)
        size = os.path.getsize(path)
        try:
            url = upload(path)
        except Exception as e:
            url = f"UPLOAD_FAILED: {e}"
        urls[name] = url
        print(f"{name:9s} {size//1024:4d}KB  {url}")
    print("\nJSON:")
    import json
    print(json.dumps(urls, indent=2))


if __name__ == "__main__":
    main()
