import sys
import math
import tkinter as tk
from tkinter import ttk

# Try to import Pillow for rotated text rendering (recommended)
try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk  # type: ignore
    PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    PIL_AVAILABLE = False
    Image = ImageDraw = ImageFont = ImageTk = None  # type: ignore


# ---------- Display and rotation config ----------
# Physical screen pixels (landscape). The UI will be rendered rotated 270° (i.e., 90° CCW)
PHYS_WIDTH = 1920
PHYS_HEIGHT = 720

# Logical canvas size (portrait). We design the UI in 720x1920 coordinate space
LOG_WIDTH = 720
LOG_HEIGHT = 1920

# Colors and styles
BG_COLOR = "#101114"
SECTION_BG = "#181a1f"
SECTION_BORDER = "#2a2e36"
BTN_BG = "#2d313a"
BTN_BG_HOVER = "#3a3f4a"
BTN_BG_ACTIVE = "#455066"
BTN_TEXT = "#e8eaf0"
TITLE_TEXT = "#9aa5b1"
ACCENT = "#3fa7ff"
DIVIDER = "#404754"

FONT_FALLBACK = ("DejaVu Sans", 16)


class RotatedCanvas:
    """
    A wrapper that maps logical portrait coordinates (LOG_WIDTH x LOG_HEIGHT)
    to the physical landscape canvas (PHYS_WIDTH x PHYS_HEIGHT) with a 270° rotation
    (equivalently 90° counter-clockwise).

    Mapping used:
      x_phys = y_log
      y_phys = LOG_WIDTH - x_log
    """

    def __init__(self, root: tk.Tk, phys_w: int, phys_h: int):
        self.root = root
        self.canvas = tk.Canvas(root, width=phys_w, height=phys_h, highlightthickness=0, bg=BG_COLOR)
        self.canvas.pack(fill="both", expand=True)
        # Keep references to PhotoImage objects to avoid GC
        self._images = []

    # ---- coordinate transforms ----
    @staticmethod
    def to_physical(x_log: float, y_log: float):
        x_phys = y_log
        y_phys = LOG_WIDTH - x_log
        return x_phys, y_phys

    @staticmethod
    def to_logical(x_phys: float, y_phys: float):
        # Inverse of mapping above
        y_log = x_phys
        x_log = LOG_WIDTH - y_phys
        return x_log, y_log

    # ---- drawing helpers (rect, oval, line, image) ----
    def rect(self, x1, y1, x2, y2, **kwargs):
        X1, Y1 = self.to_physical(x1, y1)
        X2, Y2 = self.to_physical(x2, y2)
        # Normalize in physical space to ensure proper ordering
        x_min, x_max = min(X1, X2), max(X1, X2)
        y_min, y_max = min(Y1, Y2), max(Y1, Y2)
        return self.canvas.create_rectangle(x_min, y_min, x_max, y_max, **kwargs)

    def oval(self, x1, y1, x2, y2, **kwargs):
        X1, Y1 = self.to_physical(x1, y1)
        X2, Y2 = self.to_physical(x2, y2)
        x_min, x_max = min(X1, X2), max(X1, X2)
        y_min, y_max = min(Y1, Y2), max(Y1, Y2)
        return self.canvas.create_oval(x_min, y_min, x_max, y_max, **kwargs)

    def line(self, x1, y1, x2, y2, **kwargs):
        X1, Y1 = self.to_physical(x1, y1)
        X2, Y2 = self.to_physical(x2, y2)
        return self.canvas.create_line(X1, Y1, X2, Y2, **kwargs)

    def image(self, x, y, pil_image, anchor="center"):
        # Convert PIL image to PhotoImage and place it
        photo = ImageTk.PhotoImage(pil_image)
        self._images.append(photo)
        X, Y = self.to_physical(x, y)
        return self.canvas.create_image(X, Y, image=photo, anchor=anchor)


# ---------- Text rendering (rotated 90° CCW) ----------

def draw_text(rot: RotatedCanvas, x, y, text: str, font_size=18, color=BTN_TEXT, anchor="center", bold=False):
    """
    Draw text rotated 90° CCW so that it visually matches the overall 270°-rotated UI.
    Coordinates x, y are in logical space (portrait).
    """
    if not PIL_AVAILABLE:
        # Fallback: plain canvas text (won't be rotated). Still usable if Pillow is not installed.
        X, Y = RotatedCanvas.to_physical(x, y)
        return rot.canvas.create_text(X, Y, text=text, fill=color, anchor=anchor, font=(FONT_FALLBACK[0], font_size, "bold" if bold else "normal"))

    # Create text image with transparent background
    font = _load_font(font_size, bold=bold)
    text_padding = 4
    dummy = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(dummy)
    w, h = d.textbbox((0, 0), text, font=font)[2:]
    img = Image.new("RGBA", (w + text_padding * 2, h + text_padding * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((text_padding, text_padding), text, font=font, fill=color)

    # Rotate 90° CCW so it matches the global rotation
    img = img.rotate(90, expand=True)

    return rot.image(x, y, img, anchor=anchor)


def _load_font(size: int, bold=False):
    if not PIL_AVAILABLE:
        return None
    # Try common fonts typically available on Raspberry Pi OS
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


# ---------- Interactive primitives ----------

class HitRegion:
    def __init__(self, name: str, bbox: tuple):
        self.name = name
        self.bbox = bbox  # (x1, y1, x2, y2) in logical coords

    def contains(self, x, y) -> bool:
        x1, y1, x2, y2 = self.bbox
        return x1 <= x <= x2 and y1 <= y <= y2


class RectButton:
    def __init__(self, rot: RotatedCanvas, bbox, label: str, callback):
        self.rot = rot
        self.bbox = bbox
        self.label = label
        self.callback = callback
        self._items = []

    def draw(self):
        x1, y1, x2, y2 = self.bbox
        # Button rectangle
        rect_id = self.rot.rect(x1, y1, x2, y2, fill=BTN_BG, outline=DIVIDER, width=2)
        # Label center
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        draw_text(self.rot, cx, cy, self.label, font_size=20, color=BTN_TEXT, bold=True)
        self._items.append(rect_id)

    def handle_click(self, x, y):
        x1, y1, x2, y2 = self.bbox
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.callback(self.label)
            return True
        return False


class DualVerticalButton:
    """
    A tall button where the top half is "Up" and the bottom half is "Down".
    """

    def __init__(self, rot: RotatedCanvas, bbox, label: str, callback_up, callback_down):
        self.rot = rot
        self.bbox = bbox
        self.label = label
        self.callback_up = callback_up
        self.callback_down = callback_down
        self._items = []

    def draw(self):
        x1, y1, x2, y2 = self.bbox
        mid_y = (y1 + y2) / 2
        # Outer button
        rect_id = self.rot.rect(x1, y1, x2, y2, fill=BTN_BG, outline=DIVIDER, width=2)
        # Divider
        self.rot.line(x1, mid_y, x2, mid_y, fill=DIVIDER, width=2)
        # Up/Down labels
        draw_text(self.rot, (x1 + x2) / 2, (y1 + mid_y) / 2, "Up", font_size=18, color=BTN_TEXT)
        draw_text(self.rot, (x1 + x2) / 2, (mid_y + y2) / 2, "Down", font_size=18, color=BTN_TEXT)
        self._items.append(rect_id)

    def handle_click(self, x, y):
        x1, y1, x2, y2 = self.bbox
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            return False
        mid_y = (y1 + y2) / 2
        if y < mid_y:
            self.callback_up(self.label)
        else:
            self.callback_down(self.label)
        return True


class DPadCircle:
    """
    A circular control with 5 regions: center, up, down, left, right.
    """

    def __init__(self, rot: RotatedCanvas, center, inner_radius, outer_radius, callback):
        self.rot = rot
        self.cx, self.cy = center
        self.r0 = inner_radius
        self.r1 = outer_radius
        self.callback = callback

    def draw(self):
        # Outer circle (approximate with oval)
        self.rot.rect(self.cx - self.r1, self.cy - self.r1, self.cx + self.r1, self.cy + self.r1,
                      outline=DIVIDER, width=3)
        # Inner circle
        self.rot.rect(self.cx - self.r0, self.cy - self.r0, self.cx + self.r0, self.cy + self.r0,
                      outline=ACCENT, width=3)
        # Direction hints (arrows)
        draw_text(self.rot, self.cx, self.cy - (self.r0 + self.r1) / 2, "▲", font_size=22, color=BTN_TEXT)
        draw_text(self.rot, self.cx, self.cy + (self.r0 + self.r1) / 2, "▼", font_size=22, color=BTN_TEXT)
        draw_text(self.rot, self.cx - (self.r0 + self.r1) / 2, self.cy, "◀", font_size=22, color=BTN_TEXT)
        draw_text(self.rot, self.cx + (self.r0 + self.r1) / 2, self.cy, "▶", font_size=22, color=BTN_TEXT)
        draw_text(self.rot, self.cx, self.cy, "OK", font_size=18, color=ACCENT, bold=True)

    def handle_click(self, x, y):
        dx = x - self.cx
        dy = y - self.cy
        r = math.hypot(dx, dy)
        if r <= self.r0:
            self.callback("center")
            return True
        if r > self.r1:
            return False
        # Determine direction by dominant axis
        if abs(dx) > abs(dy):
            self.callback("right" if dx > 0 else "left")
        else:
            self.callback("down" if dy > 0 else "up")
        return True


# ---------- UI layout ----------

class HomeHubUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.rot = RotatedCanvas(root, PHYS_WIDTH, PHYS_HEIGHT)
        self.controls = []  # list of controls with handle_click

    def build(self):
        margin = 20
        usable_h = LOG_HEIGHT - margin * 4
        section_h = usable_h // 3
        sec_top = margin
        sec_left = margin
        sec_right = LOG_WIDTH - margin

        # ----- Lights Section -----
        lights_rect = (sec_left, sec_top, sec_right, sec_top + section_h)
        self._draw_section_box(*lights_rect, title="Lights")
        self._layout_lights(*lights_rect)
        sec_top += section_h + margin

        # ----- Fan Section -----
        fan_rect = (sec_left, sec_top, sec_right, sec_top + section_h)
        self._draw_section_box(*fan_rect, title="Fan")
        self._layout_fan(*fan_rect)
        sec_top += section_h + margin

        # ----- TV Section -----
        tv_rect = (sec_left, sec_top, sec_right, sec_top + section_h)
        self._draw_section_box(*tv_rect, title="TV")
        self._layout_tv(*tv_rect)

        # Bind click handling (physical coordinates -> logical -> dispatch)
        self.rot.canvas.bind("<Button-1>", self._on_click)

    def _draw_section_box(self, x1, y1, x2, y2, title: str):
        # Background box
        self.rot.rect(x1, y1, x2, y2, fill=SECTION_BG, outline=SECTION_BORDER, width=3)
        # Title
        draw_text(self.rot, x1 + 14, y1 + 24, title, font_size=22, color=TITLE_TEXT, anchor="w", bold=True)
        # Divider line under title
        self.rot.line(x1 + 10, y1 + 40, x2 - 10, y1 + 40, fill=DIVIDER, width=2)

    # ----- Layouts per section -----
    def _layout_lights(self, x1, y1, x2, y2):
        inner_margin = 16
        top = y1 + 50
        left = x1 + inner_margin
        right = x2 - inner_margin
        width = right - left

        row_gap = 14
        btn_h = 120

        # Row 1: 3 buttons across evenly
        cols = 3
        gap = 12
        btn_w = (width - gap * (cols - 1)) / cols
        row1_top = top
        row1_bottom = row1_top + btn_h
        labels1 = ["L1", "L2", "L3"]
        for i in range(cols):
            bx1 = left + i * (btn_w + gap)
            bx2 = bx1 + btn_w
            b = RectButton(self.rot, (bx1, row1_top, bx2, row1_bottom), labels1[i], self._on_light_button)
            b.draw()
            self.controls.append(b)

        # Row 2: 2 buttons across evenly, take up the width
        cols2 = 2
        btn_w2 = (width - gap * (cols2 - 1)) / cols2
        row2_top = row1_bottom + row_gap
        row2_bottom = row2_top + btn_h
        labels2 = ["L4", "L5"]
        for i in range(cols2):
            bx1 = left + i * (btn_w2 + gap)
            bx2 = bx1 + btn_w2
            b = RectButton(self.rot, (bx1, row2_top, bx2, row2_bottom), labels2[i], self._on_light_button)
            b.draw()
            self.controls.append(b)

    def _layout_fan(self, x1, y1, x2, y2):
        inner_margin = 16
        top = y1 + 50
        left = x1 + inner_margin
        right = x2 - inner_margin
        width = right - left

        # Row 1: 4 buttons across
        gap = 12
        btn_h = 110
        cols = 4
        btn_w = (width - gap * (cols - 1)) / cols
        row1_top = top
        row1_bottom = row1_top + btn_h
        labels = ["F1", "F2", "F3", "F4"]
        for i in range(cols):
            bx1 = left + i * (btn_w + gap)
            bx2 = bx1 + btn_w
            b = RectButton(self.rot, (bx1, row1_top, bx2, row1_bottom), labels[i], self._on_fan_button)
            b.draw()
            self.controls.append(b)

        # Row 2: Two tall DualVerticalButton controls at left and right
        row2_top = row1_bottom + 16
        row2_bottom = y2 - inner_margin
        tall_w = 110

        # Left dual (Temp) with label to its right
        left_dual_bbox = (left, row2_top, left + tall_w, row2_bottom)
        left_dual = DualVerticalButton(self.rot, left_dual_bbox, "Temp", self._on_temp_up, self._on_temp_down)
        left_dual.draw()
        self.controls.append(left_dual)
        # Label "Temp" to the right of it, centered vertically
        draw_text(self.rot, left + tall_w + 12, (row2_top + row2_bottom) / 2, "Temp", font_size=20, color=TITLE_TEXT, anchor="w", bold=True)

        # Right dual (Fan) with label to its left
        right_dual_bbox = (right - tall_w, row2_top, right, row2_bottom)
        right_dual = DualVerticalButton(self.rot, right_dual_bbox, "Fan", self._on_fan_up, self._on_fan_down)
        right_dual.draw()
        self.controls.append(right_dual)
        # Label to the left
        draw_text(self.rot, right - tall_w - 12, (row2_top + row2_bottom) / 2, "Fan", font_size=20, color=TITLE_TEXT, anchor="e", bold=True)

    def _layout_tv(self, x1, y1, x2, y2):
        inner_margin = 16
        top = y1 + 50
        left = x1 + inner_margin
        right = x2 - inner_margin
        bottom = y2 - inner_margin
        width = right - left
        height = bottom - top

        # Left column: 3 buttons stacked
        col_w = width * 0.25
        gap = 12
        btn_h = (height - gap * 2) / 3
        labels_left = ["TV1", "TV2", "TV3"]
        for i in range(3):
            bx1 = left
            bx2 = left + col_w
            by1 = top + i * (btn_h + gap)
            by2 = by1 + btn_h
            b = RectButton(self.rot, (bx1, by1, bx2, by2), labels_left[i], self._on_tv_button)
            b.draw()
            self.controls.append(b)

        # Right side: one button then dual below it
        right_col_w = col_w
        rx2 = right
        rx1 = right - right_col_w
        top_btn_h = btn_h
        top_btn = RectButton(self.rot, (rx1, top, rx2, top + top_btn_h), "AUX", self._on_tv_button)
        top_btn.draw()
        self.controls.append(top_btn)

        dual_bbox = (rx1, top + top_btn_h + gap, rx2, top + top_btn_h + gap + (btn_h))
        # Make it tall by extending down another btn_h
        dual_bbox = (rx1, top + top_btn_h + gap, rx2, bottom)
        tv_dual = DualVerticalButton(self.rot, dual_bbox, "Chan", self._on_tv_up, self._on_tv_down)
        tv_dual.draw()
        self.controls.append(tv_dual)

        # Middle D-Pad
        mid_cx = left + col_w + (width - col_w - right_col_w) / 2
        mid_cy = top + height / 2
        dpad = DPadCircle(self.rot, (mid_cx, mid_cy), inner_radius=45, outer_radius=115, callback=self._on_dpad)
        dpad.draw()
        self.controls.append(dpad)

    # ----- Event dispatch -----
    def _on_click(self, event):
        # Physical -> logical
        x_log, y_log = RotatedCanvas.to_logical(event.x, event.y)
        # Dispatch to controls in reverse order so later drawn controls get priority
        for ctrl in reversed(self.controls):
            try:
                if ctrl.handle_click(x_log, y_log):
                    break
            except AttributeError:
                # If a control doesn't implement handle_click, skip
                continue

    # ----- Callbacks -----
    @staticmethod
    def _log(action: str):
        print(action)
        sys.stdout.flush()

    def _on_light_button(self, label):
        self._log(f"Lights: {label}")

    def _on_fan_button(self, label):
        self._log(f"Fan preset: {label}")

    def _on_temp_up(self, _):
        self._log("Temp Up")

    def _on_temp_down(self, _):
        self._log("Temp Down")

    def _on_fan_up(self, _):
        self._log("Fan Up")

    def _on_fan_down(self, _):
        self._log("Fan Down")

    def _on_tv_button(self, label):
        self._log(f"TV: {label}")

    def _on_tv_up(self, _):
        self._log("TV Up")

    def _on_tv_down(self, _):
        self._log("TV Down")

    def _on_dpad(self, direction):
        self._log(f"DPad: {direction}")


# ---------- App bootstrap (kiosk) ----------

def setup_kiosk_window(root: tk.Tk):
    root.title("Home Assistant Hub")
    # Fullscreen kiosk
    try:
        root.attributes("-fullscreen", True)
        root.attributes("-topmost", True)
    except Exception:
        pass
    # Explicit geometry as a hint (especially on Raspberry Pi)
    try:
        root.geometry(f"{PHYS_WIDTH}x{PHYS_HEIGHT}+0+0")
    except Exception:
        pass
    # Hide cursor (useful for touch displays)
    root.configure(cursor="none")

    # Exit shortcuts for development
    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<Control-q>", lambda e: root.destroy())


def main():
    root = tk.Tk()
    setup_kiosk_window(root)

    ui = HomeHubUI(root)
    ui.build()

    # Background fill
    ui.rot.canvas.configure(bg=BG_COLOR)

    root.mainloop()


if __name__ == "__main__":
    main()
