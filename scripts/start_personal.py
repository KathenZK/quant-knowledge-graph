"""One daily entry: check port, verify/rebuild Vite, then serve on loopback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys


def check_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', port))
        except OSError as exc:
            raise ValueError(f'本机端口 {port} 已被占用；没有终止任何进程。请先停止原工作台，或使用 --port 8793 选择空闲端口。') from exc


def node_environment(root):
    candidates = []
    explicit = os.environ.get('QUANTGRAPH_NODE_BIN')
    if explicit:
        candidates.append(str(Path(explicit) / 'node'))
    found = shutil.which('node')
    if found:
        candidates.append(found)
    config = root / '.artifacts/personal-launch.json'
    if config.is_file():
        value = json.loads(config.read_text())
        if value.get('node_bin'):
            candidates.append(str(Path(value['node_bin']) / 'node'))
    for candidate in dict.fromkeys(candidates):
        try:
            result = subprocess.run([candidate, '-p', 'process.versions.node.split(".")[0]'], capture_output=True, text=True, check=True)
            if int(result.stdout.strip()) >= 22:
                env = dict(os.environ, PATH=str(Path(candidate).parent) + os.pathsep + os.environ.get('PATH', ''))
                return candidate, env
        except (OSError, ValueError, subprocess.CalledProcessError):
            continue
    raise ValueError('需要 Node.js 22 或更新版本才能核对并更新页面。请安装后重新运行本命令，或设置 QUANTGRAPH_NODE_BIN 为已安装 Node 的 bin 目录。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', nargs='?', default='.artifacts/personal')
    parser.add_argument('--rebuild', action='store_true', help='强制重建页面，依赖未变化时复用')
    parser.add_argument('--port', type=int, default=int(os.environ.get('QUANTGRAPH_PERSONAL_PORT', '8791')))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError('端口必须在 1–65535 之间。')
        check_port(args.port)
        node, env = node_environment(root)
        command = [node, str(root / 'web/scripts/personal-build.mjs'), 'ensure']
        if args.rebuild:
            command.append('--rebuild')
        subprocess.run(command, cwd=root, env=env, check=True)
        check_port(args.port)
        os.chdir(root)
        os.execve(sys.executable, [sys.executable, '-m', 'quantgraph.api.personal_app', '--runtime', args.runtime,
                                  '--port', str(args.port)], env)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'工作台未启动：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
