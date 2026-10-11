#!/usr/bin/env bash
# 远端 ComfyUI 主机环境一键探测。
# 用法: bash probe_env.sh [ComfyUI 目录，默认 /root/ComfyUI]
set -u
COMFY="${1:-/root/ComfyUI}"

echo "== os =="; uname -a; cat /etc/os-release 2>/dev/null | head -3
echo "== gpu =="; nvidia-smi 2>/dev/null || echo NO_GPU
echo "== cpu/mem (宿主) =="; nproc; free -g | head -2
echo "== disk =="; df -h | head -12
echo "== python =="; python3 --version; command -v python3 pip3
echo "== packages =="; python3 -m pip list 2>/dev/null | grep -i -e sage -e triton -e torch -e comfy
echo "== comfyui version =="; cat "$COMFY/comfyui_version.py" 2>/dev/null
echo "== comfy_extras minimax =="; ls "$COMFY/comfy_extras/" 2>/dev/null | grep -i -e minimax
echo "== custom_nodes =="; ls "$COMFY/custom_nodes/" 2>/dev/null
echo "== model roots =="; ls "$COMFY/models/" 2>/dev/null
echo "== server (容器内存看 ram_total，不是 free) =="
curl -s -m 5 http://127.0.0.1:8188/system_stats | head -c 500; echo
echo "== net egress =="
curl -s -m 8 -o /dev/null -w "huggingface:%{http_code}\n" https://huggingface.co
curl -s -m 8 -o /dev/null -w "modelscope:%{http_code}\n" https://www.modelscope.cn
