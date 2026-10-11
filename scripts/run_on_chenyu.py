# -*- coding: utf-8 -*-
"""晨羽智云一键编排：申请实例 → 等待就绪 → 部署 → 跑批 → 回传 → 收尾。

依赖同目录的 chenyu_api.py 和 paramiko；API Key 从环境变量 CHENYU_API_KEY 读，不落盘。
工程约定与本仓库的 mv-local-pipeline 一致：<project>/production/manifest.json 驱动，
脚本放 <project>/production/，素材路径写在 manifest 里。

典型用法：
    # 用之前存的快照镜像起机器（镜像里已带 ComfyUI 与部署好的工程，不必重传）
    set CHENYU_API_KEY=sk-...
    python run_on_chenyu.py --list-gpus                       # 先看有哪些规格与价格
    python run_on_chenyu.py --project f:\\归人-mv --all --gpu 5090 --megapixels 0.6 --run-name h3_videos_cloud_0p6
    python run_on_chenyu.py --project f:\\归人-mv --all       # --gpu 留空则当场交互选择

    # 从基础镜像起机器，需要把工程一起传上去
    python run_on_chenyu.py --project f:\\归人-mv --all --upload \\
        --cloud-config f:\\归人-mv\\production\\pipeline_config.cloud.json

    # 只看流程不花钱
    python run_on_chenyu.py --project f:\\归人-mv --all --dry

默认收尾是 destroy（跑完立即释放，最省）；任何一步失败都**不**执行收尾，保留现场便于排查。
"""
import argparse
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chenyu_api as cy  # noqa: E402

DEFAULT_IMAGE = "b72e74eb15d14aacac38a9dc48deb1d9"   # 存好的 ComfyUI 快照
REMOTE_BASE = "/root/mv"
COMFY = "/root/ComfyUI"
COMFY_START = ("cd {c} && setsid nohup python3 main.py --listen 0.0.0.0 "
               "--disable-pinned-memory --enable-triton-backend > {b}/comfy.log 2>&1 "
               "< /dev/null &")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def connect(info):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(info["host"], port=int(info["port"]), username=info["username"],
              password=info["password"], timeout=30, banner_timeout=60, auth_timeout=60)
    return c


def sh(c, cmd, timeout=600):
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode("utf-8", "replace")
    err = se.read().decode("utf-8", "replace")
    return so.channel.recv_exit_status(), out.strip(), err.strip()


def ssh_info_of(uuid):
    d = cy.call("GET", "/instance/info", {"instance_uuid": uuid}).get("data", {})
    for svc in d.get("server_map") or []:
        if svc.get("port_type") == "ssh" and svc.get("ssh_info"):
            return svc["ssh_info"]
    sys.exit("实例上没有 SSH 映射，可能还没就绪")


def gpu_options():
    items = cy.call("GET", "/gpu/list").get("data", {}).get("gpu_list", [])
    return [g for g in items if g.get("status") == 1]


def print_gpus(opts):
    print("  计费默认按小时；按天为备选，单独标注")
    for i, g in enumerate(opts, 1):
        p = g.get("price") or {}
        day = f"按天 ¥{p.get('day')}" if p.get("day") else "按天 无"
        print(f"  {i}. {g.get('gpu_name')}   按小时 ¥{p.get('hour')}   （{day}）   {g.get('gpu_uuid')}")


def resolve_gpu(spec):
    """spec 空 → 交互选择；纯数字 → 序号；uuid → 直接用；否则按名称片段匹配。"""
    opts = gpu_options()
    if not opts:
        sys.exit("平台当前没有可用 GPU")
    if not spec:
        if not sys.stdin.isatty():
            sys.exit("未指定 --gpu；请先 --list-gpus 查看，再传 uuid / 序号 / 名称片段")
        print("可选 GPU：")
        print_gpus(opts)
        spec = input("请选择（序号或名称片段）: ").strip()
        if not spec:
            sys.exit("未选择 GPU")
    if spec.isdigit() and 1 <= int(spec) <= len(opts):
        return opts[int(spec) - 1]
    for g in opts:
        if spec.lower() == str(g.get("gpu_uuid", "")).lower():
            return g
    hits = [g for g in opts if spec.lower() in str(g.get("gpu_name", "")).lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        sys.exit(f"没有匹配 '{spec}' 的 GPU，用 --list-gpus 看可选值")
    print(f"'{spec}' 匹配到多款：")
    print_gpus(hits)
    sys.exit("请用更精确的名称片段或序号")


def wait_status(uuid, until, timeout, interval=15):
    t0 = time.time()
    while True:
        st = cy.call("GET", "/instance/info", {"instance_uuid": uuid}).get("data", {}).get("status")
        if st == until:
            log(f"实例已 {cy.STATUS.get(st, st)}，耗时 {time.time() - t0:.0f}s")
            return
        if st in cy.STOPPED and until == 2:
            sys.exit(f"实例处于 {cy.STATUS.get(st, st)}，无法继续")
        if time.time() - t0 > timeout:
            sys.exit(f"等待实例就绪超时（当前 {cy.STATUS.get(st, st)}）")
        time.sleep(interval)


def must(res, what):
    """接口返回 code!=0 时直接失败，别把失败当成功往下走。"""
    if res.get("code") != 0:
        sys.exit(f"{what} 失败：code={res.get('code')} {res.get('msg')}")
    return res


def wait_gone(uuid, timeout=300, interval=10):
    """销毁后复核：直到实例从列表消失才算真的销毁。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        items = cy.call("GET", "/instance/list").get("data", {}).get("instance_list", []) or []
        if uuid not in [i.get("instance_uuid") for i in items]:
            log("实例已从列表消失")
            return True
        time.sleep(interval)
    log(f"警告：销毁请求已接受，但 {uuid} 仍在列表中；请用 chenyu_api.py instances 复核")
    return False


def build_package(project, cloud_config):
    """按 manifest 收集要上传的文件，外加运行脚本与云端配置，打成 tar 字节。"""
    man = json.loads((project / "production" / "manifest.json").read_text(encoding="utf-8"))
    need = {"production/manifest.json"}
    for t in man["tasks"]:
        need.add(t["prompt"])
        need.add(t["audio"])
        need.update(t["images_in_order"])
    for extra in ("production/run_h3_video.py", "production/mvconfig.py"):
        need.add(extra)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for rel in sorted(need):
            p = project / rel
            if not p.exists():
                sys.exit(f"manifest 引用的文件不存在：{p}")
            tf.add(p, arcname=rel)
        if cloud_config:
            tf.add(cloud_config, arcname="production/pipeline_config.json")
    return buf.getvalue(), [t["id"] for t in man["tasks"]]


def main():
    ap = argparse.ArgumentParser(description="晨羽智云一键编排")
    ap.add_argument("--project", required=True, help="本地工程根，需含 production/manifest.json")
    ap.add_argument("--instance", default="", help="复用已在运行的实例 uuid（给了就不再创建）")
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    ap.add_argument("--gpu", default="", help="GPU uuid / 序号 / 名称片段；留空则交互选择")
    ap.add_argument("--gpu-nums", type=int, default=1, choices=[1, 2, 4, 8])
    ap.add_argument("--list-gpus", action="store_true", help="列出可用 GPU 与价格后退出")
    ap.add_argument("--project-name", default="guiren", help="远端工程名，根目录为 /root/mv/<名>-mv")
    ap.add_argument("--run-name", default="h3_videos_cloud", help="远端输出子目录名，同时也是本地回传子目录名")
    ap.add_argument("--all", action="store_true", help="跑 manifest 全部段落（默认）")
    ap.add_argument("--segments", nargs="*", default=[])
    ap.add_argument("--megapixels", default="0.6")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--upload", action="store_true", help="把工程打包上传（基础镜像才需要）")
    ap.add_argument("--cloud-config", default="", help="要上传为远端 pipeline_config.json 的本地文件")
    ap.add_argument("--after", default="destroy", choices=["destroy", "shutdown", "keep"])
    ap.add_argument("--save-image", action="store_true", help="收尾前先存快照")
    ap.add_argument("--timeout", type=int, default=7200, help="跑批总超时秒数")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    project = Path(a.project).resolve()
    remote_root = f"{REMOTE_BASE}/{a.project_name}-mv"
    remote_out = f"{remote_root}/production/{a.run_name}"
    local_out = project / "production" / a.run_name

    payload, ids = build_package(project, Path(a.cloud_config) if a.cloud_config else None)
    ids = ids if (a.all or not a.segments) else a.segments
    cmd = (f"python3 -u run_h3_video.py {' '.join(ids)} "
           f"--megapixels {a.megapixels} --aspect {a.aspect} "
           f"--out-dir {remote_out}")

    if a.list_gpus:
        print_gpus(gpu_options())
        return
    if a.dry:
        gpu_uuid, gpu_desc = "", (a.gpu or "（未指定；正式运行时会列出可选 GPU 让你选）")
    elif a.instance:
        gpu_uuid, gpu_desc = "", "（复用现有实例，不创建）"
    else:
        gpu = resolve_gpu(a.gpu)
        gpu_uuid = gpu.get("gpu_uuid")
        gpu_desc = f"{gpu.get('gpu_name')} x{a.gpu_nums}  {gpu_uuid}"
    log(f"段落 {len(ids)} 个：{' '.join(ids)}")
    log(f"云主机 {gpu_desc}")
    log(f"远端工程 {remote_root}")
    log(f"远端输出 {remote_out}")
    log(f"本地回传 {local_out}")
    log(f"上传包 {'%.1f MB' % (len(payload) / 2**20)}" + ("（含工程）" if a.upload else "（镜像已带工程，仅备用）"))
    log(f"收尾动作 {a.after}" + ("，先存镜像" if a.save_image else ""))
    log(f"跑批命令 {cmd}")
    if a.dry:
        log("--dry：到此为止，未创建任何实例")
        return

    uuid = a.instance or ""
    c = None
    try:
        if uuid:
            log(f"复用实例 {uuid}")
        else:
            r = must(cy.call("POST", "/instance/create_by_image",
                             body={"image_uuid": a.image, "gpu_uuid": gpu_uuid, "gpu_nums": a.gpu_nums}),
                     "创建实例")
            uuid = (r.get("data") or {}).get("instance_uuid", "")
            if not uuid:
                sys.exit(f"创建实例未返回 uuid：{r}")
            log(f"已创建实例 {uuid}")
        wait_status(uuid, 2, 1800)

        info = ssh_info_of(uuid)
        log(f"SSH {info['username']}@{info['host']}:{info['port']}")
        c = connect(info)

        rc, out, _ = sh(c, f"test -d {remote_root}/production && echo yes || echo no")
        if a.upload or out != "yes":
            log("上传工程包…")
            sftp = c.open_sftp()
            with sftp.file("/tmp/mv-pkg.tar", "wb") as f:
                f.write(payload)
            rc, out, err = sh(c, f"mkdir -p {remote_root} && tar -xf /tmp/mv-pkg.tar -C {remote_root} && rm -f /tmp/mv-pkg.tar && echo ok")
            if out != "ok":
                sys.exit(f"解包失败：{err}")
            log("工程就位")
        else:
            log("远端已有工程，跳过上传")

        rc, out, _ = sh(c, "curl -s -m 5 http://127.0.0.1:8188/system_stats | head -c 20")
        if not out.startswith("{"):
            log("启动 ComfyUI…")
            sh(c, COMFY_START.format(c=COMFY, b=REMOTE_BASE))
            for _ in range(60):
                time.sleep(5)
                rc, out, _ = sh(c, "curl -s -m 5 http://127.0.0.1:8188/system_stats | head -c 20")
                if out.startswith("{"):
                    break
            else:
                sys.exit("ComfyUI 启动超时")
        log("ComfyUI 就绪")

        log("发起跑批（detached）…")
        sh(c, f"mkdir -p {remote_out}")
        sh(c, f"cd {remote_root}/production && setsid nohup {cmd} > {REMOTE_BASE}/run.log 2>&1 < /dev/null & echo started")

        log(f"等待 {len(ids)} 段产出…")
        t0 = time.time()
        while True:
            rc, out, _ = sh(c, f"ls {remote_out} 2>/dev/null | wc -l")
            done = int(out or 0)
            rc2, alive, _ = sh(c, "pgrep -f 'run_h3_video.py' | wc -l")
            log(f"  {done}/{len(ids)} 已完成，生成进程数 {alive}")
            if done >= len(ids):
                break
            if int(alive or 0) == 0:
                rc3, tail, _ = sh(c, f"tail -n 15 {REMOTE_BASE}/run.log")
                sys.exit(f"生成进程已退出但只完成 {done}/{len(ids)}\n--- run.log ---\n{tail}")
            if time.time() - t0 > a.timeout:
                sys.exit(f"跑批超时（{done}/{len(ids)}）")
            time.sleep(30)

        local_out.mkdir(parents=True, exist_ok=True)
        sftp = c.open_sftp()
        for sid in ids:
            sftp.get(f"{remote_out}/{sid}.mp4", str(local_out / f"{sid}.mp4"))
        log(f"已回传 {len(ids)} 段 → {local_out}")

        if a.save_image:
            log("保存镜像（实例随后会自动关机）…")
            must(cy.call("POST", "/instance/save_image", body={"instance_uuid": uuid}), "保存镜像")
            log("镜像保存已发起，注意还要等 image/private/list 里该镜像的 save_image_status 变成 2")

        if a.after == "destroy":
            if a.save_image:
                log("已请求存镜像，稍后再销毁；本次不自动销毁，请确认镜像层传完再手动 destroy")
            else:
                must(cy.call("POST", "/instance/destroy", body={"instance_uuid": uuid}), "销毁实例")
                log("销毁请求已接受，复核中…")
                wait_gone(uuid)
        elif a.after == "shutdown":
            must(cy.call("POST", "/instance/shutdown", body={"instance_uuid": uuid}), "关机")
            log("实例已关机（保盘）")
        else:
            log(f"保留实例 {uuid} 运行")

        log("完成")
    except Exception as e:  # noqa: BLE001
        log(f"失败：{type(e).__name__}: {e}")
        if uuid:
            log(f"保留现场，未执行收尾。手工处理：python chenyu_api.py info {uuid}")
        raise
    finally:
        if c:
            c.close()


if __name__ == "__main__":
    main()
