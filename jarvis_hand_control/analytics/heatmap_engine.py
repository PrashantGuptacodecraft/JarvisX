"""
analytics/heatmap_engine.py
SQLAlchemy ORM models + HeatmapEngine for gesture analytics.
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

_REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Lazy SQLAlchemy imports (avoid hard crash if not installed) ───────────────
try:
    from sqlalchemy import (
        Column, String, Float, Integer, Boolean, DateTime,
        Date, Text, create_engine, func,
    )
    from sqlalchemy.orm import DeclarativeBase, Session as OrmSession
    _SA = True

    class _Base(DeclarativeBase):
        pass

    class GestureEvent(_Base):
        __tablename__ = "gesture_events"
        id              = Column(Integer, primary_key=True, autoincrement=True)
        timestamp       = Column(DateTime, default=datetime.utcnow, index=True)
        gesture_name    = Column(String(64), index=True)
        confidence      = Column(Float, default=0.0)
        screen_x        = Column(Integer, default=0)
        screen_y        = Column(Integer, default=0)
        action_executed = Column(String(128), default="")
        session_id      = Column(String(36), index=True)
        voice_fused     = Column(Boolean, default=False)

    class SessionRecord(_Base):
        __tablename__ = "sessions"
        session_id      = Column(String(36), primary_key=True)
        start_time      = Column(DateTime)
        end_time        = Column(DateTime, nullable=True)
        total_gestures  = Column(Integer, default=0)
        economy_score   = Column(Float, default=0.0)
        fatigue_index   = Column(Float, default=0.0)

    class DailyStat(_Base):
        __tablename__ = "daily_stats"
        date             = Column(Date, primary_key=True)
        total_gestures   = Column(Integer, default=0)
        unique_gestures  = Column(Integer, default=0)
        avg_confidence   = Column(Float, default=0.0)
        top_gesture      = Column(String(64), default="")
        economy_score    = Column(Float, default=0.0)
        fatigue_index    = Column(Float, default=0.0)

except ImportError:
    _SA = False
    log.warning("SQLAlchemy not installed — analytics persistence disabled")


class HeatmapEngine:
    """
    Records gesture events to SQLite via SQLAlchemy.
    Generates heatmap images and statistics on demand.
    """

    def __init__(self) -> None:
        self._engine       = None
        self._session_id:  Optional[str]   = None
        self._session_gestures: int        = 0
        self._session_start:    Optional[datetime] = None
        self._initialized: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def initialize(self, db_path: str) -> None:
        """Create SQLite engine and all tables."""
        if not _SA:
            return
        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
            _Base.metadata.create_all(self._engine)
            self._initialized = True
            log.info("HeatmapEngine DB: %s", db_path)
        except Exception as exc:
            log.error("HeatmapEngine init failed: %s", exc)

    def start_session(self) -> str:
        """Generate a new session UUID and record start time."""
        self._session_id       = str(uuid.uuid4())
        self._session_start    = datetime.utcnow()
        self._session_gestures = 0
        if self._initialized and _SA:
            with OrmSession(self._engine) as s:
                s.add(SessionRecord(
                    session_id  = self._session_id,
                    start_time  = self._session_start,
                ))
                s.commit()
        log.info("Session started: %s", self._session_id)
        return self._session_id

    def end_session(self) -> None:
        """Compute economy_score, fatigue_index and persist session record."""
        if not self._initialized or not _SA or self._session_id is None:
            return
        end_time = datetime.utcnow()
        duration_s = max(1, (end_time - (self._session_start or end_time)).total_seconds())
        # Economy score: gestures per minute (normalised, cap at 100)
        gpm           = self._session_gestures / (duration_s / 60.0)
        economy_score = min(100.0, gpm * 2.5)
        # Fatigue index: approximated as number of repeated identical gestures / total
        fatigue_index = min(1.0, self._session_gestures / max(duration_s, 1) * 0.05)
        try:
            with OrmSession(self._engine) as s:
                rec = s.get(SessionRecord, self._session_id)
                if rec:
                    rec.end_time      = end_time
                    rec.total_gestures= self._session_gestures
                    rec.economy_score = round(economy_score, 2)
                    rec.fatigue_index = round(fatigue_index, 4)
                    s.commit()
            self._update_daily_stat(economy_score, fatigue_index)
        except Exception as exc:
            log.error("end_session error: %s", exc)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_gesture(self, gesture_name: str, confidence: float,
                    x: int, y: int, action_executed: str,
                    voice_fused: bool = False) -> None:
        """Insert one GestureEvent row."""
        self._session_gestures += 1
        if not self._initialized or not _SA:
            return
        try:
            with OrmSession(self._engine) as s:
                s.add(GestureEvent(
                    gesture_name    = gesture_name,
                    confidence      = round(confidence, 4),
                    screen_x        = x,
                    screen_y        = y,
                    action_executed = action_executed,
                    session_id      = self._session_id or "unknown",
                    voice_fused     = voice_fused,
                ))
                s.commit()
        except Exception as exc:
            log.debug("log_gesture error: %s", exc)

    # ── Heatmap generation ────────────────────────────────────────────────────

    def generate_heatmap(self, time_window_minutes: int = 60) -> np.ndarray:
        """
        Query recent events, accumulate a 1920×1080 density map,
        apply Gaussian blur, normalise, apply JET colormap.
        Returns BGR image (1920, 1080, 3).
        """
        heat = np.zeros((1080, 1920), dtype=np.float32)

        if self._initialized and _SA:
            cutoff = datetime.utcnow() - timedelta(minutes=time_window_minutes)
            try:
                with OrmSession(self._engine) as s:
                    rows = s.query(GestureEvent).filter(
                        GestureEvent.timestamp >= cutoff
                    ).all()
                for row in rows:
                    x = max(0, min(int(row.screen_x), 1919))
                    y = max(0, min(int(row.screen_y), 1079))
                    heat[y, x] += 1.0
            except Exception as exc:
                log.error("generate_heatmap query error: %s", exc)

        # Gaussian blur
        try:
            from scipy.ndimage import gaussian_filter
            heat = gaussian_filter(heat, sigma=40)
        except ImportError:
            import cv2
            heat = cv2.GaussianBlur(heat, (81, 81), 40)

        # Normalise and colorise
        import cv2
        peak = heat.max()
        if peak > 0:
            norm = (heat / peak * 255).astype(np.uint8)
        else:
            norm = heat.astype(np.uint8)

        return cv2.applyColorMap(norm, cv2.COLORMAP_JET)

    def generate_heatmap_b64(self, time_window_minutes: int = 60) -> str:
        """Return heatmap as base64 PNG string for Flask endpoint."""
        import cv2
        img  = self.generate_heatmap(time_window_minutes)
        _, buf = cv2.imencode(".png", img)
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    # ── Statistics ────────────────────────────────────────────────────────────

    def get_session_stats(self) -> dict:
        """Return dict of current session statistics."""
        return {
            "session_id":      self._session_id,
            "total_gestures":  self._session_gestures,
            "start_time":      self._session_start.isoformat() if self._session_start else None,
        }

    def get_fatigue_curve(self) -> list[dict]:
        """Return list of {minute, fatigue} dicts for the current session."""
        if not self._initialized or not _SA or not self._session_id:
            return []
        try:
            with OrmSession(self._engine) as s:
                events = s.query(GestureEvent).filter(
                    GestureEvent.session_id == self._session_id
                ).order_by(GestureEvent.timestamp).all()
            if not events:
                return []
            start = events[0].timestamp
            curve = []
            minute_counts: dict[int, int] = {}
            for ev in events:
                m = int((ev.timestamp - start).total_seconds() // 60)
                minute_counts[m] = minute_counts.get(m, 0) + 1
            for m, cnt in sorted(minute_counts.items()):
                curve.append({"minute": m, "fatigue": min(100, cnt * 3)})
            return curve
        except Exception as exc:
            log.error("get_fatigue_curve: %s", exc)
            return []

    def get_gesture_distribution(self) -> dict:
        """Return {gesture_name: count} for current session."""
        if not self._initialized or not _SA or not self._session_id:
            return {}
        try:
            with OrmSession(self._engine) as s:
                rows = s.query(
                    GestureEvent.gesture_name,
                    func.count(GestureEvent.id).label("cnt"),
                ).filter(
                    GestureEvent.session_id == self._session_id
                ).group_by(GestureEvent.gesture_name).all()
            return {r.gesture_name: r.cnt for r in rows}
        except Exception as exc:
            log.error("get_gesture_distribution: %s", exc)
            return {}

    def get_hourly_counts(self) -> list[dict]:
        """Return [{'hour': H, 'count': N}] for today."""
        if not self._initialized or not _SA:
            return []
        try:
            today = date.today()
            with OrmSession(self._engine) as s:
                rows = s.query(GestureEvent).filter(
                    func.date(GestureEvent.timestamp) == today
                ).all()
            counts = [0] * 24
            for ev in rows:
                counts[ev.timestamp.hour] += 1
            return [{"hour": h, "count": counts[h]} for h in range(24)]
        except Exception as exc:
            log.error("get_hourly_counts: %s", exc)
            return []

    def compare_sessions(self, session_id_1: str, session_id_2: str) -> dict:
        """Return side-by-side stats for two session IDs."""
        if not self._initialized or not _SA:
            return {}
        result = {}
        try:
            with OrmSession(self._engine) as s:
                for sid in (session_id_1, session_id_2):
                    rec = s.get(SessionRecord, sid)
                    result[sid] = {
                        "total_gestures": rec.total_gestures if rec else 0,
                        "economy_score":  rec.economy_score  if rec else 0,
                        "fatigue_index":  rec.fatigue_index  if rec else 0,
                        "start_time":     rec.start_time.isoformat() if rec and rec.start_time else None,
                    }
        except Exception as exc:
            log.error("compare_sessions: %s", exc)
        return result

    # ── Reports ───────────────────────────────────────────────────────────────

    def export_weekly_report(self) -> str:
        """Generate a PDF weekly report using ReportLab. Returns file path."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image,
            )
            from reportlab.lib import colors
            import cv2, io, tempfile

            today    = date.today()
            filename = str(_REPORTS_DIR / f"weekly_{today}.pdf")
            doc      = SimpleDocTemplate(filename, pagesize=A4)
            styles   = getSampleStyleSheet()
            elements = []

            # Title
            elements.append(Paragraph(
                f"JARVIS Gesture Analytics — Week of {today}", styles["Title"]
            ))
            elements.append(Spacer(1, 12))

            # Heatmap image
            try:
                hm_img = self.generate_heatmap(time_window_minutes=10080)   # 1 week
                hm_rgb = cv2.cvtColor(hm_img, cv2.COLOR_BGR2RGB)
                _, buf = cv2.imencode(".png", hm_rgb)
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(buf.tobytes())
                tmp.flush()
                elements.append(Paragraph("Gesture Heatmap (Last 7 Days)", styles["Heading2"]))
                elements.append(Image(tmp.name, width=400, height=225))
                elements.append(Spacer(1, 12))
            except Exception:
                pass

            # Distribution table
            dist = self.get_gesture_distribution()
            if dist:
                elements.append(Paragraph("Gesture Distribution", styles["Heading2"]))
                table_data = [["Gesture", "Count"]] + sorted(
                    dist.items(), key=lambda x: -x[1]
                )
                t = Table(table_data, colWidths=[260, 80])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                    ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]))
                elements.append(t)

            doc.build(elements)
            log.info("Weekly report saved: %s", filename)
            return filename
        except Exception as exc:
            log.error("export_weekly_report: %s", exc)
            return ""

    # ── Private helpers ───────────────────────────────────────────────────────

    def _update_daily_stat(self, economy: float, fatigue: float) -> None:
        if not self._initialized or not _SA:
            return
        today = date.today()
        dist  = self.get_gesture_distribution()
        top_g = max(dist, key=dist.get) if dist else ""
        avg_c = 0.0
        try:
            with OrmSession(self._engine) as s:
                evs = s.query(GestureEvent).filter(
                    func.date(GestureEvent.timestamp) == today
                ).all()
                if evs:
                    avg_c = sum(e.confidence for e in evs) / len(evs)
                total = len(evs)
                rec   = s.get(DailyStat, today)
                if rec is None:
                    rec = DailyStat(date=today)
                    s.add(rec)
                rec.total_gestures  = total
                rec.unique_gestures = len(dist)
                rec.avg_confidence  = round(avg_c, 4)
                rec.top_gesture     = top_g
                rec.economy_score   = round(economy, 2)
                rec.fatigue_index   = round(fatigue, 4)
                s.commit()
        except Exception as exc:
            log.error("_update_daily_stat: %s", exc)
