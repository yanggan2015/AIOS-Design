#!/usr/bin/env python3
"""Minimal GTK3 hello window for Mode-A / Widget Mirror manual tests."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class Hello(Gtk.Window):
    def __init__(self):
        super().__init__(title="Hello luminOS")
        self.set_default_size(400, 240)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        self.add(box)
        self.label = Gtk.Label(label="Ready")
        self.entry = Gtk.Entry()
        btn = Gtk.Button(label="OK")
        btn.connect("clicked", self.on_ok)
        box.pack_start(self.label, False, False, 0)
        box.pack_start(self.entry, False, False, 0)
        box.pack_start(btn, False, False, 0)

    def on_ok(self, *_a):
        self.label.set_text(f"OK:{self.entry.get_text()}")


if __name__ == "__main__":
    w = Hello()
    w.connect("destroy", Gtk.main_quit)
    w.show_all()
    Gtk.main()
