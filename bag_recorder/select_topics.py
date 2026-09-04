"""GUI to browse current ros2 topics/services and pick which topics to record.

Run with:
    ros2 run bag_recorder select_topics [--config path/to/bag_config.yaml]
"""
import argparse
import os
import tkinter as tk
from collections import defaultdict
from tkinter import messagebox, ttk

import rclpy
import yaml
from rclpy.node import Node


def default_config_path():
    try:
        from ament_index_python.packages import get_package_share_directory

        return os.path.join(
            get_package_share_directory("bag_recorder"), "config", "bag_config.yaml"
        )
    except Exception:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(here, "..", "config", "bag_config.yaml")


def load_config(path):
    if os.path.isfile(path):
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}
    cfg.setdefault("output_dir", "~/bags")
    cfg.setdefault("split_size_gb", 5)
    cfg.setdefault("topics", [])
    return cfg


def discover_graph():
    """Return (sorted topic names, sorted service names) from the ROS graph."""
    rclpy.init(args=None)
    try:
        node = Node("bag_recorder_topic_picker")
        # Give discovery a moment to populate the graph cache.
        rclpy.spin_once(node, timeout_sec=1.0)
        rclpy.spin_once(node, timeout_sec=1.0)
        topics = sorted(name for name, _ in node.get_topic_names_and_types())
        services = sorted(name for name, _ in node.get_service_names_and_types())
        node.destroy_node()
        return topics, services
    finally:
        rclpy.shutdown()


class GroupedChecklist(ttk.Frame):
    """A search box + scrollable, groupable list of checkbuttons.

    Topics that share a leading path segment (e.g. /os2/points, /os2/imu)
    are collapsed under a single group row (/os2 (2)). Clicking a group's
    checkbox selects/deselects every topic in it; clicking the arrow next
    to it expands/collapses the group to show the individual topics.
    Shift-click extends selection over a contiguous range of the currently
    visible rows (leaves and/or whole groups).
    """

    SHIFT_MASK = 0x0001

    def __init__(self, parent, items, checked=()):
        super().__init__(parent)
        checked = set(checked)

        search_row = ttk.Frame(self)
        search_row.pack(fill="x", padx=4, pady=(4, 0))
        ttk.Label(search_row, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        ttk.Entry(search_row, textvariable=self.filter_var).pack(
            side="left", fill="x", expand=True, padx=4
        )

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        scrollbar.pack(side="right", fill="y", pady=4)

        self._shift_held = False
        self._last_clicked = None
        self._all_rows = []
        self._groups = []
        self.top_entries = self._build_entries(items, checked)
        self._visible_order = []
        self._apply_filter()

    # -- construction ---------------------------------------------------

    def _build_entries(self, items, checked):
        prefix_counts = defaultdict(int)
        for name in items:
            parts = [p for p in name.strip("/").split("/") if p]
            if len(parts) >= 2:
                prefix_counts["/" + parts[0]] += 1

        grouped = defaultdict(list)
        standalone = []
        for name in items:
            parts = [p for p in name.strip("/").split("/") if p]
            key = "/" + parts[0] if parts else name
            if len(parts) >= 2 and prefix_counts[key] >= 2:
                grouped[key].append(name)
            else:
                standalone.append(name)

        top = [("leaf", name) for name in standalone]
        top += [("group", key) for key in grouped]
        top.sort(key=lambda t: t[1])

        entries = []
        for kind, value in top:
            if kind == "leaf":
                entries.append(self._make_leaf(value, checked, parent=None))
            else:
                entries.append(
                    self._make_group(value, sorted(grouped[value]), checked)
                )
        return entries

    def _make_leaf(self, name, checked, parent):
        var = tk.BooleanVar(value=name in checked)
        cb = ttk.Checkbutton(self.inner, text=name, variable=var)
        entry = {
            "type": "leaf",
            "name": name,
            "var": var,
            "frame": cb,
            "parent": parent,
        }
        cb.configure(command=lambda e=entry: self._on_check_command(e))
        cb.bind("<Button-1>", self._remember_shift, add="+")
        self._all_rows.append(entry)
        return entry

    def _make_group(self, key, names, checked):
        header = ttk.Frame(self.inner)
        toggle = ttk.Label(header, text="▶", width=2, cursor="hand2")
        toggle.pack(side="left")
        var = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(header, text=f"{key} ({len(names)})", variable=var)
        cb.pack(side="left")

        entry = {
            "type": "group",
            "key": key,
            "var": var,
            "frame": header,
            "checkbutton": cb,
            "toggle": toggle,
            "expanded": False,
            "children": [],
        }
        entry["children"] = [
            self._make_leaf(name, checked, parent=entry) for name in names
        ]

        cb.configure(command=lambda e=entry: self._on_check_command(e))
        cb.bind("<Button-1>", self._remember_shift, add="+")
        toggle.bind("<Button-1>", lambda e, g=entry: self._on_toggle_expand(g))

        if any(c["var"].get() for c in entry["children"]):
            entry["expanded"] = True

        self._all_rows.append(entry)
        self._groups.append(entry)
        self._update_group_indicator(entry)
        return entry

    # -- click handling ---------------------------------------------------

    def _remember_shift(self, event):
        self._shift_held = bool(event.state & self.SHIFT_MASK)

    def _on_check_command(self, entry):
        shift = self._shift_held
        if shift and self._last_clicked is not None and self._last_clicked is not entry:
            self._select_range(self._last_clicked, entry)
        elif entry["type"] == "group":
            new_state = entry["var"].get()
            for child in entry["children"]:
                child["var"].set(new_state)
            self._set_group_alternate(entry, False)
        else:
            if entry.get("parent") is not None:
                self._update_group_indicator(entry["parent"])
        self._last_clicked = entry

    def _select_range(self, a, b):
        order = self._visible_order
        try:
            ia = order.index(a)
            ib = order.index(b)
        except ValueError:
            return
        lo, hi = sorted((ia, ib))
        touched_groups = set()
        for entry in order[lo : hi + 1]:
            if entry["type"] == "leaf":
                entry["var"].set(True)
                if entry.get("parent") is not None:
                    touched_groups.add(id(entry["parent"]))
            else:
                for child in entry["children"]:
                    child["var"].set(True)
                entry["var"].set(True)
                self._set_group_alternate(entry, False)
        for group in self._groups:
            if id(group) in touched_groups:
                self._update_group_indicator(group)

    def _update_group_indicator(self, group):
        states = [c["var"].get() for c in group["children"]]
        if all(states):
            group["var"].set(True)
            self._set_group_alternate(group, False)
        elif not any(states):
            group["var"].set(False)
            self._set_group_alternate(group, False)
        else:
            self._set_group_alternate(group, True)

    def _set_group_alternate(self, group, alternate):
        cb = group["checkbutton"]
        if alternate:
            cb.state(["alternate"])
        else:
            cb.state(["!alternate"])

    def _on_toggle_expand(self, group):
        group["expanded"] = not group["expanded"]
        self._apply_filter()

    # -- filtering / layout -----------------------------------------------

    def _apply_filter(self):
        needle = self.filter_var.get().strip().lower()
        filtering = bool(needle)
        visible = []

        for entry in self.top_entries:
            if entry["type"] == "leaf":
                if not filtering or needle in entry["name"].lower():
                    visible.append(entry)
                continue

            key_match = filtering and needle in entry["key"].lower()
            child_matches = (
                [c for c in entry["children"] if needle in c["name"].lower()]
                if filtering
                else []
            )
            show_group = (not filtering) or key_match or bool(child_matches)
            if not show_group:
                continue
            visible.append(entry)

            if filtering:
                shown_children = entry["children"] if key_match else child_matches
                expanded_now = True
            else:
                shown_children = entry["children"] if entry["expanded"] else []
                expanded_now = entry["expanded"]

            visible.extend(shown_children)
            entry["toggle"].configure(text="▼" if expanded_now else "▶")

        self._visible_order = visible
        self._relayout(visible)

    def _relayout(self, visible):
        for entry in self._all_rows:
            entry["frame"].pack_forget()
        for entry in visible:
            padx = (24, 2) if entry.get("parent") is not None else (4, 2)
            entry["frame"].pack(fill="x", anchor="w", padx=padx, pady=1)

    # -- public API ---------------------------------------------------------

    def selected(self):
        return [
            e["name"] for e in self._all_rows if e["type"] == "leaf" and e["var"].get()
        ]

    def set_all(self, value):
        for entry in self._all_rows:
            if entry["type"] == "leaf":
                entry["var"].set(value)
        for group in self._groups:
            self._update_group_indicator(group)


class App(ttk.Frame):
    def __init__(self, root, config_path, topics, services, cfg):
        super().__init__(root)
        self.root = root
        self.config_path = config_path
        self.pack(fill="both", expand=True)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=4, pady=4)

        topics_tab = ttk.Frame(notebook)
        notebook.add(topics_tab, text=f"Topics ({len(topics)})")
        self.topics_list = GroupedChecklist(
            topics_tab, topics, checked=cfg.get("topics", [])
        )
        self.topics_list.pack(fill="both", expand=True)

        btn_row = ttk.Frame(topics_tab)
        btn_row.pack(fill="x")
        ttk.Button(
            btn_row, text="Select all", command=lambda: self.topics_list.set_all(True)
        ).pack(side="left", padx=4, pady=2)
        ttk.Button(
            btn_row,
            text="Select none",
            command=lambda: self.topics_list.set_all(False),
        ).pack(side="left", padx=4, pady=2)

        services_tab = ttk.Frame(notebook)
        notebook.add(services_tab, text=f"Services ({len(services)}, info only)")
        ttk.Label(
            services_tab,
            text="Services are shown for reference only — ros2 bag record cannot record services.",
            wraplength=480,
        ).pack(fill="x", padx=4, pady=4)
        self.services_list = GroupedChecklist(services_tab, services)
        self.services_list.pack(fill="both", expand=True)

        settings = ttk.LabelFrame(self, text="Recording settings")
        settings.pack(fill="x", padx=4, pady=(0, 4))

        ttk.Label(settings, text="Output dir:").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        self.output_dir_var = tk.StringVar(value=cfg.get("output_dir", "~/bags"))
        ttk.Entry(settings, textvariable=self.output_dir_var, width=40).grid(
            row=0, column=1, sticky="we", padx=4, pady=2
        )

        ttk.Label(settings, text="Split size (GB, 0=off):").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        self.split_gb_var = tk.StringVar(value=str(cfg.get("split_size_gb", 5)))
        ttk.Entry(settings, textvariable=self.split_gb_var, width=10).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )
        settings.columnconfigure(1, weight=1)

        ttk.Label(self, text=f"Config file: {config_path}").pack(
            anchor="w", padx=4
        )

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=4, pady=4)
        ttk.Button(actions, text="Save", command=self.save).pack(
            side="right", padx=4
        )
        ttk.Button(actions, text="Cancel", command=root.destroy).pack(
            side="right", padx=4
        )

    def save(self):
        try:
            split_gb = float(self.split_gb_var.get())
        except ValueError:
            messagebox.showerror("Invalid value", "Split size must be a number.")
            return

        cfg = {
            "output_dir": self.output_dir_var.get(),
            "split_size_gb": split_gb,
            "topics": sorted(self.topics_list.selected()),
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)
        messagebox.showinfo(
            "Saved", f"Saved {len(cfg['topics'])} topics to\n{self.config_path}"
        )
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=default_config_path(),
        help="Path to the bag_recorder YAML config file to read/write.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    topics, services = discover_graph()

    root = tk.Tk()
    root.title("bag_recorder: select topics")
    root.geometry("560x520")
    App(root, args.config, topics, services, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
