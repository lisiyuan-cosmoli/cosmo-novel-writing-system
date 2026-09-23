#!/bin/bash
# 兼容旧入口。v2 快照改为可核验的压缩备份，不再复制整棵目录。
set -eu

if [ "$#" -lt 1 ] || [ ! -d "$1" ]; then
  echo "用法：bash _工具/快照.sh <项目文件夹> [备注]"
  exit 2
fi

PROJECT="$1"
NOTE="${2:-兼容快照}"
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$TOOL_DIR/备份.py" create "$PROJECT" --note "$NOTE"
