#!/usr/bin/env bash
# Start a ros2 bag recording using settings from a YAML config file.
#
# Usage:
#   record.sh [path/to/config.yaml]
#
# If no config path is given, the config installed with the bag_recorder
# package is used (edit it, or regenerate its topic list with
# `ros2 run bag_recorder select_topics`).
set -euo pipefail

if [ -z "${1:-}" ]; then
    PKG_SHARE="$(ros2 pkg prefix bag_recorder)/share/bag_recorder"
    CONFIG_FILE="$PKG_SHARE/config/bag_config.yaml"
else
    CONFIG_FILE="$1"
fi

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE" >&2
    exit 1
fi

# Parse the config in one python call: first line is "<output_dir> <split_gb>",
# remaining lines (if any) are the topics to record.
mapfile -t CONFIG_LINES < <(python3 - "$CONFIG_FILE" <<'EOF'
import os
import sys

import yaml

with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f) or {}

out_dir = os.path.expanduser(os.path.expandvars(cfg.get("output_dir", "~/bags")))
split_gb = cfg.get("split_size_gb", 0) or 0
print(f"{out_dir} {split_gb}")
for topic in cfg.get("topics") or []:
    print(topic)
EOF
)

read -r OUTPUT_DIR SPLIT_GB <<< "${CONFIG_LINES[0]}"
TOPICS=("${CONFIG_LINES[@]:1}")

if [ "${#TOPICS[@]}" -eq 0 ]; then
    echo "No topics listed in config file: $CONFIG_FILE" >&2
    echo "Run 'ros2 run bag_recorder select_topics' to pick some." >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
BAG_PATH="$OUTPUT_DIR/bag_$(date +%Y%m%d_%H%M%S)"

CMD=(ros2 bag record -o "$BAG_PATH")
if [ "$SPLIT_GB" != "0" ]; then
    MAX_BAG_SIZE=$(python3 -c "print(int($SPLIT_GB * 1024**3))")
    CMD+=(--max-bag-size "$MAX_BAG_SIZE")
fi
CMD+=("${TOPICS[@]}")

echo "Config:    $CONFIG_FILE"
echo "Recording to: $BAG_PATH"
echo "Split size: ${SPLIT_GB} GB"
echo "Topics (${#TOPICS[@]}):"
printf '  %s\n' "${TOPICS[@]}"
echo

exec "${CMD[@]}"
