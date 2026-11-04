"""Design system for Project MANUS AD LUNAM.

Everything visual lives here: the palette, the type scale, the backdrop, and
the reusable widgets the dashboard composes. Tweak the token block at the top
and the whole app follows.

Look: Apple's Liquid Glass language (iOS 26 onward) for the surfaces -- floating
glass capsules, concentric corner radii, frosted glass that samples the scene
behind it -- over Hanoon's dark grey "plexus" backdrop, set on the lunar surface:
a textured moon horizon, a slow Earthrise, and one constellation shaped like
the rover itself.

Performance notes (the camera feeds share this GUI thread):
  * The backdrop is baked into a pixmap once per resize, with a blurred copy that
    glass surfaces sample. No live blur is ever computed.
  * Live elements -- ~60 twinkling stars with mouse parallax, and Earth while it
    rises -- repaint as small rects, and are skipped while covered by glass.
  * Once Earth has risen it is baked into the backdrop and stops costing anything.
  * Nothing here puts a graphics effect over live video.
"""

from __future__ import annotations

import math
import random
import time
import weakref
from collections import deque
from html import escape

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# TOKENS -- the whole look is driven from this block
# ---------------------------------------------------------------------------

# Backdrop: Hanoon's dark grey gradient
BG_TOP = "#0B0C0E"
BG_MID = "#17181B"
BG_BOTTOM = "#26282C"

# Scenery
MOONLIGHT = "#CFE2FF"     # star halos, earthshine
EARTH_SEA = "#2F6FD0"
EARTH_DAY = "#A8D8FF"
EARTH_NIGHT = "#08111F"
REGOLITH_LIT = "#2C2E33"  # lunar surface at the horizon
REGOLITH_MID = "#1B1D21"
REGOLITH_DARK = "#0D0E10"
HORIZON = 0.14            # fraction of the window height the moon occupies
EARTHRISE_DELAY = 1.5     # seconds after launch before Earth starts to rise
EARTHRISE_SECONDS = 90.0  # how long the rise takes
PARALLAX_PX = 8.0         # how far the nearest stars shift with the mouse

INK = "#FFFFFF"

# The single accent. Blue for actions, cyan tint for live data.
ACCENT = "#0A84FF"
ACCENT_LIGHT = "#64D2FF"

# Semantic state colours -- only ever used to mean something
OK = "#30D158"
WARN = "#FFD60A"
ORANGE = "#FF9F0A"
BAD = "#FF453A"
IDLE = "#8E99AD"

# Drive command colours (Hanoon): forward, reverse, stop
CMD_FORWARD = OK
CMD_REVERSE = ORANGE
CMD_STOP = BAD

# Geometry. Radii are concentric: an inner radius is the outer radius minus
# the padding between them, which is what keeps nested glass looking right.
RADIUS_CARD = 28
PAD_CARD = 18
PAD_FEED = 10
RADIUS_VIDEO = RADIUS_CARD - PAD_FEED   # 18
RADIUS_FIELD = 14

# Liquid glass recipe
GLASS_TINT_TOP = 0.10      # white wash over the frosted backdrop
GLASS_TINT_BOTTOM = 0.035
GLASS_SHEEN = 0.07         # specular sheen across the top
GLASS_RIM_TOP = 0.42       # rim light, brightest along the top edge
GLASS_RIM_SIDE = 0.06
GLASS_RIM_BOTTOM = 0.15    # light also catches the lower lip
FROST_DOWNSCALE = 16       # blur strength of the frosted backdrop

# Type stacks. Windows gets the variable Segoe fallback, which is the closest
# match to SF Pro's proportions.
FAMILIES = [
    "SF Pro Display",
    "SF Pro Text",
    "Segoe UI Variable Display",
    "Segoe UI Variable",
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
]
MONO_FAMILIES = [
    "SF Mono",
    "Cascadia Mono",
    "JetBrains Mono",
    "Consolas",
    "Menlo",
    "Courier New",
]

# Readouts: oversized thin numerals over tiny letter-spaced capitals. Qt falls
# back to the lightest weight the font provides (Segoe UI Light on Windows).
NUMERAL_WEIGHT = QFont.Weight.ExtraLight
# The drive command letters: a bold display face. Bahnschrift ships with
# Windows 10+ and has the squared, instrument-panel feel; SF Pro Rounded on Macs.
COMMAND_FAMILIES = [
    "SF Pro Rounded",
    "Bahnschrift",
    "Segoe UI Variable Display",
    "Segoe UI",
    "Arial",
]
MICRO_SIZE = 10
MICRO_SPACING = 1.4

STARFIELD_SEED = 20260713  # fixed, so the sky is the same every launch
PLEXUS_SEED = 7            # Hanoon's dot network layout


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def tint(hex_color: str, alpha: float = 1.0) -> QColor:
    """QColor from a token with an alpha multiplier, for QPainter work."""
    color = QColor(hex_color)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def css(hex_color: str, alpha: float = 1.0) -> str:
    """'rgba(r,g,b,a)' string from a token, for stylesheets."""
    color = QColor(hex_color)
    return f"rgba({color.red()},{color.green()},{color.blue()},{alpha:.3f})"


def app_font(
    size: int,
    weight: QFont.Weight = QFont.Weight.Normal,
    spacing: float = 0.0,
    mono: bool = False,
) -> QFont:
    """A font from the Apple-style stack. Sizes are logical px; Qt scales them."""
    font = QFont()
    font.setFamilies(MONO_FAMILIES if mono else FAMILIES)
    font.setPixelSize(size)
    font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def numeral_font(size: int) -> QFont:
    """Large thin numerals for live readouts."""
    return app_font(size, NUMERAL_WEIGHT)


def micro_font(size: int = MICRO_SIZE) -> QFont:
    """Tiny upper-case caption face."""
    return app_font(size, QFont.Weight.DemiBold, spacing=MICRO_SPACING)


def state_color(state: str) -> str:
    """Map a semantic state name onto its token."""
    return {
        "ok": OK,
        "live": OK,
        "warn": WARN,
        "bad": BAD,
        "idle": IDLE,
        "accent": ACCENT_LIGHT,
    }.get(state, IDLE)


def command_color(command: str) -> str:
    """Hanoon's drive colours: forward green, reverse orange, stop red."""
    command = (command or "S").upper()
    if command.startswith("F"):
        return CMD_FORWARD
    if command.startswith("B"):
        return CMD_REVERSE
    return CMD_STOP


def caption_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Tiny upper-case, letter-spaced caption -- section headers and units."""
    label = QLabel(text.upper(), parent)
    label.setObjectName("caption")
    label.setFont(micro_font())
    return label


def title_label(text: str, parent: QWidget | None = None) -> QLabel:
    """Primary card title, one step up from a caption."""
    label = QLabel(text, parent)
    label.setObjectName("cardTitle")
    label.setFont(app_font(16, QFont.Weight.DemiBold))
    return label


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# vector glyphs -- drawn, so no emoji and no icon font dependency
# ---------------------------------------------------------------------------

def paint_glyph(painter: QPainter, name: str, rect: QRectF, color: QColor,
                width: float = 1.6) -> None:
    """Draw a simple line icon inside `rect`. Unknown names draw nothing."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    size = min(rect.width(), rect.height())
    cx, cy = rect.center().x(), rect.center().y()
    unit = size / 2.0

    if name == "refresh":
        box = QRectF(cx - unit * 0.72, cy - unit * 0.72, unit * 1.44, unit * 1.44)
        painter.drawArc(box, 40 * 16, 285 * 16)
        # arrow head at the open end
        tip = QPointF(cx + unit * 0.55, cy - unit * 0.46)
        head = QPainterPath(tip)
        head.lineTo(tip.x() - unit * 0.42, tip.y() - unit * 0.10)
        head.lineTo(tip.x() - unit * 0.06, tip.y() + unit * 0.40)
        head.closeSubpath()
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(head)

    elif name == "log":
        for index, factor in enumerate((1.0, 0.72, 0.88)):
            y = cy + (index - 1) * unit * 0.62
            painter.drawLine(
                QPointF(cx - unit * 0.78, y),
                QPointF(cx - unit * 0.78 + unit * 1.56 * factor, y),
            )

    elif name == "swap":
        # two opposed arrows: promote / demote a feed
        for sign, y in ((1.0, cy - unit * 0.38), (-1.0, cy + unit * 0.38)):
            tail = cx - sign * unit * 0.72
            tip = cx + sign * unit * 0.72
            painter.drawLine(QPointF(tail, y), QPointF(tip, y))
            head = QPainterPath(QPointF(tip - sign * unit * 0.34, y - unit * 0.30))
            head.lineTo(QPointF(tip, y))
            head.lineTo(QPointF(tip - sign * unit * 0.34, y + unit * 0.30))
            painter.drawPath(head)

    elif name in ("expand", "collapse"):
        # four corner brackets, pointing out (expand) or in (collapse)
        reach, arm = unit * 0.78, unit * 0.40
        inward = name == "collapse"
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                corner = QPointF(cx + sx * (reach - arm if inward else reach),
                                 cy + sy * (reach - arm if inward else reach))
                direction = 1.0 if inward else -1.0
                bracket = QPainterPath(QPointF(corner.x(), corner.y() + direction * sy * arm))
                bracket.lineTo(corner)
                bracket.lineTo(QPointF(corner.x() + direction * sx * arm, corner.y()))
                painter.drawPath(bracket)

    elif name in ("flip-h", "flip-v"):
        if name == "flip-v":
            painter.translate(cx, cy)
            painter.rotate(90)
            painter.translate(-cx, -cy)
        dashed = QPen(color, width)
        dashed.setDashPattern([1.6, 2.0])
        painter.setPen(dashed)
        painter.drawLine(QPointF(cx, cy - unit * 0.84), QPointF(cx, cy + unit * 0.84))
        painter.setPen(QPen(color, width))
        for sign in (-1.0, 1.0):
            path = QPainterPath(QPointF(cx + sign * unit * 0.28, cy - unit * 0.52))
            path.lineTo(QPointF(cx + sign * unit * 0.86, cy))
            path.lineTo(QPointF(cx + sign * unit * 0.28, cy + unit * 0.52))
            painter.drawPath(path)

    elif name == "image":
        box = QRectF(cx - unit * 0.82, cy - unit * 0.66, unit * 1.64, unit * 1.32)
        painter.drawRoundedRect(box, unit * 0.22, unit * 0.22)
        painter.drawEllipse(QPointF(cx - unit * 0.34, cy - unit * 0.22), unit * 0.15, unit * 0.15)
        ridge = QPainterPath(QPointF(cx - unit * 0.70, cy + unit * 0.52))
        ridge.lineTo(QPointF(cx - unit * 0.08, cy - unit * 0.06))
        ridge.lineTo(QPointF(cx + unit * 0.74, cy + unit * 0.52))
        painter.drawPath(ridge)

    elif name == "sources":
        for index in (-1, 0, 1):
            y = cy + index * unit * 0.58
            painter.drawLine(QPointF(cx - unit * 0.80, y), QPointF(cx + unit * 0.80, y))
            painter.setBrush(QBrush(QColor(BG_BOTTOM)))
            knob_x = cx + unit * (0.30 if index == 0 else -0.26 * index)
            painter.drawEllipse(QPointF(knob_x, y), unit * 0.20, unit * 0.20)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    elif name == "arrow-right":
        painter.drawLine(QPointF(cx - unit * 0.70, cy), QPointF(cx + unit * 0.56, cy))
        path = QPainterPath(QPointF(cx + unit * 0.10, cy - unit * 0.46))
        path.lineTo(QPointF(cx + unit * 0.66, cy))
        path.lineTo(QPointF(cx + unit * 0.10, cy + unit * 0.46))
        painter.drawPath(path)

    painter.restore()


# ---------------------------------------------------------------------------
# StarfieldBackground -- the backdrop
# ---------------------------------------------------------------------------

# The rover constellation: star positions in a 1.0 x 0.78 box, and the lines
# between them. Chassis, camera mast, antenna, rocker-bogie and three wheels.
ROVER_STARS = {
    "nose": (0.08, 0.42), "tail": (0.88, 0.42),
    "tail_low": (0.88, 0.56), "nose_low": (0.08, 0.56),
    "mast_base": (0.70, 0.42), "mast_top": (0.70, 0.15),
    "cam_l": (0.60, 0.11), "cam_r": (0.82, 0.11),
    "ant_base": (0.22, 0.42), "ant_top": (0.22, 0.24),
    "pivot_f": (0.30, 0.56), "pivot_r": (0.64, 0.56),
    "wheel_1": (0.14, 0.72), "wheel_2": (0.47, 0.72), "wheel_3": (0.82, 0.72),
}
ROVER_LINES = (
    ("nose", "tail"), ("tail", "tail_low"), ("tail_low", "nose_low"), ("nose_low", "nose"),
    ("mast_base", "mast_top"), ("cam_l", "mast_top"), ("mast_top", "cam_r"),
    ("ant_base", "ant_top"),
    ("wheel_1", "pivot_f"), ("pivot_f", "wheel_2"),
    ("wheel_2", "pivot_r"), ("pivot_r", "wheel_3"),
)
ROVER_WHEELS = ("wheel_1", "wheel_2", "wheel_3")


class StarfieldBackground(QWidget):
    """Backdrop seen from the lunar surface.

    Baked once per resize: Hanoon's grey gradient and plexus dot network, the
    rover constellation, the textured lunar horizon and a vignette, plus a
    blurred copy that glass surfaces sample.

    Live: ~60 twinkling stars that drift slowly and shift with the mouse
    (nearer stars more, so depth reads), and Earth rising over the horizon for
    the first minute and a half, after which it is baked in too.
    """

    LIVE_STARS = 60
    FRAME_MS = 33  # ~30 fps
    STAR_DEPTH = (0.35, 0.65, 1.0)  # parallax share per star tier

    def __init__(self, parent: QWidget | None = None, seed: int = STARFIELD_SEED):
        super().__init__(parent)
        self._seed = seed
        self._sky: QPixmap | None = None
        self._frost: QPixmap | None = None
        self._sky_dpr = 1.0
        self._sky_path = QPainterPath()         # open sky above the horizon
        self._live: list[dict] = []
        self._rects: list[QRect] = []           # last painted rect per live star
        self._sprites: dict[int, QPixmap] = {}  # pre-rendered star per tier
        self._covered: list[QRect] = []
        self._covered_age = 0
        self._phase = 0.0
        self._t0 = time.monotonic()
        self._parallax = QPointF(0.0, 0.0)      # eased, -1..1 on each axis

        # Earthrise: a live sprite until it settles, then baked into the sky.
        self._earth_baked = False
        self._earth_sprite: QPixmap | None = None
        self._earth_rect = QRect()       # sprite (with glow) in our coordinates
        self._earth_disc = QRect()       # the planet itself; stars never cross it

        # Opaque: the sky pixmap covers every pixel, so Qt need not paint under us.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._tick)

    # -- animation gating ---------------------------------------------------
    def set_animating(self, running: bool) -> None:
        """Park the timer whenever the window is hidden or minimised."""
        if running and not self._timer.isActive():
            self._timer.start()
        elif not running and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.set_animating(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.set_animating(False)

    # -- geometry -----------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sky = None  # re-bake lazily on the next paint
        self._frost = None
        self._covered_age = 0  # card geometry changed; re-measure next tick
        self._build_live_stars()

    def _horizon(self, width: float, height: float) -> tuple[QPointF, float]:
        """The moon is a huge circle whose crown peeks above the bottom edge."""
        radius = max(width, height) * 1.35
        crown = height * (1.0 - HORIZON)
        return QPointF(width * 0.40, crown + radius), radius

    def _horizon_y(self, x: float, width: float, height: float) -> float:
        center, radius = self._horizon(width, height)
        dx = min(abs(x - center.x()), radius)
        return center.y() - math.sqrt(radius * radius - dx * dx)

    def _rover_box(self, width: float, height: float) -> QRectF:
        size = min(width, height) * 0.30
        return QRectF(width * 0.05, height * 0.10, size, size * 0.78)

    def _build_live_stars(self) -> None:
        rng = random.Random(self._seed ^ 0x5EED)
        width, height = max(self.width(), 1), max(self.height(), 1)
        # The horizon crown is its highest point; keep drifting stars (plus
        # their parallax travel) in open sky.
        sky_floor = height * (1.0 - HORIZON) - PARALLAX_PX - 8
        self._live = []
        for _ in range(self.LIVE_STARS):
            tier = rng.choice((0, 1, 2))
            self._live.append(
                {
                    "x0": rng.uniform(0, width),
                    "y0": rng.uniform(0, max(sky_floor, 1)),
                    "t": tier,
                    "r": (1.05, 1.45, 1.9)[tier],
                    "a": (0.55, 0.75, 0.95)[tier],
                    # nearer (bigger) stars drift faster -- the parallax cue
                    "vx": (1.4, 3.0, 5.2)[tier] * rng.choice((-1.0, 1.0)) * rng.uniform(0.7, 1.3),
                    "ph": rng.uniform(0.0, math.tau),
                    "tw": rng.uniform(0.7, 1.6),  # twinkle rate
                    "x": 0.0,
                    "y": 0.0,
                }
            )
        self._rects = [QRect() for _ in self._live]

    # -- the baked scene ----------------------------------------------------
    def _ensure_sky(self) -> None:
        if self._sky is None or self._sky.isNull() or self._frost is None:
            self._render_sky()

    def _render_sky(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        width, height = max(self.width(), 1), max(self.height(), 1)
        pixmap = QPixmap(int(width * dpr), int(height * dpr))
        pixmap.fill(QColor(BG_TOP))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(dpr, dpr)  # draw in logical coordinates throughout
        rect = QRectF(0, 0, width, height)

        # 1. Hanoon's grey gradient
        base = QLinearGradient(0, 0, width, height * 0.35)
        base.setColorAt(0.0, QColor(BG_TOP))
        base.setColorAt(0.55, QColor(BG_MID))
        base.setColorAt(1.0, QColor(BG_BOTTOM))
        painter.fillRect(rect, QBrush(base))

        # 2. the plexus network, leaving room for the rover figure
        rover_box = self._rover_box(width, height)
        self._paint_plexus(painter, width, height, rover_box.adjusted(-24, -24, 24, 24))

        # 3. the easter egg: a constellation shaped like the rover
        self._paint_rover_constellation(painter, rover_box)

        # 4. Earth, once it has finished rising
        self._render_earth_sprite(dpr, width, height)
        if self._earth_baked and self._earth_sprite is not None:
            center, _ = self._earth_geometry(1.0, width, height)
            half = self._earth_sprite.width() / dpr / 2.0
            painter.drawPixmap(QPointF(center.x() - half, center.y() - half), self._earth_sprite)

        # 5. the lunar horizon, drawn last so it occludes everything behind it
        self._paint_horizon(painter, width, height, random.Random(self._seed))

        # 6. vignette to settle the edges
        vignette = QRadialGradient(QPointF(width * 0.5, height * 0.42), max(width, height) * 0.80)
        vignette.setColorAt(0.0, tint("#000000", 0.0))
        vignette.setColorAt(0.62, tint("#000000", 0.08))
        vignette.setColorAt(1.0, tint("#000000", 0.40))
        painter.fillRect(rect, QBrush(vignette))
        painter.end()

        center, radius = self._horizon(width, height)
        moon = QPainterPath()
        moon.addEllipse(center, radius, radius)
        open_sky = QPainterPath()
        open_sky.addRect(rect)
        self._sky_path = open_sky.subtracted(moon)

        self._sky = pixmap
        self._sky_dpr = dpr
        self._frost = self._blur(pixmap)
        self._render_sprites(dpr)

    @staticmethod
    def _blur(pixmap: QPixmap) -> QPixmap:
        """Cheap frosted copy: shrink in two smooth steps, then scale back up."""
        width, height = pixmap.width(), pixmap.height()
        smooth = Qt.TransformationMode.SmoothTransformation
        ignore = Qt.AspectRatioMode.IgnoreAspectRatio
        half = max(1, FROST_DOWNSCALE // 4)
        step = pixmap.scaled(max(1, width // half), max(1, height // half), ignore, smooth)
        tiny = step.scaled(max(1, width // FROST_DOWNSCALE), max(1, height // FROST_DOWNSCALE),
                           ignore, smooth)
        return tiny.scaled(width, height, ignore, smooth)

    @staticmethod
    def _paint_plexus(painter: QPainter, width: int, height: int, keep_clear: QRectF) -> None:
        """Hanoon's dot network: a jittered grid with gaps, each dot joined to its
        nearest neighbours by thin lines. Seeded, so it is stable between runs."""
        rng = random.Random(PLEXUS_SEED)
        cols, rows = 12, 8
        points = []
        for row in range(rows):
            for col in range(cols):
                if rng.random() < 0.18:
                    continue
                nx = (col + 0.1 + rng.random() * 0.8) / cols
                ny = (row + 0.1 + rng.random() * 0.8) / rows
                brightness = rng.random()
                point = (nx * width, ny * height, brightness)
                if not keep_clear.contains(QPointF(point[0], point[1])):
                    points.append(point)
        if not points:
            return

        spacing = math.sqrt(width * height / len(points))
        limit = spacing * 1.55
        links = {}
        for i, (x1, y1, _) in enumerate(points):
            nearest = sorted(
                ((x1 - x2) ** 2 + (y1 - y2) ** 2, j)
                for j, (x2, y2, _) in enumerate(points)
                if j != i
            )[:3]
            for dist_sq, j in nearest:
                if dist_sq <= limit * limit:
                    links[(min(i, j), max(i, j))] = math.sqrt(dist_sq)

        for (i, j), dist in links.items():
            closeness = 1.0 - dist / limit
            painter.setPen(QPen(QColor(255, 255, 255, int(24 + 60 * closeness)), 0.8))
            painter.drawLine(QPointF(points[i][0], points[i][1]), QPointF(points[j][0], points[j][1]))

        painter.setPen(Qt.PenStyle.NoPen)
        for x, y, brightness in points:
            painter.setBrush(QBrush(QColor(255, 255, 255, int(150 + 100 * brightness))))
            radius = 1.0 + brightness * 1.1
            painter.drawEllipse(QPointF(x, y), radius, radius)

    @staticmethod
    def _paint_rover_constellation(painter: QPainter, box: QRectF) -> None:
        """One figure that means something: the rover, drawn in stars."""
        def at(name: str) -> QPointF:
            nx, ny = ROVER_STARS[name]
            return QPointF(box.left() + nx * box.width(), box.top() + ny * box.width())

        line = QPen(tint(MOONLIGHT, 0.30), 1.0)
        line.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(line)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in ROVER_LINES:
            painter.drawLine(at(a), at(b))

        # wheels as faint rings around their stars
        wheel_radius = box.width() * 0.06
        painter.setPen(QPen(tint(MOONLIGHT, 0.22), 1.0))
        for name in ROVER_WHEELS:
            painter.drawEllipse(at(name), wheel_radius, wheel_radius)
        # a small dish on the antenna
        dish = at("ant_top")
        painter.drawArc(QRectF(dish.x() - 7, dish.y() - 9, 14, 10), 200 * 16, 140 * 16)

        painter.setPen(Qt.PenStyle.NoPen)
        for name in ROVER_STARS:
            point = at(name)
            bright = name in ("mast_top", "wheel_2", "nose")
            painter.setBrush(QBrush(tint(MOONLIGHT, 0.16)))
            painter.drawEllipse(point, 4.2 if bright else 3.2, 4.2 if bright else 3.2)
            painter.setBrush(QBrush(tint(INK, 0.95 if bright else 0.80)))
            painter.drawEllipse(point, 1.9 if bright else 1.4, 1.9 if bright else 1.4)

    def _paint_horizon(self, painter: QPainter, width: int, height: int,
                       rng: random.Random) -> None:
        """The lunar limb: dark, low-contrast regolith with maria, grain and a
        few faint foreshortened craters, and earthshine catching the edge."""
        center, radius = self._horizon(width, height)
        crown = height * (1.0 - HORIZON)
        surface = QPainterPath()
        surface.addEllipse(center, radius, radius)

        ground = QLinearGradient(0, crown, 0, height)
        ground.setColorAt(0.0, QColor(REGOLITH_LIT))
        ground.setColorAt(0.40, QColor(REGOLITH_MID))
        ground.setColorAt(1.0, QColor(REGOLITH_DARK))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(ground))
        painter.drawPath(surface)

        painter.save()
        painter.setClipPath(surface)

        # maria and highlands: broad soft patches, squashed by perspective
        for _ in range(26):
            x = rng.uniform(-0.05, 1.05) * width
            top = self._horizon_y(x, width, height)
            y = rng.uniform(top, height)
            rx = rng.uniform(0.05, 0.16) * width
            squash = rng.uniform(0.14, 0.28)
            dark = rng.random() < 0.6
            patch = QRadialGradient(QPointF(0, 0), rx)
            token, alpha = ("#000000", rng.uniform(0.10, 0.22)) if dark else (INK, rng.uniform(0.018, 0.04))
            patch.setColorAt(0.0, tint(token, alpha))
            patch.setColorAt(1.0, tint(token, 0.0))
            painter.save()
            painter.translate(x, y)
            painter.scale(1.0, squash)
            painter.setBrush(QBrush(patch))
            painter.drawEllipse(QPointF(0, 0), rx, rx)
            painter.restore()

        # fine regolith grain
        for _ in range(int(width * 0.9)):
            x = rng.uniform(0, width)
            y = rng.uniform(self._horizon_y(x, width, height), height)
            painter.setBrush(QBrush(tint(INK if rng.random() < 0.55 else "#000000",
                                         rng.uniform(0.015, 0.05))))
            dot = rng.uniform(0.5, 0.9)
            painter.drawEllipse(QPointF(x, y), dot, dot)

        # a few faint craters: shadowed bowl, lit far wall, dark near lip
        for _ in range(9):
            x = rng.uniform(0.04, 0.96) * width
            top = self._horizon_y(x, width, height)
            depth = rng.uniform(0.08, 1.0)
            y = top + 6 + depth * (height - top) * 0.78
            rx = 4 + depth * rng.uniform(12, 30)
            ry = rx * (0.20 + 0.14 * depth)
            bowl = QRadialGradient(QPointF(x + rx * 0.15, y - ry * 0.25), rx)
            bowl.setColorAt(0.0, tint("#000000", 0.24))
            bowl.setColorAt(1.0, tint("#000000", 0.03))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bowl))
            painter.drawEllipse(QPointF(x, y), rx, ry)
            box = QRectF(x - rx, y - ry, rx * 2, ry * 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(tint(INK, 0.08), 1.0))
            painter.drawArc(box, 200 * 16, 140 * 16)   # far wall catches the light
            painter.setPen(QPen(tint("#000000", 0.20), 1.0))
            painter.drawArc(box, 20 * 16, 140 * 16)    # near lip in shadow
        painter.restore()

        # earthshine catching the limb, brightest under Earth
        rim = QLinearGradient(0, 0, width, 0)
        rim.setColorAt(0.0, tint(MOONLIGHT, 0.04))
        rim.setColorAt(0.80, tint(MOONLIGHT, 0.30))
        rim.setColorAt(1.0, tint(MOONLIGHT, 0.12))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QBrush(rim), 1.2))
        painter.drawPath(surface)
        painter.setPen(QPen(QBrush(rim), 7.0))
        painter.setOpacity(0.10)
        painter.drawPath(surface)
        painter.setOpacity(1.0)

    # -- Earth ----------------------------------------------------------------
    def _earth_geometry(self, progress: float, width: float, height: float) -> tuple[QPointF, float]:
        """Earth climbs from below the limb to just above it."""
        radius = max(13.0, min(width, height) * 0.034)
        x = width * 0.80
        horizon = self._horizon_y(x, width, height)
        start = horizon + radius * 1.4
        rest = horizon - radius * 2.8
        return QPointF(x, start + (rest - start) * smoothstep(progress)), radius

    def _render_earth_sprite(self, dpr: float, width: int, height: int) -> None:
        """Earth as a lit crescent with a thin atmospheric halo, pre-rendered."""
        _, radius = self._earth_geometry(0.0, width, height)
        half = radius * 4.2 + 2.0
        side = int(math.ceil(half * 2))
        sprite = QPixmap(int(math.ceil(side * dpr)), int(math.ceil(side * dpr)))
        sprite.setDevicePixelRatio(dpr)
        sprite.fill(Qt.GlobalColor.transparent)
        painter = QPainter(sprite)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(side / 2.0, side / 2.0)

        glow = QRadialGradient(center, radius * 4.2)
        glow.setColorAt(0.0, tint(ACCENT_LIGHT, 0.13))
        glow.setColorAt(0.35, tint(ACCENT_LIGHT, 0.04))
        glow.setColorAt(1.0, tint(ACCENT_LIGHT, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, radius * 4.2, radius * 4.2)

        disc = QPainterPath()
        disc.addEllipse(center, radius, radius)
        painter.setBrush(QBrush(QColor(EARTH_NIGHT)))
        painter.drawPath(disc)
        # sunlight from the upper right; the night side faces the moon
        shadow = QPainterPath()
        shadow.addEllipse(QPointF(center.x() - radius * 0.52, center.y() + radius * 0.34),
                          radius * 1.02, radius * 1.02)
        day = QLinearGradient(center.x() + radius, center.y() - radius, center.x(), center.y())
        day.setColorAt(0.0, QColor(EARTH_DAY))
        day.setColorAt(1.0, QColor(EARTH_SEA))
        painter.setBrush(QBrush(day))
        painter.drawPath(disc.subtracted(shadow))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tint(ACCENT_LIGHT, 0.30), 1.0))
        painter.drawPath(disc)
        painter.end()
        self._earth_sprite = sprite

    def _advance_earthrise(self, elapsed: float, width: int, height: int) -> None:
        if self._earth_baked or self._earth_sprite is None:
            return
        progress = (elapsed - EARTHRISE_DELAY) / EARTHRISE_SECONDS
        if progress >= 1.0:
            # Settled: bake Earth into the sky (and the frost the glass samples),
            # then it costs nothing per frame.
            self._earth_baked = True
            self._render_sky()
            self.update()
            return
        center, radius = self._earth_geometry(max(progress, 0.0), width, height)
        half = int(math.ceil(self._earth_sprite.width() / self._sky_dpr / 2.0))
        rect = QRect(int(center.x()) - half, int(center.y()) - half, half * 2, half * 2)
        if rect == self._earth_rect:
            return
        dirty = rect if self._earth_rect.isNull() else rect.united(self._earth_rect)
        self._earth_rect = rect
        disc = int(radius * 1.2) + 2
        self._earth_disc = QRect(int(center.x()) - disc, int(center.y()) - disc, disc * 2, disc * 2)
        self.update(dirty)

    def _render_sprites(self, dpr: float) -> None:
        """One halo+core sprite per star tier; twinkle is just paint opacity."""
        self._sprites = {}
        for tier, radius in enumerate((1.05, 1.45, 1.9)):
            half = radius * 2.6 + 1.0
            side = int(math.ceil(half * 2))
            sprite = QPixmap(int(math.ceil(side * dpr)), int(math.ceil(side * dpr)))
            sprite.setDevicePixelRatio(dpr)
            sprite.fill(Qt.GlobalColor.transparent)
            painter = QPainter(sprite)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            center = QPointF(side / 2.0, side / 2.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tint(MOONLIGHT, 0.16)))
            painter.drawEllipse(center, radius * 2.6, radius * 2.6)
            painter.setBrush(QBrush(tint(INK, 1.0)))
            painter.drawEllipse(center, radius, radius)
            painter.end()
            self._sprites[tier] = sprite

    # -- frosted backdrop for glass ------------------------------------------
    def paint_frost(self, painter: QPainter, source: QRect, target: QRectF) -> bool:
        """Draw the blurred scene under `source` (our coordinates) into `target`."""
        self._ensure_sky()
        if self._frost is None:
            return False
        dpr = self._sky_dpr
        src = QRectF(source.x() * dpr, source.y() * dpr,
                     source.width() * dpr, source.height() * dpr)
        painter.drawPixmap(target, self._frost, src)
        return True

    # -- per-frame ----------------------------------------------------------
    def _update_parallax(self, width: int, height: int) -> None:
        """Ease the star layers toward an offset opposite the mouse pointer."""
        cursor = self.mapFromGlobal(QCursor.pos())
        tx = max(-1.0, min(1.0, cursor.x() / max(width, 1) * 2.0 - 1.0))
        ty = max(-1.0, min(1.0, cursor.y() / max(height, 1) * 2.0 - 1.0))
        px, py = self._parallax.x(), self._parallax.y()
        self._parallax = QPointF(px + (-tx - px) * 0.10, py + (-ty - py) * 0.10)

    def _tick(self) -> None:
        if not self.isVisible() or self.width() <= 0:
            return
        window = self.window()
        if window is not None and window.isMinimized():
            return
        if self._sky is None:
            return  # first paint has not happened yet

        elapsed = time.monotonic() - self._t0
        self._phase = elapsed
        width, height = self.width(), self.height()
        self._update_parallax(width, height)
        self._advance_earthrise(elapsed, width, height)

        # Card geometry only changes on resize or page switch, and stars move a
        # few px per second, so which stars sit behind glass is re-decided twice
        # a second rather than tested every frame.
        recheck = self._covered_age <= 0
        if recheck:
            self._covered = self._covered_rects()
            self._covered_age = 15
        self._covered_age -= 1

        shift_x = self._parallax.x() * PARALLAX_PX
        shift_y = self._parallax.y() * PARALLAX_PX * 0.6
        for index, star in enumerate(self._live):
            depth = self.STAR_DEPTH[star["t"]]
            star["x"] = (star["x0"] + star["vx"] * elapsed) % width + shift_x * depth
            star["y"] = star["y0"] + shift_y * depth
            new_rect = self._star_rect(star)
            old_rect = self._rects[index]
            self._rects[index] = new_rect
            dirty = new_rect if old_rect.isNull() else new_rect.united(old_rect)
            if recheck:
                star["hidden"] = any(dirty.intersects(block) for block in self._covered)
            # Stars behind glass are not worth animating: repainting them would
            # force the card (and any video in it) to repaint too.
            if star.get("hidden"):
                continue
            self.update(dirty)

    def _covered_rects(self) -> list[QRect]:
        """Geometry of visible glass surfaces, in our coordinates."""
        rects = []
        for widget in self.findChildren((GlassCard, GlassCapsule)):
            if widget.isVisible():
                rects.append(QRect(widget.mapTo(self, QPoint(0, 0)), widget.size()))
        return rects

    @staticmethod
    def _star_rect(star: dict) -> QRect:
        pad = star["r"] * 2.6 + 1.0  # halo radius plus antialiasing slack
        return QRect(
            int(star["x"] - pad), int(star["y"] - pad),
            int(pad * 2) + 2, int(pad * 2) + 2,
        )

    def paintEvent(self, event):
        self._ensure_sky()

        # Qt clips the painter to the damaged region, so blitting its bounding
        # rect only writes the pixels that actually changed.
        damaged = event.rect()
        region = event.region()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._blit_sky(painter, damaged)

        if not self._earth_baked and self._earth_sprite is not None \
                and not self._earth_rect.isNull() and region.intersects(self._earth_rect):
            painter.save()
            painter.setClipPath(self._sky_path)  # Earth rises from behind the limb
            painter.drawPixmap(QPointF(self._earth_rect.topLeft()), self._earth_sprite)
            painter.restore()

        earth = self._earth_disc
        for star, rect in zip(self._live, self._rects):
            if rect.isNull():  # not placed by a tick yet
                continue
            # test the exact region, not its bounding box; never pass in front of Earth
            if region.intersects(rect) and not rect.intersects(earth):
                self._paint_live_star(painter, star)

    def _blit_sky(self, painter: QPainter, rect: QRect) -> None:
        if self._sky is None:
            return
        dpr = self._sky_dpr
        source = QRectF(rect.x() * dpr, rect.y() * dpr, rect.width() * dpr, rect.height() * dpr)
        painter.drawPixmap(QRectF(rect), self._sky, source)

    def _paint_live_star(self, painter: QPainter, star: dict) -> None:
        sprite = self._sprites.get(star["t"])
        if sprite is None:
            return
        twinkle = 0.58 + 0.42 * math.sin(self._phase * star["tw"] + star["ph"])
        half = sprite.width() / sprite.devicePixelRatio() / 2.0
        painter.setOpacity(star["a"] * twinkle)
        painter.drawPixmap(QPointF(star["x"] - half, star["y"] - half), sprite)
        painter.setOpacity(1.0)


# ---------------------------------------------------------------------------
# Liquid glass
# ---------------------------------------------------------------------------

def _scene_behind(widget: QWidget) -> StarfieldBackground | None:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, StarfieldBackground):
            return parent
        parent = parent.parentWidget()
    return None


def paint_liquid_glass(painter: QPainter, widget: QWidget, radius: float) -> None:
    """Paint a glass slab over the whole widget.

    Layers, bottom to top: the frosted scene behind the widget (so the glass
    reads as refracting what is behind it), a white wash, a specular sheen
    across the top, and a rim light that is brightest on the top edge and
    catches again on the bottom lip.
    """
    rect = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    path = rounded_path(rect, radius)

    painter.save()
    painter.setClipPath(path)
    scene = _scene_behind(widget)
    if scene is None or not scene.paint_frost(
        painter, QRect(widget.mapTo(scene, QPoint(0, 0)), widget.size()), QRectF(widget.rect())
    ):
        painter.fillRect(rect, QColor(BG_MID))  # no scene (e.g. docked panel)

    wash = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    wash.setColorAt(0.0, tint(INK, GLASS_TINT_TOP))
    wash.setColorAt(1.0, tint(INK, GLASS_TINT_BOTTOM))
    painter.fillRect(rect, QBrush(wash))

    sheen_height = min(rect.height() * 0.45, 90.0)
    sheen = QLinearGradient(0, rect.top(), 0, rect.top() + sheen_height)
    sheen.setColorAt(0.0, tint(INK, GLASS_SHEEN))
    sheen.setColorAt(1.0, tint(INK, 0.0))
    painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), sheen_height), QBrush(sheen))
    painter.restore()

    rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    rim.setColorAt(0.0, tint(INK, GLASS_RIM_TOP))
    rim.setColorAt(min(0.25, 24.0 / max(rect.height(), 1.0)), tint(INK, GLASS_RIM_SIDE * 2))
    rim.setColorAt(0.70, tint(INK, GLASS_RIM_SIDE))
    rim.setColorAt(1.0, tint(INK, GLASS_RIM_BOTTOM))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QBrush(rim), 1.0))
    painter.drawPath(path)


class GlassCard(QWidget):
    """Liquid-glass slab with a body layout and optional section header.

    Like Hanoon's GlassBox it can glow: softly on hover, blue while it is
    "active" (its camera is live) and red as an alert (an obstacle on radar).
    """

    def __init__(
        self,
        title: str | None = None,
        parent: QWidget | None = None,
        radius: int = RADIUS_CARD,
        padding: int = PAD_CARD,
        spacing: int = 12,
    ):
        super().__init__(parent)
        self._radius = radius
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)
        self.caption: QLabel | None = None
        if title:
            self.caption = caption_label(title, self)
            self.body.addWidget(self.caption)
        self._levels = {"hover": 0.0, "active": 0.0, "alert": 0.0}
        self._targets: dict[str, float] = {}
        self._anims: dict[str, QVariantAnimation] = {}

    def _fade(self, name: str, target: float, duration: int) -> None:
        if self._targets.get(name) == target:
            return
        self._targets[name] = target
        anim = self._anims.get(name)
        if anim is None:
            anim = QVariantAnimation(self)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(lambda value, key=name: self._set_level(key, value))
            self._anims[name] = anim
        anim.stop()
        anim.setDuration(duration)
        anim.setStartValue(float(self._levels[name]))
        anim.setEndValue(float(target))
        anim.start()

    def _set_level(self, name: str, value) -> None:
        self._levels[name] = float(value)
        self.update()

    def set_active(self, active: bool) -> None:
        self._fade("active", 1.0 if active else 0.0, 350)

    def set_alert(self, alert: bool) -> None:
        self._fade("alert", 1.0 if alert else 0.0, 180)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._fade("hover", 1.0, 200)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._fade("hover", 0.0, 320)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_liquid_glass(painter, self, self._radius)

        path = rounded_path(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._radius)
        # (level, fill token, fill alpha, rim token, rim alpha, rim width)
        for level, fill, fill_alpha, rim, rim_alpha, width in (
            (self._levels["hover"], INK, 0.035, INK, 0.30, 1.2),
            (self._levels["active"], ACCENT, 0.035, ACCENT, 0.55, 1.4),
            (self._levels["alert"], BAD, 0.12, BAD, 0.92, 2.0),
        ):
            if level <= 0.004:
                continue
            painter.fillPath(path, QBrush(tint(fill, fill_alpha * level)))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(tint(rim, rim_alpha * level), width))
            painter.drawPath(path)


class GlassCapsule(QWidget):
    """Floating glass capsule, as used for iOS toolbars and status groups."""

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_liquid_glass(painter, self, self.height() / 2.0)


# ---------------------------------------------------------------------------
# BrandMark -- Hanoon's top-left identity
# ---------------------------------------------------------------------------

class BrandMark(QWidget):
    """Glowing blue core in a thin ring, then a letter-spaced MANUS / AD LUNAM.

    Density: 0 = mark only, 1 = mark + wordmark, 2 = + "Command & Control".
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._density = 2
        self._bold = app_font(14, QFont.Weight.Bold, spacing=3.0)
        self._light = app_font(14, QFont.Weight.Light, spacing=3.0)
        self._tag = app_font(12, QFont.Weight.Normal)

    def set_density(self, density: int) -> None:
        if density != self._density:
            self._density = density
            self.updateGeometry()
            self.update()

    def _widths(self) -> tuple[float, float, float]:
        return (
            QFontMetricsF(self._bold).horizontalAdvance("MANUS"),
            QFontMetricsF(self._light).horizontalAdvance("AD LUNAM"),
            QFontMetricsF(self._tag).horizontalAdvance("Command & Control"),
        )

    def sizeHint(self) -> QSize:
        manus, lunam, tag = self._widths()
        width = 30.0
        if self._density >= 1:
            width += 12 + manus + 10 + lunam
        if self._density >= 2:
            width += 18 + tag
        return QSize(int(math.ceil(width)) + 2, 40)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        mid = self.height() / 2.0

        center = QPointF(15, mid)
        glow = QRadialGradient(center, 15)
        glow.setColorAt(0.0, tint(ACCENT, 0.59))
        glow.setColorAt(1.0, tint(ACCENT, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, 15, 15)
        painter.setBrush(QBrush(QColor(ACCENT)))
        painter.drawEllipse(center, 4.5, 4.5)
        painter.setPen(QPen(tint(INK, 0.35), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, 9, 9)

        if self._density < 1:
            return
        manus, lunam, _ = self._widths()
        flags = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        x = 42.0
        painter.setFont(self._bold)
        painter.setPen(QPen(tint(INK, 0.96)))
        painter.drawText(QRectF(x, 0, manus + 8, self.height()), flags, "MANUS")
        x += manus + 10
        painter.setFont(self._light)
        painter.setPen(QPen(QColor("#C7C7D1")))
        painter.drawText(QRectF(x, 0, lunam + 8, self.height()), flags, "AD LUNAM")
        x += lunam
        if self._density >= 2:
            x += 9
            painter.setPen(QPen(tint(INK, 0.16), 1))
            painter.drawLine(QPointF(x, mid - 9), QPointF(x, mid + 9))
            painter.setFont(self._tag)
            painter.setPen(QPen(tint(INK, 0.50)))
            painter.drawText(QRectF(x + 9, 0, 200, self.height()), flags, "Command & Control")


# ---------------------------------------------------------------------------
# PillButton
# ---------------------------------------------------------------------------

class PillButton(QPushButton):
    """Capsule button with an animated hover lift.

    variant: 'primary' (accent glass), 'secondary' (clear glass + rim),
             'ghost' (plain, for use inside a glass capsule).
    Pass `glyph` for a painted icon; with no text the button is a circle.
    `set_active(True)` latches an accent tint, for toggles; `set_busy(True)`
    spins the glyph, for work in progress.
    """

    def __init__(
        self,
        text: str = "",
        variant: str = "secondary",
        glyph: str | None = None,
        parent: QWidget | None = None,
        compact: bool = False,
        height: int | None = None,
    ):
        super().__init__(text, parent)
        self._variant = variant
        self._glyph = glyph
        self._compact = compact
        self._active = False
        self._hover = 0.0
        self._fixed_height = height or (34 if compact else 46)
        self._spin_angle = 0.0
        self._spin = QTimer(self)
        self._spin.setInterval(30)
        self._spin.timeout.connect(self._advance_spin)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(app_font(13 if compact else 15, QFont.Weight.DemiBold))
        self.setFixedHeight(self._fixed_height)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # animated hover value, 0..1
    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = float(value)
        self.update()

    hover = pyqtProperty(float, _get_hover, _set_hover)

    def set_active(self, active: bool) -> None:
        """Latched look, for toggles such as the camera flip controls."""
        if self._active != active:
            self._active = active
            self.update()

    def is_active(self) -> bool:
        return self._active

    def set_glyph(self, glyph: str | None) -> None:
        self._glyph = glyph
        self.update()

    def set_busy(self, busy: bool) -> None:
        if busy and not self._spin.isActive():
            self._spin.start()
        elif not busy and self._spin.isActive():
            self._spin.stop()
            self._spin_angle = 0.0
        self.update()

    def _advance_spin(self) -> None:
        self._spin_angle = (self._spin_angle + 14.0) % 360.0
        self.update()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isEnabled():
            self._animate_to(1.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate_to(0.0)

    def _animate_to(self, value: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(value)
        self._anim.start()

    def sizeHint(self) -> QSize:
        if not self.text():
            return QSize(self._fixed_height, self._fixed_height)
        metrics = QFontMetrics(self.font())
        glyph_width = (self._fixed_height * 0.48) if self._glyph else 0
        gap = 8 if self._glyph else 0
        side = 14 if self._compact else 22
        width = metrics.horizontalAdvance(self.text()) + glyph_width + gap + side * 2
        return QSize(int(width), self._fixed_height)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(rect, rect.height() / 2.0)
        enabled = self.isEnabled()
        busy = self._spin.isActive()
        lift = 0.0 if not enabled else (1.0 if self.isDown() else self._hover)

        if self._variant == "primary":
            body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            body.setColorAt(0.0, QColor(ACCENT).lighter(108 + int(14 * lift)) if enabled else tint(INK, 0.12))
            body.setColorAt(1.0, QColor(ACCENT).darker(108 - int(6 * lift)) if enabled else tint(INK, 0.08))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(body))
            painter.drawPath(path)
            self._paint_sheen(painter, rect, path, 0.24)
            content = tint(INK, 1.0 if enabled else 0.35)
            rim_strength = 0.45
        elif self._active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tint(ACCENT, 0.30 + 0.10 * lift)))
            painter.drawPath(path)
            self._paint_sheen(painter, rect, path, 0.12)
            content = tint(ACCENT_LIGHT, 1.0 if enabled else 0.4)
            rim_strength = 0.40
        elif self._variant == "ghost":
            if lift > 0.01:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(tint(INK, 0.10 * lift)))
                painter.drawPath(path)
            content = tint(INK, (0.86 if enabled else 0.32) + 0.14 * lift)
            rim_strength = 0.0
        else:  # secondary: clear glass
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tint(INK, 0.09 + 0.07 * lift)))
            painter.drawPath(path)
            self._paint_sheen(painter, rect, path, 0.10)
            content = tint(INK, (0.90 if enabled else 0.32) + 0.10 * lift)
            rim_strength = 0.30 + 0.12 * lift
        if busy:
            content = tint(ACCENT_LIGHT, 1.0)  # stays readable while disabled

        if rim_strength:
            rim = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            rim.setColorAt(0.0, tint(INK, rim_strength))
            rim.setColorAt(0.55, tint(INK, rim_strength * 0.20))
            rim.setColorAt(1.0, tint(INK, rim_strength * 0.45))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QBrush(rim), 1.0))
            painter.drawPath(path)

        # content: optional glyph, then text, centred as a group
        metrics = QFontMetrics(self.font())
        text = self.text()
        text_width = metrics.horizontalAdvance(text) if text else 0
        glyph_size = rect.height() * (0.48 if text else 0.50)
        gap = 8 if (self._glyph and text) else 0
        total = text_width + (glyph_size if self._glyph else 0) + gap
        cursor_x = rect.center().x() - total / 2.0

        if self._glyph:
            glyph_rect = QRectF(cursor_x, rect.center().y() - glyph_size / 2.0,
                                glyph_size, glyph_size)
            if busy:
                painter.save()
                painter.translate(glyph_rect.center())
                painter.rotate(self._spin_angle)
                painter.translate(-glyph_rect.center())
            paint_glyph(painter, self._glyph, glyph_rect, content,
                        width=1.6 if self._compact else 1.8)
            if busy:
                painter.restore()
            cursor_x += glyph_size + gap

        if text:
            painter.setPen(QPen(content))
            painter.setFont(self.font())
            painter.drawText(
                QRectF(cursor_x, rect.top(), text_width + 2, rect.height()),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                text,
            )

    @staticmethod
    def _paint_sheen(painter: QPainter, rect: QRectF, path: QPainterPath, alpha: float) -> None:
        painter.save()
        painter.setClipPath(path)
        sheen = QLinearGradient(0, rect.top(), 0, rect.center().y())
        sheen.setColorAt(0.0, tint(INK, alpha))
        sheen.setColorAt(1.0, tint(INK, 0.0))
        painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), rect.height() / 2.0),
                         QBrush(sheen))
        painter.restore()


# ---------------------------------------------------------------------------
# StatusPill / StatusRow
# ---------------------------------------------------------------------------

class StatusPill(QWidget):
    """Dot + label. Healthy states breathe; everything else sits still.

    flat=True drops the capsule, for pills grouped inside a GlassCapsule.

    All breathing pills share one timer and one phase: they pulse in unison,
    and Qt folds their repaints (and the glass behind them) into a single
    paint pass per frame instead of one per pill.
    """

    PULSE_MS = 60
    PULSE_PERIOD = 1.05  # seconds per breath
    _pulse_timer: QTimer | None = None
    _pulsing: "weakref.WeakSet[StatusPill]" = weakref.WeakSet()

    def __init__(self, caption: str = "", state: str = "idle",
                 parent: QWidget | None = None, min_width: int = 0,
                 flat: bool = False):
        super().__init__(parent)
        self._caption = caption
        self._state = state
        self._min_width = min_width
        self._flat = flat
        self.setFixedHeight(30)
        self.setFont(app_font(13, QFont.Weight.DemiBold))
        self._sync_timer()

    @classmethod
    def _shared_timer(cls) -> QTimer:
        if cls._pulse_timer is None:
            cls._pulse_timer = QTimer()
            cls._pulse_timer.setInterval(cls.PULSE_MS)
            cls._pulse_timer.timeout.connect(cls._pulse_all)
        return cls._pulse_timer

    @classmethod
    def _pulse_all(cls) -> None:
        for pill in list(cls._pulsing):
            pill.update()

    def _is_pulsing(self) -> bool:
        return self in StatusPill._pulsing

    def set_state(self, state: str, caption: str | None = None) -> None:
        if state == self._state and (caption is None or caption == self._caption):
            return
        self._state = state
        if caption is not None:
            self.setText(caption)
        self._sync_timer()
        self.updateGeometry()
        self.update()

    def state(self) -> str:
        return self._state

    def setText(self, caption: str) -> None:
        """Label-style setter, so status writers can treat this like a QLabel."""
        self._caption = str(caption)
        self.setToolTip(self._caption)  # full text if the pill has to elide
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._caption

    def _sync_timer(self) -> None:
        if self._state in ("ok", "live") and self.isVisible():
            StatusPill._pulsing.add(self)
        else:
            StatusPill._pulsing.discard(self)
        timer = self._shared_timer()
        if StatusPill._pulsing and not timer.isActive():
            timer.start()
        elif not StatusPill._pulsing and timer.isActive():
            timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_timer()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        width = metrics.horizontalAdvance(self._caption) + (30 if self._flat else 42)
        return QSize(max(width, self._min_width), self.height())

    def _paint_dot(self, painter: QPainter, center: QPointF) -> None:
        color = QColor(state_color(self._state))
        if self._is_pulsing():
            pulse = (time.monotonic() / self.PULSE_PERIOD) % 1.0
            halo = 3.0 + 5.0 * pulse
            fade = QColor(color)
            fade.setAlphaF(0.34 * (1.0 - pulse))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fade))
            painter.drawEllipse(center, halo, halo)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, 3.8, 3.8)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if not self._flat:
            path = rounded_path(rect, rect.height() / 2.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(tint(INK, 0.08)))
            painter.drawPath(path)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(tint(INK, 0.12), 1.0))
            painter.drawPath(path)

        center = QPointF(rect.left() + (8 if self._flat else 15), rect.center().y())
        self._paint_dot(painter, center)

        left = center.x() + 11
        painter.setPen(QPen(tint(INK, 0.88)))
        painter.setFont(self.font())
        text_rect = QRectF(left, rect.top(), rect.right() - left - (4 if self._flat else 12),
                           rect.height())
        metrics = QFontMetrics(self.font())
        elided = metrics.elidedText(
            self._caption, Qt.TextElideMode.ElideRight, int(text_rect.width())
        )
        # Too tight for a meaningful word: show the dot alone (tooltip has the text).
        if len(elided.rstrip("…")) < 4 and elided != self._caption:
            return
        painter.drawText(
            text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided
        )


class StatusRow(StatusPill):
    """One line of a status list: dot, name on the left, value on the right."""

    def __init__(self, name: str, value: str = "", state: str = "idle",
                 parent: QWidget | None = None):
        super().__init__(value, state, parent, flat=True)
        self._name = name
        self.setFixedHeight(26)
        self._name_font = app_font(13, QFont.Weight.Medium)

    def sizeHint(self) -> QSize:
        return QSize(180, self.height())

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        self._paint_dot(painter, QPointF(rect.left() + 6, rect.center().y()))
        flags_left = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        flags_right = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

        painter.setFont(self._name_font)
        painter.setPen(QPen(tint(INK, 0.60)))
        name_width = QFontMetrics(self._name_font).horizontalAdvance(self._name)
        painter.drawText(QRectF(rect.left() + 18, rect.top(), name_width + 4, rect.height()),
                         flags_left, self._name)

        painter.setFont(self.font())
        painter.setPen(QPen(tint(INK, 0.92)))
        value_left = rect.left() + 18 + name_width + 10
        value = QFontMetrics(self.font()).elidedText(
            self._caption, Qt.TextElideMode.ElideRight, int(rect.right() - value_left)
        )
        painter.drawText(QRectF(value_left, rect.top(), rect.right() - value_left, rect.height()),
                         flags_right, value)


# ---------------------------------------------------------------------------
# VideoSurface
# ---------------------------------------------------------------------------

class VideoSurface(QLabel):
    """QLabel that paints its pixmap letterboxed inside a rounded frame.

    Stays a QLabel so the existing `setPixmap` / `size()` feed code is unchanged.
    Emits `clicked` on a left click (used to swap hero and inset) and can show
    a status chip over the picture (used in fullscreen).
    """

    clicked = pyqtSignal()

    def __init__(self, placeholder: str = "", parent: QWidget | None = None,
                 radius: int = RADIUS_VIDEO):
        super().__init__(parent)
        self._placeholder = placeholder
        self._radius = radius
        self._overlay: tuple[str, str] | None = None
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFont(app_font(13, QFont.Weight.Medium))

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_overlay(self, text: str | None, color: str | None = None) -> None:
        overlay = (text, color or INK) if text else None
        if overlay != self._overlay:
            self._overlay = overlay
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = rounded_path(rect, self._radius)

        # matte behind the video, so letterbox bars read as part of the frame
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#04050A")))
        painter.drawPath(path)

        pixmap = self.pixmap()
        painter.setClipPath(path)
        if pixmap is not None and not pixmap.isNull():
            size = pixmap.size()
            size.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF(
                (self.width() - size.width()) / 2.0,
                (self.height() - size.height()) / 2.0,
                size.width(), size.height(),
            )
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        else:
            painter.setPen(QPen(tint(INK, 0.38)))
            painter.setFont(self.font())
            painter.drawText(
                QRectF(self.rect()).adjusted(16, 16, -16, -16),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._placeholder,
            )
        if self._overlay:
            self._paint_overlay(painter, rect)
        painter.setClipping(False)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tint(INK, 0.10), 1.0))
        painter.drawPath(path)

    def _paint_overlay(self, painter: QPainter, rect: QRectF) -> None:
        text, color = self._overlay
        font = app_font(15, QFont.Weight.DemiBold)
        painter.setFont(font)
        width = QFontMetrics(font).horizontalAdvance(text) + 50
        height = 38.0
        chip = QRectF(rect.left() + 18, rect.top() + 18, width, height)
        painter.setPen(QPen(tint(INK, 0.22), 1))
        painter.setBrush(QBrush(tint("#000000", 0.58)))
        painter.drawRoundedRect(chip, height / 2, height / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(color)))
        painter.drawEllipse(QPointF(chip.left() + 19, chip.center().y()), 5.0, 5.0)
        painter.setPen(QPen(tint(INK, 0.96)))
        painter.drawText(
            QRectF(chip.left() + 33, chip.top(), width - 38, height),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            text,
        )


# ---------------------------------------------------------------------------
# SpeedSlider
# ---------------------------------------------------------------------------

class SpeedSlider(QSlider):
    """iOS-style slider: thick rounded track, accent fill, capsule glass thumb."""

    TRACK = 6.0
    THUMB_W = 19.0   # half-width of the capsule thumb
    THUMB_H = 12.0   # half-height

    def __init__(self, parent: QWidget | None = None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    # -- geometry helpers ---------------------------------------------------
    def _span(self) -> tuple[float, float]:
        left = self.THUMB_W + 1.0
        right = self.width() - self.THUMB_W - 1.0
        return left, max(right, left + 1.0)

    def _value_to_x(self, value: int) -> float:
        left, right = self._span()
        span = max(self.maximum() - self.minimum(), 1)
        return left + (right - left) * (value - self.minimum()) / span

    def _x_to_value(self, x: float) -> int:
        left, right = self._span()
        ratio = max(0.0, min(1.0, (x - left) / max(right - left, 1.0)))
        return self.minimum() + round(ratio * (self.maximum() - self.minimum()))

    # Absolute positioning: tapping the track jumps there, as on iOS.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._x_to_value(event.position().x()))
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self._x_to_value(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isSliderDown():
            self.setSliderDown(False)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center_y = self.height() / 2.0
        left, right = self._span()
        thumb_x = self._value_to_x(self.value())

        track = QRectF(left - self.THUMB_W * 0.6, center_y - self.TRACK / 2.0,
                       (right - left) + self.THUMB_W * 1.2, self.TRACK)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint(INK, 0.16)))
        painter.drawRoundedRect(track, self.TRACK / 2.0, self.TRACK / 2.0)

        filled = QRectF(track)
        filled.setRight(max(thumb_x, track.left() + self.TRACK))
        fill = QLinearGradient(filled.topLeft(), filled.topRight())
        fill.setColorAt(0.0, QColor(ACCENT))
        fill.setColorAt(1.0, QColor(ACCENT_LIGHT))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(filled, self.TRACK / 2.0, self.TRACK / 2.0)

        # The thumb grows slightly while held, like the iOS glass knob.
        grow = 1.12 if self.isSliderDown() else 1.0
        half_w, half_h = self.THUMB_W * grow, self.THUMB_H * grow
        thumb = QRectF(thumb_x - half_w, center_y - half_h, half_w * 2, half_h * 2)

        shadow = QRadialGradient(QPointF(thumb_x, center_y + 2), half_w * 1.5)
        shadow.setColorAt(0.0, tint("#000000", 0.32))
        shadow.setColorAt(1.0, tint("#000000", 0.0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QPointF(thumb_x, center_y + 2), half_w * 1.5, half_h * 1.6)

        knob = QLinearGradient(thumb.topLeft(), thumb.bottomLeft())
        knob.setColorAt(0.0, QColor("#FFFFFF"))
        knob.setColorAt(1.0, QColor("#E6EAF2"))
        painter.setBrush(QBrush(knob))
        painter.drawRoundedRect(thumb, half_h, half_h)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tint("#000000", 0.10), 1.0))
        painter.drawRoundedRect(thumb.adjusted(0.5, 0.5, -0.5, -0.5), half_h, half_h)


# ---------------------------------------------------------------------------
# NumeralLabel
# ---------------------------------------------------------------------------

class NumeralLabel(QWidget):
    """Oversized thin numerals with an optional smaller trailing unit.

    "72%" renders as a large "72" with a small "%"; "FL" renders as-is. The
    widget is only as tall as the cap height, so big numbers do not drag the
    font's empty ascent and descent space into the layout. Colour changes
    cross-fade, like Hanoon's payload tile. Label-compatible: setText() / text().
    """

    def __init__(self, text: str = "", size: int = 60, color: str = INK,
                 alpha: float = 0.96, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = str(text)
        self._color = tint(color, alpha)
        self._font = numeral_font(size)
        self._unit_font = numeral_font(max(12, int(size * 0.42)))
        cap = QFontMetricsF(self._font).capHeight()
        self.setFixedHeight(int(math.ceil(cap)) + 4)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_color)

    def setText(self, text: str) -> None:
        self._text = str(text)
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, hex_color: str, alpha: float = 0.96) -> None:
        target = tint(hex_color, alpha)
        if target == self._color:
            return
        self._anim.stop()
        self._anim.setStartValue(QColor(self._color))
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_color(self, value) -> None:
        self._color = QColor(value)
        self.update()

    def _split(self) -> tuple[str, str]:
        """Separate a trailing non-alphanumeric unit such as '%' or '°'."""
        cut = len(self._text)
        while cut > 0 and not self._text[cut - 1].isalnum():
            cut -= 1
        if cut == 0:
            return self._text, ""
        return self._text[:cut], self._text[cut:]

    def sizeHint(self) -> QSize:
        main, unit = self._split()
        width = QFontMetricsF(self._font).horizontalAdvance(main)
        if unit:
            width += 3 + QFontMetricsF(self._unit_font).horizontalAdvance(unit)
        return QSize(int(math.ceil(width)) + 4, self.height())

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        baseline = self.height() - 2
        main, unit = self._split()
        painter.setPen(QPen(self._color))
        painter.setFont(self._font)
        painter.drawText(QPointF(0, baseline), main)
        if unit:
            x = QFontMetricsF(self._font).horizontalAdvance(main) + 3
            unit_color = QColor(self._color)
            unit_color.setAlphaF(self._color.alphaF() * 0.55)
            painter.setPen(QPen(unit_color))
            painter.setFont(self._unit_font)
            painter.drawText(QPointF(x, baseline), unit)


class CommandLabel(NumeralLabel):
    """Bold, glowing drive-command letters ("S", "FL", ...).

    The letters are filled with a top-lit gradient in the command colour and
    sit in a soft bloom with a layered halo, so the active command reads at a
    glance. Same API as NumeralLabel: setText(), text(), set_color() (which
    cross-fades). It only repaints when the command changes.
    """

    GLOW_PAD = 14  # room around the letters for the halo

    def __init__(self, text: str = "", size: int = 58, color: str = INK,
                 alpha: float = 1.0, parent: QWidget | None = None):
        super().__init__(text, size, color, alpha, parent)
        font = QFont()
        font.setFamilies(COMMAND_FAMILIES)
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        self._font = font
        cap = QFontMetricsF(font).capHeight()
        self.setFixedHeight(int(math.ceil(cap)) + 2 * self.GLOW_PAD)

    def sizeHint(self) -> QSize:
        width = QFontMetricsF(self._font).horizontalAdvance(self._text)
        return QSize(int(math.ceil(width)) + 2 * self.GLOW_PAD, self.height())

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self._color)
        baseline = self.height() - self.GLOW_PAD
        path = QPainterPath()
        # Winding fill: variable fonts such as Bahnschrift build stems from
        # overlapping contours, which the default odd-even rule punches holes in.
        path.setFillRule(Qt.FillRule.WindingFill)
        path.addText(QPointF(self.GLOW_PAD, baseline), self._font, self._text)
        bounds = path.boundingRect()

        # soft bloom behind the letters: an ellipse that fades to nothing inside
        # the widget, so it never shows a hard clipped edge
        rect = QRectF(self.rect())
        center = bounds.center()
        # centred on the letters, and no larger than the room the widget has
        rx = min(center.x() - rect.left(), rect.right() - center.x())
        ry = min(center.y() - rect.top(), rect.bottom() - center.y())
        bloom = QRadialGradient(QPointF(0, 0), 1.0)
        bloom_in = QColor(color)
        bloom_in.setAlphaF(0.24)
        bloom_out = QColor(color)
        bloom_out.setAlphaF(0.0)
        bloom.setColorAt(0.0, bloom_in)
        bloom.setColorAt(1.0, bloom_out)
        painter.save()
        painter.translate(center)
        painter.scale(rx, ry)
        painter.fillRect(QRectF(-1, -1, 2, 2), QBrush(bloom))
        painter.restore()

        # layered halo: wide and faint to tight and bright, a cheap blur
        for width, alpha in ((14.0, 0.07), (9.0, 0.12), (5.0, 0.22), (2.4, 0.40)):
            halo = QColor(color)
            halo.setAlphaF(alpha)
            pen = QPen(halo, width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.strokePath(path, pen)

        # letters: lit from above, settling into the command colour
        fill = QLinearGradient(bounds.topLeft(), bounds.bottomLeft())
        fill.setColorAt(0.0, color.lighter(165))
        fill.setColorAt(0.55, color.lighter(118))
        fill.setColorAt(1.0, color)
        painter.fillPath(path, QBrush(fill))


# ---------------------------------------------------------------------------
# KeyCaps
# ---------------------------------------------------------------------------

class KeyCaps(QWidget):
    """W / A S D key caps that press down and light up while held.

    The lit colour follows the drive command (Hanoon's keyboard payload).
    """

    ROWS = (("W",), ("A", "S", "D"))
    CAP = 32
    GAP = 6
    DEPTH = 3          # visible key-side; a pressed cap sinks into it
    FRAME_MS = 16

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        width = 3 * self.CAP + 2 * self.GAP
        height = 2 * self.CAP + self.GAP + self.DEPTH
        self.setFixedSize(width + 2, height + 2)
        keys = [key for row in self.ROWS for key in row]
        self._target = dict.fromkeys(keys, 0.0)
        self._level = dict.fromkeys(keys, 0.0)
        self._lit = QColor(ACCENT)
        self._font = app_font(13, QFont.Weight.DemiBold)
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._animate)

    def set_color(self, hex_color: str) -> None:
        self._lit = QColor(hex_color)
        self.update()

    def set_pressed(self, letters) -> None:
        """Light exactly these keys, e.g. {'W', 'A'}."""
        letters = {str(letter).upper() for letter in letters}
        for key in self._target:
            self._target[key] = 1.0 if key in letters else 0.0
            if self._target[key] == 1.0:
                self._level[key] = 1.0  # presses land instantly; releases ease out
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _animate(self) -> None:
        settled = True
        for key, target in self._target.items():
            level = self._level[key]
            if level > target:
                level = max(target, level - 0.12)
                settled = False
            self._level[key] = level
        if settled:
            self._timer.stop()
        self.update()

    def _cap_rect(self, row: int, col: int) -> QRectF:
        step = self.CAP + self.GAP
        x = 1 + step if row == 0 else 1 + col * step  # W sits above S
        return QRectF(x, 1 + row * step, self.CAP, self.CAP)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        radius = 8.0
        for row, keys in enumerate(self.ROWS):
            for col, key in enumerate(keys):
                level = self._level[key]
                base = self._cap_rect(row, col)

                # key side, visible below an un-pressed cap
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(tint("#000000", 0.45)))
                painter.drawRoundedRect(base.translated(0, self.DEPTH), radius, radius)

                face = base.translated(0, self.DEPTH * level)
                if level > 0.01:
                    glow = QRadialGradient(face.center(), self.CAP * 0.95)
                    glow_in = QColor(self._lit)
                    glow_in.setAlphaF(0.32 * level)
                    glow_out = QColor(self._lit)
                    glow_out.setAlphaF(0.0)
                    glow.setColorAt(0.0, glow_in)
                    glow.setColorAt(1.0, glow_out)
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(face.center(), self.CAP * 0.95, self.CAP * 0.95)

                fill = QLinearGradient(face.topLeft(), face.bottomLeft())
                fill.setColorAt(0.0, self._mix(tint(INK, 0.14), self._lit.lighter(118), level))
                fill.setColorAt(1.0, self._mix(tint(INK, 0.07), self._lit, level))
                painter.setBrush(QBrush(fill))
                painter.drawRoundedRect(face, radius, radius)

                rim = QLinearGradient(face.topLeft(), face.bottomLeft())
                rim.setColorAt(0.0, tint(INK, 0.38 + 0.2 * level))
                rim.setColorAt(1.0, tint(INK, 0.06))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QBrush(rim), 1.0))
                painter.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

                painter.setPen(QPen(tint(INK, 0.62 + 0.38 * level)))
                painter.setFont(self._font)
                painter.drawText(face, int(Qt.AlignmentFlag.AlignCenter), key)

    @staticmethod
    def _mix(a: QColor, b: QColor, t: float) -> QColor:
        t = max(0.0, min(1.0, t))
        return QColor.fromRgbF(
            a.redF() + (b.redF() - a.redF()) * t,
            a.greenF() + (b.greenF() - a.greenF()) * t,
            a.blueF() + (b.blueF() - a.blueF()) * t,
            a.alphaF() + (b.alphaF() - a.alphaF()) * t,
        )


# ---------------------------------------------------------------------------
# DirectionIndicator
# ---------------------------------------------------------------------------

class DirectionIndicator(QWidget):
    """Compass glyph that lights the axes of the active drive command."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(76, 76)
        self._command = "S"
        self._color = QColor(CMD_STOP)

    def set_command(self, command: str, color: str | None = None) -> None:
        self._command = (command or "S").upper()
        self._color = QColor(color or command_color(self._command))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        center = rect.center()
        reach = min(rect.width(), rect.height()) / 2.0 - 3.0

        command = self._command
        forward = command.startswith("F")
        back = command.startswith("B")
        left = command.endswith("L") and len(command) > 1
        right = command.endswith("R") and len(command) > 1

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint(INK, 0.05)))
        painter.drawEllipse(center, reach, reach)
        painter.setPen(QPen(tint(INK, 0.12), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, reach, reach)

        for active, angle in (
            (forward, 0.0),    # up
            (back, 180.0),     # down
            (left, 270.0),
            (right, 90.0),
        ):
            color = QColor(self._color) if active else tint(INK, 0.18)
            painter.save()
            painter.translate(center)
            painter.rotate(angle)
            pen = QPen(color, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            tip_y = -reach * 0.74
            chevron = QPainterPath(QPointF(-reach * 0.26, tip_y + reach * 0.24))
            chevron.lineTo(QPointF(0.0, tip_y))
            chevron.lineTo(QPointF(reach * 0.26, tip_y + reach * 0.24))
            painter.drawPath(chevron)
            if active:  # faint bloom behind the live direction
                painter.setPen(Qt.PenStyle.NoPen)
                glow = QRadialGradient(QPointF(0.0, tip_y + reach * 0.08), reach * 0.52)
                glow_in = QColor(self._color)
                glow_in.setAlphaF(0.26)
                glow_out = QColor(self._color)
                glow_out.setAlphaF(0.0)
                glow.setColorAt(0.0, glow_in)
                glow.setColorAt(1.0, glow_out)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPointF(0.0, tip_y + reach * 0.08), reach * 0.52, reach * 0.52)
            painter.restore()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint(INK, 0.07)))
        painter.drawEllipse(center, reach * 0.30, reach * 0.30)
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(center, reach * 0.13, reach * 0.13)


# ---------------------------------------------------------------------------
# TelemetryGraph -- Hanoon's rolling graph, restyled
# ---------------------------------------------------------------------------

class TelemetryGraph(QWidget):
    """Smooth rolling line graph of one value over the last 30 seconds.

    Samples are bucketed (0.25 s) so the curve stays readable: 'min' keeps the
    closest reading of each bucket, 'avg' the mean. Gaps in the data break the
    line. The repaint timer only runs while there is data in the window.
    """

    WINDOW = 30.0
    BUCKET = 0.25
    GAP = 1.2
    HEADER = 18.0

    def __init__(self, title: str, unit: str, color: str, min_span: float = 100.0,
                 cap: float | None = None, threshold: float | None = None,
                 mode: str = "avg", parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(160, 42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._title = title.upper()
        self._unit = unit
        self._color = QColor(color)
        self._min_span = float(min_span)
        self._cap = float(cap) if cap else None  # fixed ceiling; readings above are clamped
        self._threshold = threshold
        self._mode = mode
        self._samples: deque[tuple[float, float]] = deque()
        self._bucket: list[float] = []
        self._bucket_start: float | None = None
        self._top = float(cap) if cap else float(min_span)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)

    def add(self, value: float) -> None:
        now = time.monotonic()
        value = float(value)
        if self._cap:
            value = min(value, self._cap)
        if self._bucket_start is None or now - self._bucket_start > self.BUCKET * 2:
            self._bucket = []
            self._bucket_start = now
        self._bucket.append(value)
        if now - self._bucket_start >= self.BUCKET:
            result = min(self._bucket) if self._mode == "min" else sum(self._bucket) / len(self._bucket)
            self._samples.append((now, result))
            self._bucket = []
            self._bucket_start = now
            cutoff = now - self.WINDOW - 2.0
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        now = time.monotonic()
        while self._samples and self._samples[0][0] < now - self.WINDOW - 2.0:
            self._samples.popleft()
        if not self._samples:
            self._timer.stop()  # nothing left to scroll
        self.update()

    @staticmethod
    def _smooth_path(points: list[QPointF]) -> QPainterPath:
        """Catmull-Rom spline through the points, as cubic Beziers."""
        path = QPainterPath(points[0])
        count = len(points)
        for i in range(count - 1):
            p0 = points[i - 1] if i > 0 else points[i]
            p1, p2 = points[i], points[i + 1]
            p3 = points[i + 2] if i + 2 < count else p2
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        now = time.monotonic()
        width, height = float(self.width()), float(self.height())
        window_start = now - self.WINDOW
        visible = [(t, v) for t, v in self._samples if t >= window_start - 1.0]

        # The vertical range eases toward what the data needs (fixed when capped).
        if self._cap:
            top = self._cap
        else:
            peak = max((v for _, v in visible), default=0.0)
            self._top += (max(self._min_span, peak * 1.2) - self._top) * 0.2
            top = max(self._top, 1.0)

        plot = QRectF(0, self.HEADER + 4, width, max(10.0, height - self.HEADER - 4))

        def x_of(t: float) -> float:
            return plot.left() + (t - window_start) / self.WINDOW * plot.width()

        def y_of(v: float) -> float:
            return plot.bottom() - min(max(v / top, 0.0), 1.0) * plot.height()

        latest = visible[-1] if visible else None
        live = latest is not None and now - latest[0] < 1.5
        if not live:
            value_text = "--"
        elif self._cap and latest[1] >= self._cap:
            value_text = f">{int(self._cap)} {self._unit}"
        else:
            value_text = f"{int(round(latest[1]))} {self._unit}"
        painter.setFont(micro_font())
        painter.setPen(QPen(tint(INK, 0.50)))
        painter.drawText(QRectF(0, 0, width * 0.62, self.HEADER),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self._title)
        painter.setFont(app_font(13, QFont.Weight.DemiBold))
        painter.setPen(QPen(self._color if live else tint(INK, 0.40)))
        painter.drawText(QRectF(0, 0, width, self.HEADER),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                         value_text)

        painter.setPen(QPen(tint(INK, 0.08), 1))
        for i in range(4):
            y = plot.top() + plot.height() * i / 3.0
            painter.drawLine(QPointF(0, y), QPointF(width, y))

        painter.save()
        painter.setClipRect(plot.adjusted(0, -3, 0, 3))

        if self._threshold is not None and self._threshold < top:
            painter.setPen(QPen(tint(BAD, 0.55), 1, Qt.PenStyle.DashLine))
            y = y_of(self._threshold)
            painter.drawLine(QPointF(0, y), QPointF(width, y))

        segments: list[list[QPointF]] = []
        current: list[QPointF] = []
        previous_t = None
        for t, v in visible:
            if previous_t is not None and t - previous_t > self.GAP:
                segments.append(current)
                current = []
            current.append(QPointF(x_of(t), y_of(v)))
            previous_t = t
        if current:
            segments.append(current)

        fill = QLinearGradient(0, plot.top(), 0, plot.bottom())
        fill_top = QColor(self._color)
        fill_top.setAlpha(85)
        fill_bottom = QColor(self._color)
        fill_bottom.setAlpha(0)
        fill.setColorAt(0.0, fill_top)
        fill.setColorAt(1.0, fill_bottom)

        line_pen = QPen(self._color, 2)
        line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        line_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        for points in segments:
            if len(points) < 2:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(self._color))
                painter.drawEllipse(points[0], 2.0, 2.0)
                continue
            line = self._smooth_path(points)
            area = QPainterPath(line)
            area.lineTo(points[-1].x(), plot.bottom())
            area.lineTo(points[0].x(), plot.bottom())
            area.closeSubpath()
            painter.fillPath(area, QBrush(fill))
            painter.setPen(line_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(line)

        if live and segments:
            end = segments[-1][-1]
            glow = QColor(self._color)
            glow.setAlpha(70)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(end, 6.0, 6.0)
            painter.setBrush(QBrush(tint(INK, 0.96)))
            painter.drawEllipse(end, 2.6, 2.6)
        painter.restore()


# ---------------------------------------------------------------------------
# EventLogView
# ---------------------------------------------------------------------------

class EventLogView(QTextEdit):
    """Monospace log that colour-codes the [SYS] / [TX] / [CAM] / [LOCAL] tags.

    `append(text)` keeps its plain-text signature, so existing callers are
    untouched; the colouring happens here.
    """

    TAG_COLORS = {
        "[SYS]": ACCENT_LIGHT,
        "[TX]": OK,
        "[CAM]": WARN,
        "[LOCAL]": IDLE,
    }
    MAX_BLOCKS = 800  # keep the log bounded over a long mission

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(app_font(12, mono=True))
        self.setDocumentTitle("Event stream")
        self.document().setMaximumBlockCount(self.MAX_BLOCKS)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.viewport().setAutoFillBackground(False)

    def append(self, text: str) -> None:  # noqa: A003 - mirrors QTextEdit.append
        message = str(text)
        tag = ""
        body = message
        if message.startswith("["):
            close = message.find("]")
            if close != -1:
                tag = message[: close + 1]
                body = message[close + 1:].lstrip()

        tag_color = self.TAG_COLORS.get(tag, css(INK, 0.55))
        html = (
            f'<span style="color:{tag_color};">{escape(tag)}</span>'
            f'<span style="color:{css(INK, 0.80)};"> {escape(body)}</span>'
        )
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.document().isEmpty():
            cursor.insertBlock()
        cursor.insertHtml(html)
        self.moveCursor(QTextCursor.MoveOperation.End)
        self.ensureCursorVisible()


# ---------------------------------------------------------------------------
# application stylesheet -- only what custom painting does not cover
# ---------------------------------------------------------------------------

APP_STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {BG_TOP};
}}
QWidget#page, QStackedWidget {{
    background: transparent;
}}
QLabel {{
    /* no font here: a stylesheet font would override every setFont() call */
    color: {css(INK, 0.90)};
    background: transparent;
}}
QLabel#caption {{
    color: {css(INK, 0.60)};
}}
QLabel#cardTitle {{
    color: {css(INK, 0.94)};
}}
QLabel#helper {{
    color: {css(INK, 0.48)};
    font-size: 12px;
}}
QLabel#error {{
    color: {BAD};
    font-size: 12px;
}}
QLabel#appTitle {{
    color: {css(INK, 0.97)};
}}
QLabel#appSubtitle {{
    color: {css(INK, 0.55)};
}}
QLabel#metric {{
    color: {css(INK, 0.70)};
}}
QLabel#qrTile {{
    background-color: #FFFFFF;
    border-radius: {RADIUS_FIELD}px;
    color: #6B7280;
    font-size: 11px;
}}
QLineEdit {{
    background-color: {css(INK, 0.08)};
    color: {css(INK, 0.96)};
    border: 1px solid {css(INK, 0.14)};
    border-radius: {RADIUS_FIELD}px;
    padding: 10px 14px;
    font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 14px;
    selection-background-color: {css(ACCENT, 0.55)};
}}
QLineEdit:hover {{
    border: 1px solid {css(INK, 0.22)};
}}
QLineEdit:focus {{
    border: 1px solid {css(ACCENT, 0.90)};
    background-color: {css(INK, 0.10)};
}}
QLineEdit[invalid="true"] {{
    border: 1px solid {css(BAD, 0.85)};
}}
QTextEdit {{
    background: transparent;
    border: none;
    color: {css(INK, 0.80)};
    selection-background-color: {css(ACCENT, 0.45)};
}}
QDockWidget {{
    color: {css(INK, 0.70)};
    font-family: "SF Pro Display", "Segoe UI Variable Display", "Segoe UI", sans-serif;
    font-size: 13px;
    font-weight: 600;
}}
QDockWidget::title {{
    background: transparent;
    padding: 12px 16px;
    border: none;
    text-align: left;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    background: transparent;
    border: none;
    icon-size: 12px;
    subcontrol-position: top right;
    subcontrol-origin: margin;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 6px 2px 6px 2px;
}}
QScrollBar::handle:vertical {{
    background: {css(INK, 0.18)};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background: {css(INK, 0.32)};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px 6px 2px 6px;
}}
QScrollBar::handle:horizontal {{
    background: {css(INK, 0.18)};
    border-radius: 4px;
    min-width: 32px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QToolTip {{
    background-color: #1C1D21;
    color: {css(INK, 0.94)};
    border: 1px solid {css(INK, 0.16)};
    border-radius: 10px;
    padding: 7px 10px;
    font-family: "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 12px;
}}
QMessageBox {{
    background-color: #17181B;
}}
QMessageBox QLabel {{
    color: {css(INK, 0.90)};
}}
QMessageBox QPushButton {{
    background-color: {css(ACCENT, 0.92)};
    color: #FFFFFF;
    border: none;
    border-radius: 14px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}}
QFileDialog {{
    background-color: #17181B;
}}
"""
