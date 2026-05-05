#!/usr/bin/env python3
"""Small non-focus dictation HUD for WhisprFlow."""

from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402


class WhisprFlowHud:
    def __init__(self, hud_path: Path) -> None:
        self.hud_path = hud_path
        self.last_text = ""
        self.window = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_accept_focus(False)
        self.window.set_focus_on_map(False)
        self.window.set_resizable(False)
        self.window.set_name("whisprflow-hud")

        self.label = Gtk.Label()
        self.label.set_xalign(0.5)
        self.label.set_yalign(0.5)
        self.label.set_margin_start(16)
        self.label.set_margin_end(16)
        self.label.set_margin_top(10)
        self.label.set_margin_bottom(10)
        self.window.add(self.label)

        css = b"""
        #whisprflow-hud {
          background: rgba(20, 24, 32, 0.88);
          border-radius: 8px;
          border: 1px solid rgba(100, 255, 218, 0.65);
        }
        #whisprflow-hud label {
          color: #64ffda;
          font: 11pt "JetBrains Mono";
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def read_text(self) -> str:
        try:
            return self.hud_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def tick(self) -> bool:
        text = self.read_text()
        if text == self.last_text:
            return True
        self.last_text = text
        if not text:
            self.window.hide()
            return True
        self.label.set_text(text)
        self.window.show_all()
        self.position()
        return True

    def position(self) -> None:
        self.window.resize(1, 1)
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        screen = Gdk.Screen.get_default()
        monitor = screen.get_primary_monitor()
        geom = screen.get_monitor_geometry(monitor)
        width, height = self.window.get_size()
        x = geom.x + max(0, (geom.width - width) // 2)
        y = geom.y + geom.height - height - 96
        self.window.move(x, y)

    def run(self) -> None:
        GLib.timeout_add(200, self.tick)
        self.tick()
        Gtk.main()


def main() -> int:
    hud_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "whisprflow-ubuntu" / "hud.txt"
    WhisprFlowHud(hud_path).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
