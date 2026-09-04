# bag_recorder

Config-driven `ros2 bag record` wrapper, plus a small GUI to pick topics.

## Config file

`config/bag_config.yaml`:

```yaml
output_dir: "/home/robot/bags"     # where recordings are saved
split_size_gb: 5         # split into a new file after this many GB (0 = off)
topics: []                # topics to record
```

## Picking topics with the GUI

```bash
ros2 run bag_recorder select_topics
```

Lists all currently discoverable topics (checkable) and services (shown for
reference — `ros2 bag record` cannot record services). Check the topics you
want, adjust output dir / split size, and hit Save to write them into
`bag_config.yaml`.

Pass `--config /path/to/other.yaml` to edit a different config file.

Requires `python3-tk` (`sudo apt install python3-tk`) if not already present.

## Recording

```bash
ros2 run bag_recorder record.sh                 # uses the installed config
ros2 run bag_recorder record.sh /path/to.yaml   # or an explicit config
```

Each run creates a new timestamped subfolder under `output_dir`.
