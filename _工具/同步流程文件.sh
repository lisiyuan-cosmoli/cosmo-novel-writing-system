#!/usr/bin/env bash
# 同步流程文件 —— 这里只做转发。
# **白名单与全部逻辑都在 _工具/同步文件.py，Shell 不再保留第二份清单**：
# 两份各写各的，迟早对不上——排除表那次已经证明过一遍了。
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$here/同步文件.py" "$@"
