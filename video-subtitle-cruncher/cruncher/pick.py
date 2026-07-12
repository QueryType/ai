"""Interactive region picker: dim the screen, drag a rectangle, get X,Y,W,H."""

import tkinter as tk


def pick_region() -> dict | None:
    """Returns an mss-style region dict, or None if cancelled (Esc)."""
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.3)
    root.configure(bg="black")
    canvas = tk.Canvas(root, cursor="cross", bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        root.winfo_screenwidth() // 2, 60,
        text="Drag a rectangle over the area to record — Esc to cancel",
        fill="white", font=("Helvetica", 20))

    state: dict = {"start": None, "rect": None, "label": None, "result": None}

    def on_press(event):
        state["start"] = (event.x_root, event.y_root)
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#00ff88", width=2)
        state["label"] = canvas.create_text(
            event.x, event.y - 14, fill="#00ff88", font=("Helvetica", 14), text="")

    def on_drag(event):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        # canvas coords track root coords on a fullscreen window
        canvas.coords(state["rect"], x0, y0, event.x_root, event.y_root)
        w, h = abs(event.x_root - x0), abs(event.y_root - y0)
        canvas.coords(state["label"], min(x0, event.x_root) + 50,
                      min(y0, event.y_root) - 14)
        canvas.itemconfigure(state["label"], text=f"{w} x {h}")

    def on_release(event):
        if not state["start"]:
            return
        x0, y0 = state["start"]
        x1, y1 = event.x_root, event.y_root
        left, top = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w > 10 and h > 10:
            state["result"] = {"left": left, "top": top, "width": w, "height": h}
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", lambda e: root.destroy())
    root.mainloop()
    return state["result"]
