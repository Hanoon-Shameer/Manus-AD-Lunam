"""Design system for Project MANUS AD LUNAM.

Everything visual lives here: the palette, the type scale, and the reusable
widgets the dashboard composes. Tweak the token block at the top and the whole
app follows.

Mood: Apple's Liquid Glass language (iOS 26 onward) applied to lunar mission
control. Floating glass capsules, concentric corner radii, surfaces that
refract a frosted copy of the scene behind them, one restrained accent, and
semantic colour used only to signal state.

The backdrop is an "Earthrise": the lunar horizon along the bottom, Earth hanging
in the black sky, and a faint transfer trajectory between them.

Performance notes (the camera feeds share this GUI thread):
  * The scene is baked into a pixmap once per resize, together with a blurred
    copy that glass surfaces sample. No live blur is ever computed.
  * Only ~90 bright stars animate. They repaint as small damaged rects and are
    skipped entirely when they sit behind glass, so cards and video are not
    recomposited by the background.
  * Nothing here puts a graphics effect over live video.
"""

from __future__ import annotations

import math
import random
import time
import weakref
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
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
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
    QTransform,
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

# Deep space gradient
BG_TOP = "#04060B"
BG_MID = "#070A14"
BG_BOTTOM = "#0A0E1A"

# Scenery
NEBULA_A = "#2B2456"      # violet bloom
NEBULA_B = "#113158"      # blue bloom
MOONLIGHT = "#CFE2FF"     # star halos
EARTH_SEA = "#2F6FD0"
EARTH_DAY = "#A8D8FF"
EARTH_NIGHT = "#08111F"
REGOLITH_LIT = "#2A2F3A"  # lunar surface at the horizon
REGOLITH_DARK = "#0B0D13"
HORIZON = 0.14            # fraction of the window height the moon occupies

INK = "#FFFFFF"

# The single accent. Blue for actions, cyan tint for live data.
ACCENT = "#0A84FF"
ACCENT_LIGHT = "#64D2FF"

# Semantic state colours -- only ever used to mean something
OK = "#30D158"
WARN = "#FFD60A"
BAD = "#FF453A"
IDLE = "#8E99AD"

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

# Readouts: oversized thin numerals over tiny letter-spaced capitals. The
# contrast in size and weight is what carries the hierarchy. Qt falls back to
# the lightest weight the font provides (Segoe UI Light on Windows).
NUMERAL_WEIGHT = QFont.Weight.ExtraLight
MICRO_SIZE = 10
MICRO_SPACING = 1.4

STARFIELD_SEED = 20260713  # fixed, so the sky is the same every launch


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


def numeral_font(size: int) -> QFont:
    """Large thin numerals for live readouts."""
    return app_font(size, NUMERAL_WEIGHT)


def micro_font(size: int = MICRO_SIZE) -> QFont:
    """Tiny upper-case caption face."""
    return app_font(size, QFont.Weight.DemiBold, spacing=MICRO_SPACING)


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
# StarfieldBackground -- the Earthrise scene
# ---------------------------------------------------------------------------

class StarfieldBackground(QWidget):
    """Deep-space backdrop seen from the lunar surface.

    Baked once per resize: sky gradient, nebula blooms, two dim star layers,
    Earth with its atmosphere glow, a dashed Earth-to-Moon transfer trajectory,
    the lunar horizon with a few foreshortened craters, and a vignette. A
    blurred copy of the result is kept for glass surfaces to sample.

    Animated: the nearest star layer -- slow parallax drift and a gentle
    twinkle -- repainting as small rects only where no glass covers them.
    """

    # (stars per megapixel, radius, alpha) for the two baked layers
    BAKED_LAYERS = ((520, 0.60, 0.30), (240, 0.95, 0.52))
    LIVE_STARS = 90
    FRAME_MS = 33  # ~30 fps

    def __init__(self, parent: QWidget | None = None, seed: int = STARFIELD_SEED):
        super().__init__(parent)
        self._seed = seed
        self._sky: QPixmap | None = None
        self._frost: QPixmap | None = None
        self._sky_dpr = 1.0
        self._earth_rect = QRect()
        self._live: list[dict] = []
        self._rects: list[QRect] = []           # last painted rect per live star
        self._sprites: dict[int, QPixmap] = {}  # pre-rendered star per tier
        self._covered: list[QRect] = []
        self._covered_age = 0
        self._phase = 0.0
        self._t0 = time.monotonic()

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

    def _build_live_stars(self) -> None:
        rng = random.Random(self._seed ^ 0x5EED)
        width, height = max(self.width(), 1), max(self.height(), 1)
        # The horizon crown is its highest point, so this keeps every drifting
        # star in open sky.
        sky_floor = height * (1.0 - HORIZON) - 8
        self._live = []
        for _ in range(self.LIVE_STARS):
            tier = rng.choice((0, 1, 2))
            self._live.append(
                {
                    "x0": rng.uniform(0, width),
                    "y": rng.uniform(0, max(sky_floor, 1)),
                    "t": tier,
                    "r": (1.05, 1.45, 1.9)[tier],
                    "a": (0.55, 0.75, 0.95)[tier],
                    # nearer (bigger) stars drift faster -- the parallax cue
                    "vx": (1.4, 3.0, 5.2)[tier] * rng.choice((-1.0, 1.0)) * rng.uniform(0.7, 1.3),
                    "ph": rng.uniform(0.0, math.tau),
                    "tw": rng.uniform(0.7, 1.6),  # twinkle rate
                    "x": 0.0,
                }
            )
        self._rects = [QRect() for _ in self._live]

    # -- the baked scene ----------------------------------------------------
    def _render_sky(self) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        width, height = max(self.width(), 1), max(self.height(), 1)
        pixmap = QPixmap(int(width * dpr), int(height * dpr))
        pixmap.fill(QColor(BG_TOP))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(dpr, dpr)  # draw in logical coordinates throughout
        rng = random.Random(self._seed)
        rect = QRectF(0, 0, width, height)

        # 1. deep space gradient
        sky = QLinearGradient(0, 0, width * 0.25, height)
        sky.setColorAt(0.0, QColor(BG_TOP))
        sky.setColorAt(0.55, QColor(BG_MID))
        sky.setColorAt(1.0, QColor(BG_BOTTOM))
        painter.fillRect(rect, QBrush(sky))

        # 2. soft nebula blooms
        for cx, cy, radius, token, alpha in (
            (0.16, 0.14, 0.85, NEBULA_A, 0.15),
            (0.70, 0.40, 0.90, NEBULA_B, 0.12),
        ):
            bloom = QRadialGradient(
                QPointF(width * cx, height * cy), max(width, height) * radius * 0.55
            )
            bloom.setColorAt(0.0, tint(token, alpha))
            bloom.setColorAt(1.0, tint(token, 0.0))
            painter.fillRect(rect, QBrush(bloom))

        # 3. baked star layers
        megapixels = (width * height) / 1_000_000.0
        painter.setPen(Qt.PenStyle.NoPen)
        for count_per_mp, radius, alpha in self.BAKED_LAYERS:
            for _ in range(int(count_per_mp * max(megapixels, 0.25))):
                x = rng.uniform(0, width)
                y = rng.uniform(0, height)
                jitter = rng.uniform(0.75, 1.3)
                painter.setBrush(QBrush(tint(INK, alpha * rng.uniform(0.5, 1.0))))
                painter.drawEllipse(QPointF(x, y), radius * jitter, radius * jitter)

        # 4. Earth, its parking orbit, and the trajectory down to the surface
        earth_center, earth_radius = self._paint_earth(painter, width, height)
        self._paint_trajectory(painter, width, height, earth_center, earth_radius)

        # 5. the lunar horizon, drawn last so it occludes stars behind it
        self._paint_horizon(painter, width, height, rng)

        # 6. vignette to settle the edges
        vignette = QRadialGradient(
            QPointF(width * 0.5, height * 0.42), max(width, height) * 0.80
        )
        vignette.setColorAt(0.0, tint("#000000", 0.0))
        vignette.setColorAt(0.62, tint("#000000", 0.08))
        vignette.setColorAt(1.0, tint("#000000", 0.40))
        painter.fillRect(rect, QBrush(vignette))

        painter.end()
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

    def _paint_earth(self, painter: QPainter, width: int, height: int) -> tuple[QPointF, float]:
        """Earth as a lit crescent with a thin atmospheric halo."""
        center = QPointF(width * 0.80, height * 0.19)
        radius = max(13.0, min(width, height) * 0.036)

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
        lit = disc.subtracted(shadow)
        day = QLinearGradient(center.x() + radius, center.y() - radius, center.x(), center.y())
        day.setColorAt(0.0, QColor(EARTH_DAY))
        day.setColorAt(1.0, QColor(EARTH_SEA))
        painter.setBrush(QBrush(day))
        painter.drawPath(lit)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tint(ACCENT_LIGHT, 0.30), 1.0))
        painter.drawPath(disc)

        margin = int(radius * 1.6)
        self._earth_rect = QRect(int(center.x()) - margin, int(center.y()) - margin,
                                 margin * 2, margin * 2)
        return center, radius

    def _paint_trajectory(self, painter: QPainter, width: int, height: int,
                          earth: QPointF, earth_radius: float) -> None:
        """Parking orbit around Earth plus a dashed transfer arc to the surface."""
        painter.save()
        orbit = QPainterPath()
        orbit.addEllipse(QPointF(0, 0), earth_radius * 3.1, earth_radius * 1.05)
        painter.setTransform(QTransform().translate(earth.x(), earth.y()).rotate(-18), True)
        orbit_pen = QPen(tint(INK, 0.11), 1.0)
        orbit_pen.setCosmetic(True)
        painter.setPen(orbit_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(orbit)
        painter.restore()

        landing_x = width * 0.24
        start = QPointF(earth.x() - earth_radius * 2.6, earth.y() + earth_radius * 1.0)
        end = QPointF(landing_x, self._horizon_y(landing_x, width, height) - 3)
        transfer = QPainterPath(start)
        transfer.cubicTo(QPointF(width * 0.60, height * 0.20),
                         QPointF(width * 0.34, height * 0.36), end)
        dashed = QPen(tint(INK, 0.16), 1.0)
        dashed.setCosmetic(True)
        dashed.setDashPattern([5.0, 7.0])
        painter.setPen(dashed)
        painter.drawPath(transfer)

        craft = transfer.pointAtPercent(0.38)
        halo = QRadialGradient(craft, 9.0)
        halo.setColorAt(0.0, tint(ACCENT_LIGHT, 0.40))
        halo.setColorAt(1.0, tint(ACCENT_LIGHT, 0.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(craft, 9.0, 9.0)
        painter.setBrush(QBrush(tint(INK, 0.95)))
        painter.drawEllipse(craft, 1.8, 1.8)

    def _paint_horizon(self, painter: QPainter, width: int, height: int,
                       rng: random.Random) -> None:
        """The lunar limb: dark regolith, an earthshine rim, foreshortened craters."""
        center, radius = self._horizon(width, height)
        crown = height * (1.0 - HORIZON)
        surface = QPainterPath()
        surface.addEllipse(center, radius, radius)

        ground = QLinearGradient(0, crown, 0, height)
        ground.setColorAt(0.0, QColor(REGOLITH_LIT))
        ground.setColorAt(0.35, QColor("#151821"))
        ground.setColorAt(1.0, QColor(REGOLITH_DARK))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(ground))
        painter.drawPath(surface)

        painter.save()
        painter.setClipPath(surface)
        # fine regolith grain
        for _ in range(int(width * 0.35)):
            x = rng.uniform(0, width)
            y = rng.uniform(self._horizon_y(x, width, height), height)
            painter.setBrush(QBrush(tint(INK, rng.uniform(0.02, 0.06))))
            painter.drawEllipse(QPointF(x, y), 0.7, 0.7)
        # craters squashed by perspective, larger towards the viewer
        for _ in range(11):
            x = rng.uniform(0.04, 0.96) * width
            top = self._horizon_y(x, width, height)
            depth = rng.uniform(0.08, 1.0)
            y = top + 6 + depth * (height - top) * 0.75
            rx = 5 + depth * rng.uniform(14, 34)
            ry = rx * (0.22 + 0.10 * depth)
            # shallow bowl: soft shadowed floor, sunlit far wall
            bowl = QRadialGradient(QPointF(x, y - ry * 0.3), rx)
            bowl.setColorAt(0.0, tint("#000000", 0.24))
            bowl.setColorAt(1.0, tint("#000000", 0.04))
            painter.setBrush(QBrush(bowl))
            painter.drawEllipse(QPointF(x, y), rx, ry)
            painter.setPen(QPen(tint(INK, 0.10), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(x - rx, y - ry, rx * 2, ry * 2), 200 * 16, 140 * 16)
            painter.setPen(Qt.PenStyle.NoPen)
        painter.restore()

        # earthshine catching the limb, brightest under Earth
        rim = QLinearGradient(0, 0, width, 0)
        rim.setColorAt(0.0, tint(MOONLIGHT, 0.04))
        rim.setColorAt(0.70, tint(MOONLIGHT, 0.34))
        rim.setColorAt(1.0, tint(MOONLIGHT, 0.12))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QBrush(rim), 1.2))
        painter.drawPath(surface)
        painter.setPen(QPen(QBrush(rim), 7.0))
        painter.setOpacity(0.10)
        painter.drawPath(surface)
        painter.setOpacity(1.0)

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
        if self._frost is None:
            return False
        dpr = self._sky_dpr
        src = QRectF(source.x() * dpr, source.y() * dpr,
                     source.width() * dpr, source.height() * dpr)
        painter.drawPixmap(target, self._frost, src)
        return True

    # -- per-frame ----------------------------------------------------------
    def _tick(self) -> None:
        if not self.isVisible() or self.width() <= 0:
            return
        window = self.window()
        if window is not None and window.isMinimized():
            return

        elapsed = time.monotonic() - self._t0
        self._phase = elapsed
        width = self.width()

        # Card geometry only changes on resize or page switch, and stars drift a
        # few px per second, so which stars sit behind glass is re-decided twice
        # a second rather than tested every frame.
        recheck = self._covered_age <= 0
        if recheck:
            self._covered = self._covered_rects()
            self._covered_age = 15
        self._covered_age -= 1

        for index, star in enumerate(self._live):
            star["x"] = (star["x0"] + star["vx"] * elapsed) % width
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
        if self._sky is None or self._sky.isNull():
            self._render_sky()

        # Qt clips the painter to the damaged region, so blitting its bounding
        # rect only writes the pixels that actually changed.
        damaged = event.rect()
        region = event.region()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._blit_sky(painter, damaged)
        earth = self._earth_rect
        for star, rect in zip(self._live, self._rects):
            if rect.isNull():  # not placed by a tick yet
                rect = self._star_rect(star)
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
    """Liquid-glass slab with a body layout and optional section header."""

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

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_liquid_glass(painter, self, self._radius)


class GlassCapsule(QWidget):
    """Floating glass capsule, as used for iOS toolbars and status groups."""

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_liquid_glass(painter, self, self.height() / 2.0)


# ---------------------------------------------------------------------------
# PillButton
# ---------------------------------------------------------------------------

class PillButton(QPushButton):
    """Capsule button with an animated hover lift.

    variant: 'primary' (accent glass), 'secondary' (clear glass + rim),
             'ghost' (plain, for use inside a glass capsule).
    Pass `glyph` for a painted icon; with no text the button is a circle.
    `set_active(True)` latches an accent tint, for toggles.
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
            paint_glyph(painter, self._glyph, glyph_rect, content,
                        width=1.6 if self._compact else 1.8)
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
# StatusPill
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
        self._state = state
        if caption is not None:
            self.setText(caption)
        self._sync_timer()
        self.updateGeometry()
        self.update()

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

        color = QColor(state_color(self._state))
        center = QPointF(rect.left() + (8 if self._flat else 15), rect.center().y())
        if self._is_pulsing():
            pulse = (time.monotonic() / self.PULSE_PERIOD) % 1.0
            halo = 3.0 + 5.0 * pulse
            painter.setPen(Qt.PenStyle.NoPen)
            fade = QColor(color)
            fade.setAlphaF(0.34 * (1.0 - pulse))
            painter.setBrush(QBrush(fade))
            painter.drawEllipse(center, halo, halo)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, 3.8, 3.8)

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


# ---------------------------------------------------------------------------
# VideoSurface
# ---------------------------------------------------------------------------

class VideoSurface(QLabel):
    """QLabel that paints its pixmap letterboxed inside a rounded frame.

    Stays a QLabel so the existing `setPixmap` / `size()` feed code is unchanged.
    Emits `clicked` on a left click, used to swap the hero and inset feeds.
    """

    clicked = pyqtSignal()

    def __init__(self, placeholder: str = "", parent: QWidget | None = None,
                 radius: int = RADIUS_VIDEO):
        super().__init__(parent)
        self._placeholder = placeholder
        self._radius = radius
        self.setMinimumSize(160, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFont(app_font(13, QFont.Weight.Medium))

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
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
        painter.setClipping(False)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(tint(INK, 0.10), 1.0))
        painter.drawPath(path)


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
    font's empty ascent and descent space into the layout.
    Label-compatible: setText() / text().
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

    def setText(self, text: str) -> None:
        self._text = str(text)
        self.updateGeometry()
        self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, hex_color: str, alpha: float = 0.96) -> None:
        self._color = tint(hex_color, alpha)
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


# ---------------------------------------------------------------------------
# KeyCaps
# ---------------------------------------------------------------------------

class KeyCaps(QWidget):
    """W / A S D key caps that press down and light up while held."""

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
        self._font = app_font(13, QFont.Weight.DemiBold)
        self._timer = QTimer(self)
        self._timer.setInterval(self.FRAME_MS)
        self._timer.timeout.connect(self._animate)

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
        if row == 0:
            x = 1 + step  # W sits above S
        else:
            x = 1 + col * step
        y = 1 + row * step
        return QRectF(x, y, self.CAP, self.CAP)

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
                side = base.translated(0, self.DEPTH)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(tint("#000000", 0.45)))
                painter.drawRoundedRect(side, radius, radius)

                face = base.translated(0, self.DEPTH * level)
                if level > 0.01:
                    glow = QRadialGradient(face.center(), self.CAP * 0.95)
                    glow.setColorAt(0.0, tint(ACCENT_LIGHT, 0.32 * level))
                    glow.setColorAt(1.0, tint(ACCENT_LIGHT, 0.0))
                    painter.setBrush(QBrush(glow))
                    painter.drawEllipse(face.center(), self.CAP * 0.95, self.CAP * 0.95)

                fill = QLinearGradient(face.topLeft(), face.bottomLeft())
                idle_top, idle_bottom = tint(INK, 0.14), tint(INK, 0.07)
                lit_top, lit_bottom = QColor(ACCENT).lighter(118), QColor(ACCENT)
                fill.setColorAt(0.0, self._mix(idle_top, lit_top, level))
                fill.setColorAt(1.0, self._mix(idle_bottom, lit_bottom, level))
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

    def set_command(self, command: str) -> None:
        self._command = (command or "S").upper()
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
        stopped = not (forward or back)

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
            color = tint(ACCENT_LIGHT, 0.95) if active else tint(INK, 0.18)
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
                glow.setColorAt(0.0, tint(ACCENT_LIGHT, 0.26))
                glow.setColorAt(1.0, tint(ACCENT_LIGHT, 0.0))
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPointF(0.0, tip_y + reach * 0.08), reach * 0.52, reach * 0.52)
            painter.restore()

        hub = tint(WARN, 0.92) if stopped else tint(ACCENT_LIGHT, 0.92)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint(INK, 0.07)))
        painter.drawEllipse(center, reach * 0.30, reach * 0.30)
        painter.setBrush(QBrush(hub))
        painter.drawEllipse(center, reach * 0.13, reach * 0.13)


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
    border-radius: {RADIUS_FIELD + 6}px;
    color: #6B7280;
    font-size: 12px;
}}
QLineEdit {{
    background-color: {css(INK, 0.08)};
    color: {css(INK, 0.96)};
    border: 1px solid {css(INK, 0.14)};
    border-radius: {RADIUS_FIELD}px;
    padding: 12px 16px;
    font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 15px;
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
    background-color: #161B28;
    color: {css(INK, 0.94)};
    border: 1px solid {css(INK, 0.16)};
    border-radius: 10px;
    padding: 7px 10px;
    font-family: "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 12px;
}}
QMessageBox {{
    background-color: #0B0F1A;
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
    background-color: #0B0F1A;
}}
"""
