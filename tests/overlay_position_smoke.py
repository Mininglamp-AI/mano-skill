"""Manual smoke: spawn TaskOverlayView for ~3s and capture its geometry."""
import sys, os, time, platform
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if platform.system() == "Windows":
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

from visual.view.task_overlay_view import TaskOverlayView

v = TaskOverlayView()
print("ui_initialized:", v._ui_initialized)
if v._ui_initialized:
    v.root.deiconify()
    v.root.update()
    geo = v.root.geometry()
    x = v.root.winfo_x()
    y = v.root.winfo_y()
    w = v.root.winfo_width()
    h = v.root.winfo_height()
    print("geometry:", geo, "x,y,w,h =", x, y, w, h)
    # ~3s then close
    v.root.after(3000, v.root.destroy)
    try:
        v.root.mainloop()
    except Exception as e:
        print("mainloop ended:", e)
print("done.")
