# -*- coding: utf-8 -*-
"""用 ComfyUI 的 /object_info 校验节点是否存在、模型名是否合法。

跨环境部署最关键的一步：节点的有无、模型名的合法清单，都由服务端说了算，
不要靠目录扫描（软链接挂载会扫漏），也不要把另一台机器上的模型名照抄过来。

用法（在目标主机上执行，需 ComfyUI 已启动）：
    python3 verify_nodes.py Node1 Node2 ...
    python3 verify_nodes.py --model UNETLoader:unet_name --model VAELoader:vae_name --grep minimax

示例（MiniMax H3 多参视频链路）：
    python3 verify_nodes.py MiniMaxH3ReferenceToVideo PathchSageAttentionKJ VHS_VideoCombine LoadAudio \\
        --model UNETLoader:unet_name --model CLIPLoader:clip_name \\
        --model VAELoader:vae_name --model LoraLoaderModelOnly:lora_name --grep minimax
"""
import argparse
import json
import urllib.parse
import urllib.request


def fetch(server, cls):
    url = f"{server}/object_info/{urllib.parse.quote(cls)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r).get(cls)


def check_node(server, cls):
    d = fetch(server, cls)
    if not d:
        print(f"[MISSING] {cls}")
        return
    spec = d.get("input", {})
    req = list(spec.get("required", {}))
    opt = list(spec.get("optional", {}))
    print(f"[OK] {cls}\n     REQ={req}\n     OPT={opt}")


def check_model(server, spec, grep):
    cls, _, widget = spec.partition(":")
    if not widget:
        print(f"[WARN] 参数格式应为 Class:widget，收到 {spec}")
        return
    d = fetch(server, cls)
    if not d:
        print(f"[MISSING] {cls}（用于 {widget}）")
        return
    section = d.get("input", {})
    entry = section.get("required", {}).get(widget) or section.get("optional", {}).get(widget)
    if not entry:
        print(f"[MISSING] {cls}.{widget} 不存在")
        return
    if not isinstance(entry[0], list):
        print(f"[WARN] {cls}.{widget} 不是可选列表，类型为 {type(entry[0]).__name__}")
        return
    options = entry[0]
    hits = [o for o in options if grep.lower() in str(o).lower()] if grep else options
    print(f"[{cls}.{widget}] 命中 {len(hits)}/{len(options)} 项：")
    for o in hits:
        print(f"      {o}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nodes", nargs="*", help="要校验的节点 class 名")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--model", action="append", default=[], metavar="CLASS:WIDGET",
                    help="要列出合法值的模型下拉，可重复")
    ap.add_argument("--grep", default="", help="模型名只显示含该关键词的项")
    a = ap.parse_args()

    if not a.nodes and not a.model:
        ap.print_help()
        return
    for cls in a.nodes:
        check_node(a.server, cls)
    for spec in a.model:
        check_model(a.server, spec, a.grep)


if __name__ == "__main__":
    main()
