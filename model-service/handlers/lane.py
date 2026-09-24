"""Lane marking detection (Polyline) — CPU-only classical computer vision.

Why classical CV and not a network
----------------------------------
The guideline's seven ``lane/*`` classes come from BDD100K, but no public
checkpoint predicts them, and this repo owns zero lane annotations (both
``train/1354`` and ``train/1571`` contain none). A learned model was therefore
not an option; a deterministic pipeline that needs no training data was.

Everything happens in metres, not pixels
----------------------------------------
In a dashcam frame the same 0.15 m lane line is ~40 px wide 3 m ahead and ~3 px
wide 25 m ahead, so ``dx/dX = f / Z`` varies by more than 10x across one frame.
A fixed pixel kernel is therefore wrong somewhere by construction: a 21 px
top-hat element fits *inside* a near-field line and returns zero, shredding it
into slivers. That failure is not a tuning problem, it is a units problem.

The fix is to resample the road onto a top-down metric raster ("bird view") and
do all morphology and all geometry there, converting back to pixels only when
writing the answer. Under the flat-ground pinhole model::

    Z = f * h / (y - vy)            distance ahead, metres
    X = (x - vx) * h / (y - vy)     lateral offset, metres

``f`` cancels out of ``X``, so lateral measurements -- which decide single vs
double -- need only the camera height and the horizon row, no calibration.

Pipeline
--------
1. Whiteness and yellowness score maps in image space (per-pixel colour).
2. Warp both onto a bird view at a fixed pixels-per-metre.
3. Black top-hat with metric kernels: fine keeps lane lines, coarse keeps the
   wider crosswalk bars. Top-hat removes the smooth background, which is what
   makes night frames and shadows survivable without retuning.
4. Connected components on the bird raster, then metric PCA per component.
5. Classify: colour by pixel vote on hue/saturation, geometry from the PCA,
   doubles from ridge counting plus parallel pairing.
6. Ordered centreline per marking, mapped back to pixels, Douglas-Peucker.

Scope and deliberate limitations (reported in the payload, not hidden)
----------------------------------------------------------------------
* The detector sees a cone of +/-LANE_ROI_HALF_RATIO (by default about +/-2.9 m)
  around the camera axis -- the ego lane and its immediate neighbours. Markings
  further out are off the modelled road plane.
* ``lane/road curb`` is off by default (``LANE_CURB_ENABLED``): a curb is a
  depth edge, not a bright marking, and a pure-CV detector for it produced
  mostly false positives on the test set.
* ``lane/double *`` needs the two stripes resolved. Beyond roughly 12-15 m they
  fall below one pixel apart and are emitted as single.
* Worn or fully occluded markings below the local contrast floor are missed.
  This is a review aid, not a replacement for annotation.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from typing import Any

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LaneConfig:
    """Tunables. Every field is overridable through a ``LANE_*`` env var."""

    # --- ground-plane geometry (assumed, not calibrated) -------------------
    horizon_ratio: float = 0.48      # vanishing-point row / image height
    focal_ratio: float = 0.625       # f / image width  (~77 deg HFOV at 16:9)
    camera_height_m: float = 1.35    # dashcam height above the road
    roi_half_ratio: float = 0.62     # lateral half-cone, as a fraction of width
    min_depth_m: float = 2.5
    # 12 m, not 20 or 30. The bird raster upsamples by (Z^2 / (f*h)) * ppm rows
    # per image row: at 20 m that is ~15x, so a single bright noisy pixel near
    # the horizon is stretched into a one-metre-long blob and reads as a
    # marking. Capping at 12 m holds the stretch under ~5x, which removed most
    # of the false positives clustered at the vanishing point. The cost is real:
    # markings are only traced over roughly the bottom 40% of the frame.
    max_depth_m: float = 12.0

    # --- bird view ---------------------------------------------------------
    bird_ppm: float = 40.0           # pixels per metre in the top-down raster

    # --- segmentation ------------------------------------------------------
    # Whiteness and yellowness live on different scales -- a white line scores
    # ~0.9, a yellow line ~0.25 -- so each gets its own threshold. A single
    # shared threshold silently drops every yellow marking.
    yellow_hue_center: float = 27.0  # OpenCV hue units (0-179); yellow ~ 25-30
    yellow_hue_sigma: float = 11.0
    yellow_min_sat: float = 0.22     # gate: below this hue is meaningless
    tophat_fine_m: float = 0.30      # kernel width, lane lines
    tophat_coarse_m: float = 0.85    # kernel width, crosswalk bars
    threshold_fine: int = 45         # top-hat response, 0-255, white
    threshold_coarse: int = 60
    # The yellow channel is intrinsically weak: a bright yellow line scores only
    # ~0.25 where a white line scores ~0.9, and after the denoise its top-hat
    # peak lands near 30. A threshold tuned for the white channel would erase
    # every yellow marking, so these sit much lower on purpose.
    threshold_yellow: int = 18
    threshold_yellow_coarse: int = 24
    preblur_sigma_px: float = 1.2    # bird-raster denoise; a lane line is ~6 px
    close_m: float = 0.12            # bridge pinholes along a line, but not the
                                     # gap inside a double (that is ~0.15-0.3 m)

    # --- colour decision (per component, by pixel vote) --------------------
    classify_white_max_sat: float = 0.22
    classify_white_min_value: float = 0.45
    classify_yellow_min_sat: float = 0.28
    classify_hue_min: float = 15.0
    classify_hue_max: float = 45.0
    classify_min_vote: float = 0.35  # else the marking is reported as "other"

    # --- component acceptance (metres) -------------------------------------
    min_component_area_m2: float = 0.06
    min_length_m: float = 1.0
    min_elongation: float = 3.0
    max_single_width_m: float = 0.45  # above this a marking is not one line
    # A double line measured as a single merged blob is ~0.45-0.55 m across, so
    # rejecting everything above max_single_width_m would throw away exactly the
    # doubles this module is trying to find. Only reject past the widest
    # plausible pair; the ridge test decides what it actually is.
    max_pair_width_m: float = 0.85

    # --- doubles -----------------------------------------------------------
    double_gap_min_m: float = 0.22
    double_gap_max_m: float = 0.65
    double_gap_tol_m: float = 0.14   # max spread of the gap along the pair
    double_max_angle_deg: float = 12.0
    ridge_min_run_m: float = 0.09    # a ridge thinner than this is noise
    ridge_min_gap_m: float = 0.10    # a gap thinner than this is not a gap

    # --- crosswalk ---------------------------------------------------------
    crosswalk_enabled: bool = True
    crosswalk_min_stripes: int = 3
    crosswalk_stripe_width_min_m: float = 0.25
    crosswalk_stripe_width_max_m: float = 1.3
    crosswalk_stripe_min_len_m: float = 1.2
    crosswalk_depth_tol_m: float = 2.0
    # The coarse channel bridges the 0.6-0.9 m gaps between zebra bars, so a
    # crosswalk often arrives as one wide lateral band instead of N stripes.
    # Accept that signature too, but only close in, where a wide bright band
    # across the road is unambiguous (a stop line is far narrower).
    crosswalk_merged_min_len_m: float = 2.0
    crosswalk_merged_min_width_m: float = 1.5
    crosswalk_merged_max_depth_m: float = 12.0

    # --- curb (off by default, see module docstring) -----------------------
    curb_enabled: bool = False
    curb_min_length_m: float = 3.0
    curb_min_lateral_m: float = 1.6

    # --- output ------------------------------------------------------------
    max_marks: int = 120
    simplify_eps_px: float = 2.0

    @classmethod
    def from_env(cls) -> "LaneConfig":
        base = cls()
        return replace(
            base,
            horizon_ratio=_env_float("LANE_HORIZON_RATIO", base.horizon_ratio),
            focal_ratio=_env_float("LANE_FOCAL_RATIO", base.focal_ratio),
            camera_height_m=_env_float("LANE_CAMERA_HEIGHT_M", base.camera_height_m),
            roi_half_ratio=_env_float("LANE_ROI_HALF_RATIO", base.roi_half_ratio),
            min_depth_m=_env_float("LANE_MIN_DEPTH_M", base.min_depth_m),
            max_depth_m=_env_float("LANE_MAX_DEPTH_M", base.max_depth_m),
            bird_ppm=_env_float("LANE_BIRD_PPM", base.bird_ppm),
            yellow_hue_center=_env_float("LANE_YELLOW_HUE_CENTER", base.yellow_hue_center),
            yellow_hue_sigma=_env_float("LANE_YELLOW_HUE_SIGMA", base.yellow_hue_sigma),
            yellow_min_sat=_env_float("LANE_YELLOW_MIN_SAT", base.yellow_min_sat),
            tophat_fine_m=_env_float("LANE_TOPHAT_FINE_M", base.tophat_fine_m),
            tophat_coarse_m=_env_float("LANE_TOPHAT_COARSE_M", base.tophat_coarse_m),
            threshold_fine=_env_int("LANE_THRESHOLD_FINE", base.threshold_fine),
            threshold_coarse=_env_int("LANE_THRESHOLD_COARSE", base.threshold_coarse),
            threshold_yellow=_env_int("LANE_THRESHOLD_YELLOW", base.threshold_yellow),
            threshold_yellow_coarse=_env_int(
                "LANE_THRESHOLD_YELLOW_COARSE", base.threshold_yellow_coarse
            ),
            preblur_sigma_px=_env_float("LANE_PREBLUR_SIGMA_PX", base.preblur_sigma_px),
            close_m=_env_float("LANE_CLOSE_M", base.close_m),
            classify_white_max_sat=_env_float(
                "LANE_CLASSIFY_WHITE_MAX_SAT", base.classify_white_max_sat
            ),
            classify_white_min_value=_env_float(
                "LANE_CLASSIFY_WHITE_MIN_VALUE", base.classify_white_min_value
            ),
            classify_yellow_min_sat=_env_float(
                "LANE_CLASSIFY_YELLOW_MIN_SAT", base.classify_yellow_min_sat
            ),
            classify_hue_min=_env_float("LANE_CLASSIFY_HUE_MIN", base.classify_hue_min),
            classify_hue_max=_env_float("LANE_CLASSIFY_HUE_MAX", base.classify_hue_max),
            classify_min_vote=_env_float("LANE_CLASSIFY_MIN_VOTE", base.classify_min_vote),
            min_component_area_m2=_env_float(
                "LANE_MIN_COMPONENT_AREA_M2", base.min_component_area_m2
            ),
            min_length_m=_env_float("LANE_MIN_LENGTH_M", base.min_length_m),
            min_elongation=_env_float("LANE_MIN_ELONGATION", base.min_elongation),
            max_single_width_m=_env_float("LANE_MAX_SINGLE_WIDTH_M", base.max_single_width_m),
            max_pair_width_m=_env_float("LANE_MAX_PAIR_WIDTH_M", base.max_pair_width_m),
            double_gap_min_m=_env_float("LANE_DOUBLE_GAP_MIN_M", base.double_gap_min_m),
            double_gap_max_m=_env_float("LANE_DOUBLE_GAP_MAX_M", base.double_gap_max_m),
            double_gap_tol_m=_env_float("LANE_DOUBLE_GAP_TOL_M", base.double_gap_tol_m),
            double_max_angle_deg=_env_float("LANE_DOUBLE_MAX_ANGLE_DEG", base.double_max_angle_deg),
            crosswalk_enabled=_env_bool("LANE_CROSSWALK_ENABLED", base.crosswalk_enabled),
            crosswalk_min_stripes=_env_int("LANE_CROSSWALK_MIN_STRIPES", base.crosswalk_min_stripes),
            crosswalk_stripe_min_len_m=_env_float(
                "LANE_CROSSWALK_STRIPE_MIN_LEN_M", base.crosswalk_stripe_min_len_m
            ),
            crosswalk_depth_tol_m=_env_float("LANE_CROSSWALK_DEPTH_TOL_M", base.crosswalk_depth_tol_m),
            crosswalk_merged_min_len_m=_env_float(
                "LANE_CROSSWALK_MERGED_MIN_LEN_M", base.crosswalk_merged_min_len_m
            ),
            crosswalk_merged_min_width_m=_env_float(
                "LANE_CROSSWALK_MERGED_MIN_WIDTH_M", base.crosswalk_merged_min_width_m
            ),
            crosswalk_merged_max_depth_m=_env_float(
                "LANE_CROSSWALK_MERGED_MAX_DEPTH_M", base.crosswalk_merged_max_depth_m
            ),
            curb_enabled=_env_bool("LANE_CURB_ENABLED", base.curb_enabled),
            curb_min_length_m=_env_float("LANE_CURB_MIN_LENGTH_M", base.curb_min_length_m),
            curb_min_lateral_m=_env_float("LANE_CURB_MIN_LATERAL_M", base.curb_min_lateral_m),
            max_marks=_env_int("LANE_MAX_MARKS", base.max_marks),
            simplify_eps_px=_env_float("LANE_SIMPLIFY_EPS_PX", base.simplify_eps_px),
        )


# ---------------------------------------------------------------------------
# Ground plane and bird view
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GroundPlane:
    """Flat-road pinhole model: image pixels <-> road metres.

    ``focal`` and ``camera_height`` only ever appear as the product
    ``focal * camera_height`` in the depth equation and as ``camera_height``
    alone in the lateral equation, so an approximate focal length degrades the
    depth estimate but leaves lateral distances -- which is what the single vs
    double decision rests on -- correct.
    """

    vx: float
    vy: float
    focal: float
    cam_h: float
    width: int
    height: int

    @classmethod
    def from_config(cls, config: LaneConfig, width: int, height: int) -> "GroundPlane":
        return cls(
            vx=width / 2.0,
            vy=config.horizon_ratio * height,
            focal=config.focal_ratio * width,
            cam_h=config.camera_height_m,
            width=width,
            height=height,
        )

    def to_ground(self, x: Any, y: Any) -> tuple[np.ndarray, np.ndarray]:
        """Image pixels -> (lateral X metres, depth Z metres)."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        dz = np.maximum(y - self.vy, 1e-3)
        return (x - self.vx) * self.cam_h / dz, self.focal * self.cam_h / dz

    def to_image(self, lateral: Any, depth: Any) -> tuple[np.ndarray, np.ndarray]:
        """(lateral X metres, depth Z metres) -> image pixels."""
        lateral = np.asarray(lateral, dtype=np.float64)
        depth = np.maximum(np.asarray(depth, dtype=np.float64), 1e-3)
        y = self.vy + self.focal * self.cam_h / depth
        x = self.vx + lateral * self.focal / depth
        return x, y

    def depth_at_bottom(self) -> float:
        """Depth of the last image row; nothing nearer is visible."""
        return self.focal * self.cam_h / max(self.height - self.vy, 1e-3)

    def lateral_limit(self, config: LaneConfig) -> float:
        """Half-width of the modelled road cone, in metres.

        Constant with depth: the ROI is bounded by the two lines through the
        vanishing point and the bottom corners, so its metric half-width does
        not depend on how far ahead you look.
        """
        return config.roi_half_ratio * self.width * self.cam_h / max(self.height - self.vy, 1e-3)

    def roi_polygon(self, config: LaneConfig) -> np.ndarray:
        """The road cone, as an image-space trapezoid."""
        y_top = self.vy + self.focal * self.cam_h / config.max_depth_m
        y_bottom = float(self.height)
        half_bottom = config.roi_half_ratio * self.width
        span = max(y_bottom - self.vy, 1e-3)
        half_top = half_bottom * max(y_top - self.vy, 0.0) / span
        return np.array(
            [
                [self.vx - half_top, y_top],
                [self.vx + half_top, y_top],
                [self.vx + half_bottom, y_bottom],
                [self.vx - half_bottom, y_bottom],
            ],
            dtype=np.int32,
        )


@dataclass(frozen=True)
class BirdView:
    """Top-down metric raster of the modelled road plane.

    ``col`` runs left to right in metres, ``row`` runs far to near, so the
    raster is a plain metric image: one pixel is always ``1/ppm`` metres in
    both axes, at every distance. That is what lets every kernel size, area
    and gap in this module be written in metres.
    """

    ppm: float
    x_max: float
    z_min: float
    z_max: float
    cols: int
    rows: int

    @classmethod
    def from_config(cls, config: LaneConfig, plane: GroundPlane) -> "BirdView":
        # Nothing nearer than the last image row exists, so never ask for it:
        # the remap would sample outside the source and return zeros.
        z_min = max(config.min_depth_m, plane.depth_at_bottom())
        x_max = plane.lateral_limit(config)
        return cls(
            ppm=config.bird_ppm,
            x_max=x_max,
            z_min=z_min,
            z_max=config.max_depth_m,
            cols=max(8, int(round(2.0 * x_max * config.bird_ppm))),
            rows=max(8, int(round((config.max_depth_m - z_min) * config.bird_ppm))),
        )

    # -- metric <-> raster --------------------------------------------------

    def lateral_of(self, cols: np.ndarray) -> np.ndarray:
        return cols / self.ppm - self.x_max

    def depth_of(self, rows: np.ndarray) -> np.ndarray:
        return self.z_max - rows / self.ppm

    def col_of(self, lateral: np.ndarray) -> np.ndarray:
        return (lateral + self.x_max) * self.ppm

    def row_of(self, depth: np.ndarray) -> np.ndarray:
        return (self.z_max - depth) * self.ppm

    def metres(self, pixels: float) -> float:
        return pixels / self.ppm

    def pixels(self, metres: float) -> int:
        return max(3, int(round(metres * self.ppm)) | 1)

    def remap_grid(self, plane: GroundPlane) -> tuple[np.ndarray, np.ndarray]:
        """Source-image coordinates for every bird pixel, for ``cv2.remap``."""
        cols = np.arange(self.cols, dtype=np.float64)
        rows = np.arange(self.rows, dtype=np.float64)
        lateral = self.lateral_of(cols)[None, :]
        depth = self.depth_of(rows)[:, None]
        px, py = plane.to_image(np.broadcast_to(lateral, (self.rows, self.cols)),
                                np.broadcast_to(depth, (self.rows, self.cols)))
        return px.astype(np.float32), py.astype(np.float32)


# ---------------------------------------------------------------------------
# Stage 1-3: segmentation on the bird raster
# ---------------------------------------------------------------------------

def _score_maps(hsv: np.ndarray, config: LaneConfig) -> tuple[np.ndarray, np.ndarray]:
    """Whiteness and yellowness response maps, from an HSV image.

    ``white = V * (1 - S)`` peaks on bright, desaturated paint and reaches ~0.9
    on a clean white line. ``yellow = V * S * hue_window`` peaks on saturated
    paint in the yellow band and reaches only ~0.25 on a yellow line, because a
    bright yellow is also fairly light. The two are therefore never compared
    directly; see ``_classify_colour``.
    """
    hue = hsv[..., 0].astype(np.float32)
    sat = hsv[..., 1].astype(np.float32) / 255.0
    val = hsv[..., 2].astype(np.float32) / 255.0

    white = val * (1.0 - sat)

    delta = np.abs(hue - config.yellow_hue_center)
    delta = np.minimum(delta, 180.0 - delta)  # OpenCV hue wraps at 180
    window = np.exp(-0.5 * (delta / max(config.yellow_hue_sigma, 1e-6)) ** 2)
    yellow = val * sat * window
    yellow[sat < config.yellow_min_sat] = 0.0

    return white, yellow


def _tophat(score: np.ndarray, kernel_px: int) -> np.ndarray:
    """Black top-hat: keeps bright structures narrower than the kernel."""
    size = max(3, kernel_px | 1)  # force odd
    element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    return cv2.morphologyEx((score * 255.0).astype(np.uint8), cv2.MORPH_TOPHAT, element)


def _bird_rasters(
    rgb: np.ndarray,
    config: LaneConfig,
    plane: GroundPlane,
    bird: BirdView,
) -> dict[str, Any]:
    """Warp the colour scores onto the bird view and threshold them there."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    white, yellow = _score_maps(hsv, config)

    map_x, map_y = bird.remap_grid(plane)
    white_bird = cv2.remap(white, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    yellow_bird = cv2.remap(yellow, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    # Denoise *after* the warp, never before. On the bird raster a lane line is
    # the same ~6 px at every distance, so one small kernel suppresses speckle
    # without touching the line. Blurring in image space instead would wipe out
    # the far field, where the same line is only 3 px wide.
    if config.preblur_sigma_px > 0:
        size = int(round(config.preblur_sigma_px * 4)) | 1
        element = (size, size)
        white_bird = cv2.GaussianBlur(white_bird, element, config.preblur_sigma_px)
        yellow_bird = cv2.GaussianBlur(yellow_bird, element, config.preblur_sigma_px)

    fine_px = bird.pixels(config.tophat_fine_m)
    coarse_px = bird.pixels(config.tophat_coarse_m)

    white_fine = _tophat(white_bird, fine_px)
    yellow_fine = _tophat(yellow_bird, fine_px)
    white_coarse = _tophat(white_bird, coarse_px)
    yellow_coarse = _tophat(yellow_bird, coarse_px)

    fine_mark = (white_fine >= config.threshold_fine) | (yellow_fine >= config.threshold_yellow)
    coarse_mark = (
        (white_coarse >= config.threshold_coarse)
        | (yellow_coarse >= config.threshold_yellow_coarse)
    )
    mark = fine_mark | coarse_mark

    # Three masks, each with one job.
    #   `mask_fine`  fine channel only -- what the ridge counter reads, because
    #                the coarse channel bridges the 0.15-0.3 m gap inside a
    #                double line and would report it as one solid ridge.
    #   `mask_raw`   everything, still full of pinholes.
    #   `mask`       everything, closed, so a marking is one component.
    open_element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    fine_raw_u8 = cv2.morphologyEx(fine_mark.astype(np.uint8) * 255, cv2.MORPH_OPEN, open_element)
    raw_u8 = cv2.morphologyEx(mark.astype(np.uint8) * 255, cv2.MORPH_OPEN, open_element)
    closed_u8 = cv2.morphologyEx(
        raw_u8,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bird.pixels(config.close_m),) * 2),
    )

    return {
        "hsv": hsv,
        "mask": closed_u8 > 0,
        "mask_raw": raw_u8 > 0,
        "mask_fine": fine_raw_u8 > 0,
        "thresholds_px": {"fine": fine_px, "coarse": coarse_px},
    }


# ---------------------------------------------------------------------------
# Stage 3: per-component metric analysis (all in bird coordinates)
# ---------------------------------------------------------------------------

@dataclass
class _Candidate:
    """One marking candidate measured on the road plane."""

    color: str                       # 'white' | 'yellow' | 'other'
    colour_margin: float
    lateral_m: np.ndarray            # centreline lateral, metres
    depth_m: np.ndarray              # centreline depth, metres
    length_m: float
    width_m: float
    elongation: float
    orientation: str                 # 'longitudinal' | 'lateral' | 'oblique'
    ridges: int
    confidence: float
    evidence: dict[str, Any]

    def lateral_at(self, depths: np.ndarray) -> np.ndarray | None:
        """Interpolate lateral offset onto arbitrary depths, or None."""
        order = np.argsort(self.depth_m)
        z = self.depth_m[order]
        if z.size < 2 or z[-1] - z[0] < 1e-6:
            return None
        inside = (depths >= z[0]) & (depths <= z[-1])
        if not inside.any():
            return None
        out = np.full(depths.shape, np.nan)
        out[inside] = np.interp(depths[inside], z, self.lateral_m[order])
        return out


def _classify_colour(
    hsv: np.ndarray, ys: np.ndarray, xs: np.ndarray, config: LaneConfig
) -> tuple[str, float]:
    """Decide white vs yellow by voting on saturation and hue.

    Comparing the two score maps directly misclassifies yellow: bright yellow
    paint is light as well as saturated, so it scores ~0.28 on whiteness against
    ~0.24 on yellowness and loses. Hue -- which is what "yellow" actually means
    -- separates them cleanly; saturation guards the case where hue is just
    noise on a near-grey pixel.
    """
    hue = hsv[ys, xs, 0].astype(np.float32)
    sat = hsv[ys, xs, 1].astype(np.float32) / 255.0
    val = hsv[ys, xs, 2].astype(np.float32) / 255.0

    yellow_vote = (sat >= config.classify_yellow_min_sat) & (
        (hue >= config.classify_hue_min) & (hue <= config.classify_hue_max)
    )
    white_vote = (sat <= config.classify_white_max_sat) & (val >= config.classify_white_min_value)

    total = float(max(len(hue), 1))
    yellow_fraction = float(np.count_nonzero(yellow_vote)) / total
    white_fraction = float(np.count_nonzero(white_vote)) / total

    if white_fraction >= config.classify_min_vote and white_fraction >= yellow_fraction:
        return "white", white_fraction
    if yellow_fraction >= config.classify_min_vote and yellow_fraction > white_fraction:
        return "yellow", yellow_fraction
    return "other", max(white_fraction, yellow_fraction)


def _count_ridges(
    lateral: np.ndarray,
    depth: np.ndarray,
    mask: np.ndarray,
    bird: BirdView,
    config: LaneConfig,
) -> tuple[int, float]:
    """Count bright ridges across the marking, perpendicular to it.

    Returns ``(median ridge count, median ridge pitch)``. Two ridges separated
    by a real gap is the signature of a double line; a single line yields one.
    Sampling on the bird raster means the step is a fixed number of centimetres
    at every distance, so the smallest resolvable gap does not drift.
    """
    order = np.argsort(depth)
    z_line = depth[order]
    x_line = lateral[order]
    if z_line.size < 2:
        return 1, 0.0

    span = np.linspace(0.25, 0.75, 5)  # avoid the ends, where the fit is weakest
    counts: list[int] = []
    pitches: list[float] = []
    offsets = np.arange(-1.1, 1.1 + 1e-9, 0.02)
    step = float(offsets[1] - offsets[0])

    for fraction in span:
        z0 = float(z_line[0] + fraction * (z_line[-1] - z_line[0]))
        x0 = float(np.interp(z0, z_line, x_line))
        x_before = float(np.interp(max(z0 - 0.5, z_line[0]), z_line, x_line))
        x_after = float(np.interp(min(z0 + 0.5, z_line[-1]), z_line, x_line))
        tangent = np.array([x_after - x_before, 1.0])
        tangent /= np.linalg.norm(tangent)
        normal = np.array([tangent[1], -tangent[0]])

        cols = np.rint(bird.col_of(x0 + offsets * normal[0])).astype(np.int64)
        rows = np.rint(bird.row_of(z0 + offsets * normal[1])).astype(np.int64)
        inside = (cols >= 0) & (cols < bird.cols) & (rows >= 0) & (rows < bird.rows)
        if inside.sum() < 8:
            continue
        profile = np.zeros(offsets.shape, dtype=bool)
        profile[inside] = mask[rows[inside], cols[inside]]

        runs: list[list[float]] = []
        start: int | None = None
        for index, hit in enumerate(profile):
            if hit and start is None:
                start = index
            elif not hit and start is not None:
                runs.append([start * step, (index - 1) * step])
                start = None
        if start is not None:
            runs.append([start * step, (len(profile) - 1) * step])

        merged: list[list[float]] = []
        for run in (r for r in runs if (r[1] - r[0]) >= config.ridge_min_run_m):
            if merged and (run[0] - merged[-1][1]) <= config.ridge_min_gap_m:
                merged[-1][1] = run[1]
            else:
                merged.append(run)

        counts.append(len(merged))
        if len(merged) == 2:
            pitches.append(
                (merged[1][0] + merged[1][1]) / 2 - (merged[0][0] + merged[0][1]) / 2
            )

    if not counts:
        return 1, 0.0
    return int(np.median(counts)), float(np.median(pitches)) if pitches else 0.0


def _extract_candidates(
    rasters: dict[str, Any],
    plane: GroundPlane,
    bird: BirdView,
    config: LaneConfig,
) -> tuple[list[_Candidate], dict[str, int]]:
    """Bird-raster components -> metric candidates."""
    mask = rasters["mask"]
    mask_fine = rasters["mask_fine"]
    num, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )

    min_area_px = config.min_component_area_m2 * bird.ppm * bird.ppm
    hsv = rasters["hsv"]
    candidates: list[_Candidate] = []
    rejected = {"area": 0, "length": 0, "elongation": 0, "width": 0}

    for index in range(1, num):
        x0, y0, bw, bh, area = (int(v) for v in stats[index])
        if area < min_area_px:
            rejected["area"] += 1
            continue

        sub = labels[y0 : y0 + bh, x0 : x0 + bw] == index
        rows, cols = np.nonzero(sub)
        cols = cols + x0
        rows = rows + y0

        lateral = bird.lateral_of(cols.astype(np.float64))
        depth = bird.depth_of(rows.astype(np.float64))
        if depth.max() < config.min_depth_m or depth.min() > config.max_depth_m:
            continue

        points = np.column_stack([lateral, depth])
        mean = points.mean(axis=0)
        centered = points - mean
        # PCA in metric ground coordinates: lanes are straight and parallel here.
        cov = centered.T @ centered / max(len(centered) - 1, 1)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        axis = eigenvectors[:, int(np.argmax(eigenvalues))]
        normal = np.array([-axis[1], axis[0]])

        along = centered @ axis
        across = centered @ normal
        length_m = float(along.max() - along.min())
        width_m = float(across.max() - across.min())
        elongation = length_m / max(width_m, 1e-3)

        if length_m < config.min_length_m:
            rejected["length"] += 1
            continue
        if elongation < config.min_elongation:
            rejected["elongation"] += 1
            continue

        # Longitudinal = principal axis along Z; lateral = along X.
        angle_deg = float(np.degrees(np.arctan2(abs(axis[1]), abs(axis[0]))))
        if angle_deg >= 55.0:
            orientation = "longitudinal"
        elif angle_deg <= 35.0:
            orientation = "lateral"
        else:
            orientation = "oblique"
        if orientation == "longitudinal" and width_m > config.max_pair_width_m:
            rejected["width"] += 1
            continue

        # Ordered centreline: median perpendicular offset per bin along the axis.
        order = np.argsort(along)
        along_sorted = along[order]
        across_sorted = across[order]
        bins = int(np.clip(length_m / 0.6, 2, 24))
        edges = np.linspace(along_sorted[0], along_sorted[-1], bins + 1)
        centre_along: list[float] = []
        centre_across: list[float] = []
        for low, high in zip(edges[:-1], edges[1:]):
            if high <= low:
                continue
            selected = (along_sorted >= low) & (along_sorted <= high)
            if not selected.any():
                continue
            centre_along.append(float(np.median(along_sorted[selected])))
            centre_across.append(float(np.median(across_sorted[selected])))
        if len(centre_along) < 2:
            rejected["length"] += 1
            continue

        line_ground = mean + np.outer(centre_along, axis) + np.outer(centre_across, normal)

        ridges, pitch = _count_ridges(line_ground[:, 0], line_ground[:, 1], mask_fine, bird, config)

        # Colour is decided on the original pixels under the marking -- the
        # centreline resampled densely -- so it uses the hue the eye sees rather
        # than a resampled raster. Only the spine is probed, never the edges,
        # which are blended with asphalt and would drag saturation down.
        probe_ground = mean + np.outer(np.linspace(along.min(), along.max(), 48), axis)
        probe_x, probe_y = plane.to_image(probe_ground[:, 0], probe_ground[:, 1])
        probe_x = np.clip(np.rint(probe_x).astype(np.int64), 0, plane.width - 1)
        probe_y = np.clip(np.rint(probe_y).astype(np.int64), 0, plane.height - 1)
        colour, colour_margin = _classify_colour(hsv, probe_y, probe_x, config)

        confidence = _confidence(
            length_m=length_m,
            width_m=width_m,
            elongation=elongation,
            colour_margin=colour_margin,
            ridges=ridges,
            config=config,
        )
        candidates.append(
            _Candidate(
                color=colour,
                colour_margin=colour_margin,
                lateral_m=line_ground[:, 0],
                depth_m=line_ground[:, 1],
                length_m=length_m,
                width_m=width_m,
                elongation=elongation,
                orientation=orientation,
                ridges=ridges,
                confidence=confidence,
                evidence={
                    "colour": colour,
                    "colour_vote": round(colour_margin, 3),
                    "length_m": round(length_m, 3),
                    "width_m": round(width_m, 3),
                    "elongation": round(elongation, 2),
                    "orientation": orientation,
                    "ridges": ridges,
                    "ridge_pitch_m": round(pitch, 3) if pitch else None,
                    "depth_range_m": [round(float(depth.min()), 2), round(float(depth.max()), 2)],
                    "area_m2": round(float(area) / (bird.ppm * bird.ppm), 3),
                },
            )
        )

    return candidates, rejected


def _confidence(
    *,
    length_m: float,
    width_m: float,
    elongation: float,
    colour_margin: float,
    ridges: int,
    config: LaneConfig,
) -> float:
    """Heuristic 0.05-0.99 score; a review aid, not a probability."""
    length_score = float(np.clip(length_m / 6.0, 0.0, 1.0))
    elongation_score = float(np.clip(elongation / 8.0, 0.0, 1.0))
    if width_m <= config.max_single_width_m:
        width_score = 1.0
    else:
        width_score = float(np.clip(1.0 - (width_m - config.max_single_width_m) / 0.6, 0.0, 1.0))
    colour_score = float(np.clip(colour_margin / 0.5, 0.0, 1.0))
    ridge_score = 1.0 if ridges <= 2 else 0.6

    score = (
        0.34 * length_score
        + 0.24 * elongation_score
        + 0.18 * width_score
        + 0.14 * colour_score
        + 0.10 * ridge_score
    )
    return float(np.clip(0.05 + 0.94 * score, 0.05, 0.99))


# ---------------------------------------------------------------------------
# Stage 4: doubles and crosswalks
# ---------------------------------------------------------------------------

def _pair_doubles(
    candidates: list[_Candidate],
    plane: GroundPlane,
    config: LaneConfig,
) -> tuple[list[_Candidate], set[int]]:
    """Merge parallel same-colour neighbours into ``lane/double *``.

    Only longitudinal markings pair. A gap that stays constant along the pair is
    required, which is what separates a real double line from two unrelated
    markings that merely happen to be close at one end.
    """
    consumed: set[int] = set()
    doubles: list[_Candidate] = []

    longitudinal = [
        i for i, c in enumerate(candidates)
        if c.orientation == "longitudinal" and c.color in {"white", "yellow"} and c.length_m >= 1.5
    ]

    def direction(candidate: _Candidate) -> np.ndarray:
        order = np.argsort(candidate.depth_m)
        head = np.array([candidate.lateral_m[order[0]], candidate.depth_m[order[0]]])
        tail = np.array([candidate.lateral_m[order[-1]], candidate.depth_m[order[-1]]])
        vector = tail - head
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm > 1e-6 else np.array([1.0, 0.0])

    for position, i in enumerate(longitudinal):
        if i in consumed:
            continue
        for j in longitudinal[position + 1 :]:
            if j in consumed:
                continue
            a, b = candidates[i], candidates[j]
            if a.color != b.color:
                continue

            angle = float(np.degrees(np.arccos(
                np.clip(abs(float(np.dot(direction(a), direction(b)))), 0.0, 1.0)
            )))
            if angle > config.double_max_angle_deg:
                continue

            z_lo = max(a.depth_m.min(), b.depth_m.min())
            z_hi = min(a.depth_m.max(), b.depth_m.max())
            overlap = float(z_hi - z_lo)
            if overlap < max(1.0, 0.5 * min(a.length_m, b.length_m)):
                continue

            grid = np.linspace(z_lo, z_hi, 9)
            lateral_a = a.lateral_at(grid)
            lateral_b = b.lateral_at(grid)
            if lateral_a is None or lateral_b is None:
                continue
            both = ~(np.isnan(lateral_a) | np.isnan(lateral_b))
            if both.sum() < 5:
                continue
            gaps = np.abs(lateral_a[both] - lateral_b[both])
            gap = float(np.median(gaps))
            if not (config.double_gap_min_m <= gap <= config.double_gap_max_m):
                continue
            if float(gaps.std()) > config.double_gap_tol_m:
                continue

            grid_ok = grid[both]
            mid = (lateral_a[both] + lateral_b[both]) / 2.0
            gap_score = float(np.clip(
                1.0 - float(gaps.std()) / max(config.double_gap_tol_m, 1e-6), 0.0, 1.0
            ))
            doubles.append(
                _Candidate(
                    color=a.color,
                    colour_margin=min(a.colour_margin, b.colour_margin),
                    lateral_m=mid,
                    depth_m=grid_ok,
                    length_m=overlap,
                    width_m=gap,
                    elongation=overlap / max(gap, 1e-3),
                    orientation="longitudinal",
                    ridges=2,
                    confidence=float(np.clip(
                        min(a.confidence, b.confidence) * (0.82 + 0.17 * gap_score), 0.05, 0.99
                    )),
                    evidence={
                        "colour": a.color,
                        "length_m": round(overlap, 3),
                        "pair_gap_m": round(gap, 3),
                        "gap_std_m": round(float(gaps.std()), 4),
                        "angles_deg": round(angle, 2),
                        "paired_from": "two components",
                    },
                )
            )
            consumed.add(i)
            consumed.add(j)
            break

    return doubles, consumed


def _crosswalk_candidate(
    members: list[_Candidate], confidence: float, shape: str
) -> _Candidate:
    """Emit a zebra region as one open outline path.

    The guideline forces Polyline for every lane class, so a crosswalk -- which
    BDD100K stores as a closed polygon -- becomes the outline of its bounding
    rectangle, with the first point repeated at the end so the ring closes.
    """
    ground = np.vstack([np.column_stack([c.lateral_m, c.depth_m]) for c in members])
    corners = np.array([
        [ground[:, 0].min(), ground[:, 1].min()],
        [ground[:, 0].max(), ground[:, 1].min()],
        [ground[:, 0].max(), ground[:, 1].max()],
        [ground[:, 0].min(), ground[:, 1].max()],
    ])
    outline = np.vstack([corners, corners[:1]])
    lateral_span = float(np.ptp(ground[:, 0]))
    depth_span = float(np.ptp(ground[:, 1]))
    return _Candidate(
        color="white",
        colour_margin=float(np.mean([c.colour_margin for c in members])),
        lateral_m=outline[:, 0],
        depth_m=outline[:, 1],
        length_m=lateral_span,
        width_m=depth_span,
        elongation=lateral_span / max(depth_span, 1e-3),
        orientation="lateral",
        ridges=len(members),
        confidence=float(np.clip(confidence, 0.05, 0.99)),
        evidence={
            "stripes": len(members),
            "extent_lateral_m": round(lateral_span, 2),
            "extent_depth_m": round(depth_span, 2),
            "shape": shape,
        },
    )


def _detect_crosswalks(
    candidates: list[_Candidate], config: LaneConfig
) -> tuple[list[_Candidate], set[int]]:
    """Find crosswalk regions from two signatures."""
    if not config.crosswalk_enabled:
        return [], set()

    consumed: set[int] = set()
    crosswalks: list[_Candidate] = []

    # Signature A: one wide lateral band. The coarse top-hat channel bridges the
    # 0.6-0.9 m gaps between zebra bars, so a crosswalk normally arrives here
    # already merged rather than as N separate stripes. A stop line is far
    # narrower, which is what crosswalk_merged_min_width_m excludes.
    for index, candidate in enumerate(candidates):
        if (
            candidate.orientation == "lateral"
            and candidate.length_m >= config.crosswalk_merged_min_len_m
            and candidate.width_m >= config.crosswalk_merged_min_width_m
            and float(np.median(candidate.depth_m)) <= config.crosswalk_merged_max_depth_m
        ):
            crosswalks.append(_crosswalk_candidate(
                [candidate], candidate.confidence * 0.8, "merged zebra band"
            ))
            consumed.add(index)

    # Signature B: several separate bars sitting at the same depth.
    stripes = [
        i for i, c in enumerate(candidates)
        if i not in consumed
        and c.orientation == "lateral"
        and c.length_m >= config.crosswalk_stripe_min_len_m
        and config.crosswalk_stripe_width_min_m <= c.width_m <= config.crosswalk_stripe_width_max_m
    ]
    if len(stripes) < config.crosswalk_min_stripes:
        return crosswalks, consumed

    stripes.sort(key=lambda i: float(np.median(candidates[i].depth_m)))
    regions: list[list[int]] = []
    for index in stripes:
        for region in regions:
            if abs(
                float(np.median(candidates[index].depth_m))
                - float(np.median(candidates[region[0]].depth_m))
            ) <= config.crosswalk_depth_tol_m:
                region.append(index)
                break
        else:
            regions.append([index])

    for region in regions:
        if len(region) < config.crosswalk_min_stripes:
            continue
        members = [candidates[i] for i in region]
        crosswalks.append(_crosswalk_candidate(
            members,
            float(np.mean([c.confidence for c in members])) * 0.95,
            "outline path of the zebra region",
        ))
        consumed.update(region)
    return crosswalks, consumed


def _detect_curbs(
    rgb: np.ndarray, plane: GroundPlane, config: LaneConfig
) -> list[_Candidate]:
    """Very conservative curb detector. Off by default.

    A curb is a depth discontinuity, not a bright marking, so it is found from
    the transverse gradient rather than the marking mask. Only long, near
    longitudinal edges far out to the side qualify; on the test set this still
    over-triggers, which is why ``LANE_CURB_ENABLED`` defaults to false.
    """
    if not config.curb_enabled:
        return []

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (0, 0), 1.4)
    grad = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))

    roi = np.zeros(gray.shape, dtype=np.uint8)
    cv2.fillPoly(roi, [plane.roi_polygon(config)], 1)
    grad[roi == 0] = 0

    threshold = float(np.percentile(grad[roi > 0], 97.5)) if (roi > 0).any() else 1e9
    edges = (grad >= max(threshold, 40.0)).astype(np.uint8) * 255
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    )

    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=60,
        minLineLength=int(0.18 * plane.height), maxLineGap=25,
    )
    if lines is None:
        return []

    results: list[_Candidate] = []
    for raw in lines[:, 0]:
        x1, y1, x2, y2 = (float(v) for v in raw)
        lateral_a, depth_a = plane.to_ground(x1, y1)
        lateral_b, depth_b = plane.to_ground(x2, y2)
        lateral_a, depth_a = float(lateral_a), float(depth_a)
        lateral_b, depth_b = float(lateral_b), float(depth_b)
        length = float(np.hypot(lateral_b - lateral_a, depth_b - depth_a))
        if length < config.curb_min_length_m:
            continue
        if abs(depth_b - depth_a) < 0.6 * length:  # must run along the road
            continue
        if min(abs(lateral_a), abs(lateral_b)) < config.curb_min_lateral_m:
            continue
        results.append(
            _Candidate(
                color="other",
                colour_margin=0.0,
                lateral_m=np.array([lateral_a, lateral_b]),
                depth_m=np.array([depth_a, depth_b]),
                length_m=length,
                width_m=0.0,
                elongation=length,
                orientation="longitudinal",
                ridges=1,
                confidence=0.30,
                evidence={"length_m": round(length, 2), "detector": "transverse gradient + Hough"},
            )
        )
    return results[:8]


# ---------------------------------------------------------------------------
# Stage 5: output
# ---------------------------------------------------------------------------

def _simplify(points: np.ndarray, epsilon: float) -> np.ndarray:
    if len(points) <= 2:
        return points
    approx = cv2.approxPolyDP(
        points.astype(np.float32).reshape(-1, 1, 2), float(epsilon), False
    )
    simplified = approx.reshape(-1, 2)
    return simplified if len(simplified) >= 2 else points


def _is_double(candidate: _Candidate, config: LaneConfig) -> bool:
    """A double needs two ridges *and* a plausible distance between them.

    Counting ridges alone is not enough: on a noisy night mask a single speckled
    line crosses the profile several times. Requiring the pitch to land in the
    physical double-line range is what separates structure from speckle.
    """
    if candidate.evidence.get("pair_gap_m") is not None:
        return True  # two separate components, gap already validated
    pitch = candidate.evidence.get("ridge_pitch_m")
    return (
        candidate.ridges == 2
        and pitch is not None
        and config.double_gap_min_m <= pitch <= config.double_gap_max_m
    )


def _label_for(candidate: _Candidate, config: LaneConfig) -> str:
    if candidate.evidence.get("stripes") is not None:
        return "lane/crosswalk"
    if candidate.evidence.get("detector") is not None:
        return "lane/road curb"
    if _is_double(candidate, config):
        if candidate.color == "yellow":
            return "lane/double yellow"
        if candidate.color == "white":
            return "lane/double white"
        return "lane/single other"
    if candidate.color == "white":
        return "lane/single white"
    if candidate.color == "yellow":
        return "lane/single yellow"
    return "lane/single other"


def _to_polyline(
    candidate: _Candidate, plane: GroundPlane, config: LaneConfig
) -> dict[str, Any] | None:
    px, py = plane.to_image(candidate.lateral_m, candidate.depth_m)
    points = _simplify(np.column_stack([px, py]), config.simplify_eps_px)
    flat: list[float] = []
    for x, y in points:
        flat.extend([
            round(float(np.clip(x, 0.0, plane.width)), 2),
            round(float(np.clip(y, 0.0, plane.height)), 2),
        ])
    # CVAT requires at least two points (four numbers) for a polyline.
    if len(flat) < 4:
        return None
    return {
        "label": _label_for(candidate, config),
        "confidence": round(candidate.confidence, 4),
        "points": flat,
        "closed": False,
        "evidence": candidate.evidence,
    }


def run_lane_detection(
    rgb: np.ndarray,
    config: LaneConfig | None = None,
) -> dict[str, Any]:
    """Detect lane markings and return CVAT-ready polylines.

    Runs entirely on the CPU with OpenCV: it deliberately never imports torch,
    so it adds **zero** VRAM next to the GPU-resident detection and
    segmentation models.
    """
    config = config or LaneConfig.from_env()
    started = time.perf_counter()

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected an HxWx3 RGB array, got shape {rgb.shape}")
    rgb = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
    height, width = rgb.shape[:2]
    plane = GroundPlane.from_config(config, width, height)
    bird = BirdView.from_config(config, plane)

    t_seg = time.perf_counter()
    rasters = _bird_rasters(rgb, config, plane, bird)
    t_seg_end = time.perf_counter()

    candidates, rejected = _extract_candidates(rasters, plane, bird, config)
    t_comp_end = time.perf_counter()

    crosswalks, crosswalk_used = _detect_crosswalks(candidates, config)
    doubles, double_used = _pair_doubles(candidates, plane, config)

    used = crosswalk_used | double_used
    singles = [c for i, c in enumerate(candidates) if i not in used]
    curbs = _detect_curbs(rgb, plane, config)

    marks = [*crosswalks, *doubles, *singles, *curbs]
    marks.sort(key=lambda c: -c.confidence)
    marks = marks[: config.max_marks]

    lanes: list[dict[str, Any]] = []
    for candidate in marks:
        polyline = _to_polyline(candidate, plane, config)
        if polyline is not None:
            lanes.append(polyline)

    counts: dict[str, int] = {}
    for lane in lanes:
        counts[lane["label"]] = counts.get(lane["label"], 0) + 1

    elapsed = (time.perf_counter() - started) * 1000.0
    return {
        "width": width,
        "height": height,
        "model": "lane-classical-cv-v1",
        "device": "cpu",
        "lanes": lanes,
        "counts_by_label": counts,
        "stats": {
            "components": len(candidates),
            "singles": len(singles),
            "doubles": len(doubles),
            "crosswalks": len(crosswalks),
            "curbs": len(curbs),
            "rejected": rejected,
            "ground_plane": {
                "vanishing_point": [round(plane.vx, 2), round(plane.vy, 2)],
                "focal_px": round(plane.focal, 2),
                "camera_height_m": plane.cam_h,
                "lateral_limit_m": round(plane.lateral_limit(config), 2),
                "assumed": True,
            },
            "bird_view": {
                "pixels_per_metre": bird.ppm,
                "size": [bird.cols, bird.rows],
                "depth_range_m": [round(bird.z_min, 2), round(bird.z_max, 2)],
            },
        },
        "timing_ms": {
            "segmentation": round((t_seg_end - t_seg) * 1000, 2),
            "components": round((t_comp_end - t_seg_end) * 1000, 2),
            "classification": round((time.perf_counter() - t_comp_end) * 1000, 2),
            "total": round(elapsed, 2),
        },
        "limitations": _limitations(config),
    }


def _limitations(config: LaneConfig) -> list[str]:
    items = [
        "Detection is limited to the modelled road cone around the camera axis; "
        "markings further out are off the assumed ground plane.",
        "lane/double * merges into a single line beyond the distance where the "
        "two stripes fall below one pixel apart.",
        "Worn or fully occluded markings below the local contrast floor are missed.",
    ]
    if not config.curb_enabled:
        items.append("lane/road curb is disabled (LANE_CURB_ENABLED=false).")
    return items
