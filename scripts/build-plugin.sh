#!/usr/bin/env bash
# 把本仓打成一个 Claude Code 插件 zip。
#
#   scripts/build-plugin.sh [输出目录]        # 默认 ~/Desktop
#
# 版本单一来源 = gunstore_mcp/__init__.py 的 __version__(pyproject 也从这里取)。
# 脚本会实跑打出来的产物,断言 serverInfo.version 与之一致 —— 版本号说谎的包
# 会让客户端的缓存判断失效(resolved version 没变就不会拉新版)。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$HOME/Desktop}"
NAME=gunstore-pos

cd "$REPO"
VERSION="$(python3 -c "import re,pathlib;print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('gunstore_mcp/__init__.py').read_text()).group(1))")"
echo "==> $NAME $VERSION"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PLUGIN="$STAGE/$NAME"
mkdir -p "$PLUGIN/.claude-plugin"

# Python 依赖不能像 npm 那样由 Claude Code 自动装,所以带上 pyproject + uv.lock,
# 由 .mcp.json 里的 `uv run --directory` 在首次启动时解依赖。
rsync -a --exclude '__pycache__' --exclude '*.pyc' gunstore_mcp "$PLUGIN/"
cp pyproject.toml uv.lock README.md TOOLS.md .env.example "$PLUGIN/"
cp plugin/INSTALL.md "$PLUGIN/"
sed "s/__VERSION__/$VERSION/" plugin/plugin.json.in > "$PLUGIN/.claude-plugin/plugin.json"
cp plugin/mcp.json "$PLUGIN/.mcp.json"

# --- 冒烟:不带任何凭据实跑一次,确认产物能起来且版本号不说谎 ---------------
echo "==> 冒烟测试(两个 mode)"
for MODE in full cpa; do
  RESULT="$(printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"build","version":"1"}}}' \
    | env GUNSTORE_MCP_MODE="$MODE" uv run --directory "$PLUGIN" gunstore-mcp 2>/dev/null \
    | python3 -c 'import sys,json
for l in sys.stdin:
    l=l.strip()
    if l:
        s=json.loads(l).get("result",{}).get("serverInfo",{})
        print(s.get("name",""), s.get("version",""))
        break')"
  EXPECT_NAME="gunstore-pos"; [ "$MODE" = cpa ] && EXPECT_NAME="gunstore-pos-cpa"
  if [ "$RESULT" != "$EXPECT_NAME $VERSION" ]; then
    echo "✘ mode=$MODE 自报 '$RESULT',期望 '$EXPECT_NAME $VERSION'" >&2
    exit 1
  fi
done
# uv 会在插件目录里建 .venv,不能打进包
rm -rf "$PLUGIN/.venv"
find "$PLUGIN" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$PLUGIN" -name '*.egg-info' -type d -prune -exec rm -rf {} + 2>/dev/null || true

claude plugin validate "$PLUGIN" >/dev/null || { echo "✘ claude plugin validate 失败" >&2; exit 1; }

mkdir -p "$OUT_DIR"
ZIP="$OUT_DIR/$NAME-plugin.zip"
rm -f "$ZIP"
( cd "$STAGE" && zip -qr "$ZIP" "$NAME" -x '*/.DS_Store' '*/.env' )

# --- 上传前的硬闸门(每条都对应一次真实被拒/装不上的经历) -----------------
python3 - "$ZIP" "$NAME" <<'PY'
import re, subprocess, sys, os
zip_path, name = sys.argv[1], sys.argv[2]
entries = subprocess.run(["unzip", "-Z1", zip_path], capture_output=True, text=True, check=True).stdout.split()
fail = []
bad = {c for e in entries for c in e if not re.match(r"[A-Za-z0-9._/-]", c)}
if bad: fail.append(f"路径含非法字符 {bad}")
tops = {e.split("/")[0] for e in entries}
if tops != {name}: fail.append(f"顶层不是单个文件夹 {name}/:{tops}")
if f"{name}/.claude-plugin/plugin.json" not in entries: fail.append("缺 .claude-plugin/plugin.json")
if any(e.startswith(f"{name}/bin/") for e in entries): fail.append("有顶层 bin/(claude.ai 会拒)")
if any(e.endswith("/.env") or e == ".env" for e in entries): fail.append("打进了 .env")
if any("/.venv/" in e for e in entries): fail.append("打进了 .venv")
size = os.path.getsize(zip_path)
if size > 50 * 1024 * 1024: fail.append(f"超过 50 MB 上传上限({size/1e6:.1f} MB)")
if fail:
    print("✘ " + "\n✘ ".join(fail), file=sys.stderr); sys.exit(1)
print(f"   {len(entries)} 个条目,{size/1024:.0f} KB")
PY

echo "✔ $ZIP"
