"""GUI to browse current ros2 topics/services and pick which topics to record.

Run with:
    ros2 run bag_recorder select_topics [--config path/to/bag_config.yaml]
"""
import argparse
import os
import tkinter as tk
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


class ScrollableChecklist(ttk.Frame):
    """A search box + scrollable list of checkbuttons."""

    def __init__(self, parent, items, checked=()):
        super().__init__(parent)
        self.vars = {}

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

        self._rows = []
        checked = set(checked)
        for name in items:
            var = tk.BooleanVar(value=name in checked)
            cb = ttk.Checkbutton(self.inner, text=name, variable=var)
            cb.pack(anchor="w", padx=2)
            self.vars[name] = var
            self._rows.append((name, cb))

    def _apply_filter(self):
        needle = self.filter_var.get().lower()
        for name, cb in self._rows:
            if needle in name.lower():
                cb.pack(anchor="w", padx=2)
            else:
                cb.pack_forget()

    def selected(self):
        return [name for name, var in self.vars.items() if var.get()]

    def set_all(self, value):
        for var in self.vars.values():
            var.set(value)


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
        self.topics_list = ScrollableChecklist(
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
        self.services_list = ScrollableChecklist(services_tab, services)
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
