#!/usr/bin/env python3
"""
Generic line-array splay angle calculator.

You give it the room (a listening area: the distance range from the
array and ONE listening height that applies to the whole area), the
rig (box count, box vertical coverage angle, array height), and it
distributes splay angles so each box covers an equal *share of the
audience*, which naturally gives:
  - wide splays at the bottom (near field, off-axis listeners),
  - tight splays at the top (far field, on-axis listeners).

Optionally snap results to the fixed splay steps your rig's hardware
actually supports (e.g. 0 / 2.5 / 5 / 7.5 / 10 degrees).

Run:  python3 array_calc.py          opens the GUI (needs PySide6)
Run:  python3 array_calc.py --cli    terminal mode, no dependencies
"""

import math
import argparse


# ----------------------------------------------------------------------
# Geometry helpers -- all angles in degrees
# ----------------------------------------------------------------------

def aim_angle(x, y, x0, y0):
    """Angle (deg) from the array origin down to a point. 0 = straight
    ahead (horizontal), positive = downward tilt."""
    return math.degrees(math.atan2(y0 - y, x - x0))


# ----------------------------------------------------------------------
# Core algorithm
# ----------------------------------------------------------------------

def compute_splays(boxes, box_coverage, rig_height,
                   area_start, area_end, ear_height,
                   min_splay=0.0, max_splay=None,
                   snap_steps=None, safety_margin_deg=0.0):
    """
    boxes:            number of boxes in the hang
    box_coverage:     nominal vertical coverage of ONE box (deg), e.g. 10
    rig_height:       height of the ACOUSTIC CENTER of the array (m or ft)
                      -- for a rough job, the bottom box height is fine
    area_start:       distance from the array where the listening
                      area begins (nearest listener)
    area_end:         distance from the array where the listening
                      area ends (farthest listener)
    ear_height:       listening height of the ENTIRE area (m or ft)
    min_splay:        never go below this between boxes (deg)
    max_splay:        never exceed this (default: box_coverage)
    snap_steps:       optional list of allowed splays, e.g. [0, 2.5, 5, 7.5, 10]
    safety_margin_deg: subtract from computed splays to guarantee overlap
    """
    if max_splay is None:
        max_splay = box_coverage
    if boxes < 2:
        return {"aims": [0.0], "splays": [], "notes": "Single box: just aim it."}
    if area_end <= area_start:
        return {"error": "Listening area end distance must be greater "
                         "than its start distance. Check your inputs."}

    # Aim angles of the extreme boxes (same listening height everywhere)
    ang_bottom = aim_angle(area_start, ear_height, 0.0, rig_height) + safety_margin_deg
    ang_top = aim_angle(area_end, ear_height, 0.0, rig_height)

    total_arc = ang_bottom - ang_top
    if total_arc <= 0:
        return {"error": "Listening height is at or above the array "
                        "height -- the array needs no downward arc. "
                        "Check your inputs."}

    # --- Partition the listening area into one zone per box -------------
    # The standard trick: divide the audience by equal log-distance
    # share and aim each box at a zone boundary.
    d_min = math.log(max(area_start, 0.5))
    d_max = math.log(area_end)
    # Boundaries in log-distance space; each box aims at one boundary
    boundaries = []
    for i in range(boxes):
        frac = i / (boxes - 1)
        ld = d_min + frac * (d_max - d_min)
        d = math.exp(ld)
        boundaries.append(d)

    aims = [aim_angle(d, ear_height, 0.0, rig_height) for d in boundaries]

    # Smooth: enforce monotonic (strictly decreasing downward tilt from
    # bottom to top) and clamp so coverage always overlaps enough to sum.
    splays = []
    for i in range(1, boxes):
        s = aims[i - 1] - aims[i]   # splay between box i-1 and i (bottom-up)
        s = max(min_splay, min(max_splay, s))
        splays.append(s)

    if snap_steps:
        usable = [st for st in snap_steps if min_splay <= st <= max_splay]
        if usable:
            splays = [min(usable, key=lambda st: abs(st - s)) for s in splays]
        else:
            return {"error": "All snap steps fall outside "
                            f"[{min_splay}, {max_splay}] deg -- nothing "
                            "to snap to. Check your inputs."}

    # Recompute cumulative aims from the clamped/snapped splays so the
    # printed aim angles are consistent with the splays you'll actually set.
    aims_final = [ang_bottom]
    for s in splays:
        aims_final.append(aims_final[-1] - s)

    return {
        "aims": aims_final,          # downward tilt of each box, bottom first
        "splays": splays,           # splay between box i and i+1
        "ang_bottom": ang_bottom,
        "ang_top": aims_final[-1],
        "requested_top": ang_top,
    }


# ----------------------------------------------------------------------
# Pretty printing
# ----------------------------------------------------------------------

def report(res, boxes):
    if "error" in res:
        print("!! " + res["error"])
        return
    if "notes" in res:
        print(res["notes"])
        return
    print("=" * 62)
    print("SPLAY SHEET  (top box first -- as the hang sits in the air)")
    print("=" * 62)
    print(f"{'Box':>4} {'Aim (dwn)':>10} {'Splay to box below':>20}")
    print("-" * 62)
    for i in reversed(range(boxes)):
        aim = res["aims"][i]
        sp = f"{res['splays'][i-1]:.1f} deg" if i > 0 else "  --"
        print(f"{i+1:>4} {aim:>9.1f}° {sp:>20}")
    print("-" * 62)
    print(f"Bottom box aim: {res['ang_bottom']:.1f}° down")
    print(f"Top box aim:    {res['aims'][-1]:.1f}° down "
          f"(listener geometry asked for {res['requested_top']:.1f}°)")


# ----------------------------------------------------------------------
# GUI (PySide6) -- default mode. Use --cli for the terminal mode.
# ----------------------------------------------------------------------

def _gui_classes():
    """Build and return the GUI classes. Imported lazily so the
    terminal mode works without PySide6 installed."""
    from PySide6 import QtCore, QtGui, QtWidgets

    class SideView(QtWidgets.QWidget):
        """Side-view cross-section: the hang, each box's aim ray and
        coverage fan, and the listening area."""

        def __init__(self):
            super().__init__()
            self.inputs = None
            self.res = None
            self.error = None
            self.setMinimumHeight(220)

        def set_result(self, inputs, res, error):
            self.inputs = inputs
            self.res = res
            self.error = error
            self.update()

        def _box_color(self, i, boxes, alpha=255):
            hue = 205 + int(150 * i / max(boxes - 1, 1))
            color = QtGui.QColor()
            color.setHsv(hue, 170, 235, alpha)
            return color

        def paintEvent(self, event):
            p = QtGui.QPainter(self)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.fillRect(self.rect(), QtGui.QColor("#fafafa"))
            if self.error or not self.inputs or not self.res:
                p.setPen(QtGui.QColor("#b00020"))
                p.drawText(self.rect(),
                           QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap,
                           "!! " + (self.error or "no data"))
                return

            inp = self.inputs
            boxes = inp["boxes"]
            rig_h = inp["rig_height"]
            near, far, ear = inp["near"], inp["far"], inp["ear"]
            cov = inp["coverage"]
            aims = self.res["aims"]

            w, h = self.width(), self.height()
            x_max = max(far * 1.12, 10.0)
            y_max = max(rig_h * 1.7, ear + 2.0, 6.0)
            ml, mr, mt, mb = 48, 14, 10, 24
            s = min((w - ml - mr) / x_max, (h - mt - mb) / y_max)
            floor_y = h - mb

            def X(x):
                return ml + x * s

            def Y(y):
                return floor_y - y * s

            # Floor and array mast
            p.setPen(QtGui.QPen(QtCore.Qt.gray, 1))
            p.drawLine(ml - 30, floor_y, w - 4, floor_y)
            p.setPen(QtGui.QPen(QtCore.Qt.lightGray, 1, QtCore.Qt.DashLine))
            p.drawLine(X(0), floor_y, X(0), Y(rig_h))

            # Coverage fan: one translucent wedge per box
            R = x_max + y_max
            p.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            for i in range(boxes):
                a0 = aims[i] - cov / 2
                a1 = aims[i] + cov / 2
                pts = [QtCore.QPointF(X(0), Y(rig_h))]
                steps = 14
                for k in range(steps + 1):
                    a = math.radians(a0 + (a1 - a0) * k / steps)
                    pts.append(QtCore.QPointF(
                        X(R * math.sin(a)), Y(rig_h - R * math.cos(a))))
                p.setBrush(self._box_color(i, boxes, alpha=30))
                p.drawPolygon(pts)

            # Listening area: band at ear height between near and far
            p.setPen(QtGui.QPen(QtGui.QColor("#1565c0"), 2))
            p.setBrush(QtGui.QColor(21, 101, 192, 40))
            band = 0.25
            p.drawRect(QtCore.QRectF(X(near), Y(ear + band),
                                    (far - near) * s, 2 * band * s))
            for d in (near, far):
                p.setPen(QtGui.QPen(QtGui.QColor("#1565c0"), 1,
                                    QtCore.Qt.DotLine))
                p.drawLine(X(d), floor_y, X(d), Y(ear + band))

            # Aim rays and aim points on the ear line
            for i in range(boxes):
                theta = math.radians(aims[i])
                sth, cth = math.sin(theta), math.cos(theta)
                color = self._box_color(i, boxes)
                t = min(x_max / max(sth, 1e-9),
                        rig_h / max(cth, 1e-9)) * 1.05
                p.setPen(QtGui.QPen(color, 1))
                p.drawLine(X(0), Y(rig_h), X(t * sth), Y(rig_h - t * cth))
                t_ear = (rig_h - ear) / max(cth, 1e-9)
                p.setBrush(color)
                p.drawEllipse(QtCore.QPointF(X(t_ear * sth), Y(ear)), 3.5, 3.5)

            # The hang itself: boxes chained along the aim directions
            L = max(0.35, min(0.8, rig_h * 0.45 / max(boxes, 1)))
            W = L * 0.6
            cx, cy = 0.0, rig_h
            for i in range(boxes - 1, -1, -1):
                theta = math.radians(aims[i])
                sth, cth = math.sin(theta), math.cos(theta)
                if i == boxes - 1:
                    cx, cy = sth * L / 2, rig_h - cth * L / 2
                else:
                    cx, cy = cx + sth * L, cy - cth * L
                p.save()
                p.translate(X(cx), Y(cy))
                p.rotate(-aims[i])
                p.setPen(QtGui.QPen(QtGui.QColor("#37474f"), 1))
                p.setBrush(QtGui.QColor("#546e7a"))
                p.drawRect(QtCore.QRectF(-W * s / 2, -L * s / 2, W * s, L * s))
                p.restore()

            # Rig point
            p.setPen(QtGui.QPen(QtGui.QColor("#263238"), 2))
            p.setBrush(QtGui.QColor("#263238"))
            p.drawEllipse(QtCore.QPointF(X(0), Y(rig_h)), 3.5, 3.5)

            # Distance and height labels
            p.setPen(QtGui.QPen(QtCore.Qt.darkGray))
            f = QtGui.QFont()
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(QtCore.QPointF(X(0) - 14, floor_y + 14), "array")
            p.drawText(QtCore.QPointF(X(near) - 8, floor_y + 14), f"{near:g} m")
            p.drawText(QtCore.QPointF(X(far) - 8, floor_y + 14), f"{far:g} m")
            p.drawText(QtCore.QPointF(X(near), Y(ear + band) - 4),
                       f"ears at {ear:g} m")

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("array_calc -- line array splay calculator")
            self.resize(1150, 720)

            panel = QtWidgets.QWidget()
            panel.setMaximumWidth(280)
            form = QtWidgets.QFormLayout(panel)

            self.sp_boxes = QtWidgets.QSpinBox()
            self.sp_boxes.setRange(1, 64)
            self.sp_boxes.setValue(8)
            form.addRow("Boxes in the hang", self.sp_boxes)

            def spinner(lo, hi, val, step=0.5):
                sb = QtWidgets.QDoubleSpinBox()
                sb.setRange(lo, hi)
                sb.setValue(val)
                sb.setSingleStep(step)
                sb.setSuffix(" m")
                return sb

            self.dsb_cov = QtWidgets.QDoubleSpinBox()
            self.dsb_cov.setRange(1, 180)
            self.dsb_cov.setValue(10)
            self.dsb_cov.setSingleStep(0.5)
            self.dsb_cov.setSuffix(" °")
            form.addRow("Box vertical coverage", self.dsb_cov)

            self.dsb_h = spinner(0.2, 200, 7.0)
            form.addRow("Array height (ac. center)", self.dsb_h)
            self.dsb_near = spinner(0, 1000, 4.0)
            form.addRow("Listening area starts", self.dsb_near)
            self.dsb_far = spinner(0.5, 2000, 40.0)
            form.addRow("Listening area ends", self.dsb_far)
            self.dsb_ear = spinner(0, 200, 1.5)
            form.addRow("Listening height", self.dsb_ear)

            self.ed_steps = QtWidgets.QLineEdit()
            self.ed_steps.setPlaceholderText("0 2.5 5 7.5 10 (empty = none)")
            form.addRow("Snap steps", self.ed_steps)

            self.lbl_error = QtWidgets.QLabel()
            self.lbl_error.setWordWrap(True)
            self.lbl_error.setStyleSheet("color: #b00020;")
            form.addRow(self.lbl_error)

            btn_reset = QtWidgets.QPushButton("Reset to example")
            btn_reset.clicked.connect(self._reset)
            form.addRow(btn_reset)

            self.table = QtWidgets.QTableWidget(0, 3)
            self.table.setHorizontalHeaderLabels(
                ["Box", "Aim down (°)", "Splay to box below (°)"])
            self.table.horizontalHeader().setSectionResizeMode(
                QtWidgets.QHeaderView.Stretch)
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(
                QtWidgets.QAbstractItemView.NoEditTriggers)
            self.table.setSelectionMode(
                QtWidgets.QAbstractItemView.NoSelection)

            self.lbl_summary = QtWidgets.QLabel()
            self.lbl_summary.setWordWrap(True)

            bottom = QtWidgets.QWidget()
            vb = QtWidgets.QVBoxLayout(bottom)
            vb.setContentsMargins(0, 0, 0, 0)
            vb.addWidget(self.table, 1)
            vb.addWidget(self.lbl_summary)

            self.diagram = SideView()
            splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            splitter.addWidget(self.diagram)
            splitter.addWidget(bottom)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 2)

            central = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(central)
            lay.addWidget(panel)
            lay.addWidget(splitter, 1)
            self.setCentralWidget(central)

            for w in (self.sp_boxes, self.dsb_cov, self.dsb_h,
                      self.dsb_near, self.dsb_far, self.dsb_ear):
                w.valueChanged.connect(self.recompute)
            self.ed_steps.textChanged.connect(self.recompute)
            self.recompute()

        def _reset(self):
            self.sp_boxes.setValue(8)
            self.dsb_cov.setValue(10)
            self.dsb_h.setValue(7)
            self.dsb_near.setValue(4)
            self.dsb_far.setValue(40)
            self.dsb_ear.setValue(1.5)
            self.ed_steps.clear()
            self.recompute()

        def recompute(self):
            parts = self.ed_steps.text().replace(",", " ").split()
            snap = None
            if parts:
                try:
                    snap = [float(t) for t in parts]
                except ValueError:
                    self._show_error("Snap steps must be numbers, "
                                     "e.g. '0 2.5 5 7.5 10'")
                    return
            inputs = {
                "boxes": self.sp_boxes.value(),
                "coverage": self.dsb_cov.value(),
                "rig_height": self.dsb_h.value(),
                "near": self.dsb_near.value(),
                "far": self.dsb_far.value(),
                "ear": self.dsb_ear.value(),
            }
            res = compute_splays(
                boxes=inputs["boxes"],
                box_coverage=inputs["coverage"],
                rig_height=inputs["rig_height"],
                area_start=inputs["near"],
                area_end=inputs["far"],
                ear_height=inputs["ear"],
                snap_steps=snap,
            )
            if "error" in res:
                self._show_error(res["error"])
                return
            self.lbl_error.clear()
            boxes = inputs["boxes"]
            self.table.setRowCount(boxes)
            for row, i in enumerate(reversed(range(boxes))):
                splay = (f"{res['splays'][i-1]:.1f}" if i > 0 else "--")
                for col, text in enumerate((str(i + 1),
                                            f"{res['aims'][i]:.1f}", splay)):
                    item = QtWidgets.QTableWidgetItem(text)
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                    self.table.setItem(row, col, item)
            if "notes" in res:
                self.lbl_summary.setText(res["notes"])
            else:
                self.lbl_summary.setText(
                    f"Bottom box aim: {res['ang_bottom']:.1f}° down    "
                    f"Top box aim: {res['aims'][-1]:.1f}° down "
                    f"(listener geometry asked for {res['requested_top']:.1f}°)")
            self.diagram.set_result(inputs, res, None)

        def _show_error(self, msg):
            self.lbl_error.setText("!! " + msg)
            self.table.setRowCount(0)
            self.lbl_summary.clear()
            self.diagram.set_result(None, None, msg)

    return SideView, MainWindow


def run_gui():
    """Launch the GUI. Returns the Qt exit code, or None if PySide6
    is not installed."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        return None
    import sys
    _, MainWindow = _gui_classes()
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


# ----------------------------------------------------------------------
# Example / CLI
# ----------------------------------------------------------------------

def main():
    import sys
    if "--cli" not in sys.argv:
        code = run_gui()
        if code is None:
            print("PySide6 is not installed -- starting terminal mode "
                  "instead.\n"
                  "Install the GUI dependency with:  pip install PySide6\n")
        else:
            sys.exit(code)
    else:
        sys.argv.remove("--cli")
    p = argparse.ArgumentParser(
        description="Generic line array splay calculator")
    p.add_argument("-n", "--boxes", type=int, default=8,
                   help="number of boxes in the hang")
    p.add_argument("-c", "--coverage", type=float, default=10,
                   help="vertical coverage of one box in degrees")
    p.add_argument("-H", "--height", type=float, default=7.0,
                   help="height of array acoustic center above floor (m)")
    p.add_argument("--near", type=float, default=4.0,
                   help="distance from array where the listening area "
                        "starts")
    p.add_argument("--far", type=float, default=40.0,
                   help="distance from array where the listening area ends")
    p.add_argument("--ear", type=float, default=1.5,
                   help="listening height of the entire area (m)")
    p.add_argument("--steps", type=float, nargs="+",
                   help="allowed splay steps of your rigging, e.g. "
                        "0 2.5 5 7.5 10")
    args = p.parse_args()

    res = compute_splays(
        boxes=args.boxes,
        box_coverage=args.coverage,
        rig_height=args.height,
        area_start=args.near,
        area_end=args.far,
        ear_height=args.ear,
        snap_steps=args.steps,
    )
    report(res, args.boxes)


if __name__ == "__main__":
    main()
