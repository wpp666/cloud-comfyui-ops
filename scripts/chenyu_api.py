# -*- coding: utf-8 -*-
"""晨羽智云开放 API 封装：实例生命周期（申请 / 开机 / 关机 / 销毁）与账户查询。

认证：环境变量 CHENYU_API_KEY（形如 sk-xxxx），只从环境变量读，不落盘、不进日志。
基础地址：https://www.chenyu.cn/api/open/v2
接口文档：https://enterprise.chenyu.cn/api-reference/introduction

用法：
    python chenyu_api.py balance
    python chenyu_api.py instances
    python chenyu_api.py info <instance_uuid>
    python chenyu_api.py ssh <instance_uuid> [--show-password]
    python chenyu_api.py gpus
    python chenyu_api.py images [--page 1] [--cuda 12.8] [--python 3.12]
    python chenyu_api.py create --image <image_uuid> --gpu <gpu_uuid> [--nums 1]
    python chenyu_api.py start|shutdown|restart|destroy <instance_uuid>
    python chenyu_api.py save-image <instance_uuid> --name <镜像名> [--remark 说明]
    python chenyu_api.py wait <instance_uuid> [--field status|save_image_status] [--until 2] [--timeout 900]

只读命令（balance/instances/info/gpus/images）可随时执行；
start/shutdown/restart/destroy/create/save-image 会改动账号资源，执行前先确认目标实例。

注意：save-image 只能在实例【运行中】保存，且保存发起后实例会保持运行、完成后自动关机。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("CHENYU_BASE", "https://www.chenyu.cn/api/open/v2")

STATUS = {
    0: "已创建", 1: "开机中(首次)", 2: "运行中", 3: "关机中", 4: "已关机",
    21: "关机中", 22: "已关机", 23: "已关机(异常)", 24: "开机中", 27: "重启中",
}
STOPPED = {4, 22, 23}
SAVE_STATUS = {1: "上传中", 2: "上传成功", 3: "上传失败"}


def status_text(code):
    return f"{code} {STATUS.get(code, '未知')}"


def call(method, path, params=None, body=None):
    key = os.environ.get("CHENYU_API_KEY")
    if not key:
        sys.exit("未设置环境变量 CHENYU_API_KEY")
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")


def instance_uuid_of(d):
    return d.get("instance_uuid") or d.get("uuid") or ""


def print_instances(res):
    items = res.get("data", {}).get("instance_list", [])
    if not items:
        print("(无实例)")
        return
    for it in items:
        print(f"{it.get('instance_uuid')}  {status_text(it.get('status'))}  "
              f"{it.get('gpu_name')} x{it.get('gpu_nums')}  "
              f"镜像 {it.get('image_name')}:{it.get('image_tag')}")
        for svc in it.get("server_map", []) or []:
            if svc.get("port_type") == "ssh" and svc.get("ssh_info"):
                s = svc["ssh_info"]
                print(f"    ssh {s.get('username')}@{s.get('host')} -p {s.get('port')}")


def cmd_balance(a):
    res = call("GET", "/balance/info")
    d = res.get("data", {})
    print(f"余额 {d.get('balance')} 元   算力卡余额 {d.get('card_balance')} 元")


def cmd_instances(a):
    print_instances(call("GET", "/instance/list"))


def cmd_info(a):
    res = call("GET", "/instance/info", {"instance_uuid": a.uuid})
    d = res.get("data", {})
    print(f"实例 {d.get('instance_uuid')}")
    print(f"  状态      {status_text(d.get('status'))}")
    print(f"  规格      {d.get('gpu_name')} x{d.get('gpu_nums')}")
    print(f"  镜像      {d.get('image_name')}:{d.get('image_tag')}  uuid={d.get('image_uuid')}")
    print(f"  gpu_uuid  {d.get('gpu_uuid')}")
    print(f"  创建/启动 {d.get('create_time')} / {d.get('start_time')}")
    for svc in d.get("server_map", []) or []:
        print(f"  [{svc.get('title')}] {svc.get('url')}")
        if svc.get("port_type") == "ssh" and svc.get("ssh_info"):
            print(f"      ssh_info = {json.dumps(svc['ssh_info'], ensure_ascii=False)}")


def cmd_ssh(a):
    d = call("GET", "/instance/info", {"instance_uuid": a.uuid}).get("data", {})
    for svc in d.get("server_map", []) or []:
        if svc.get("port_type") == "ssh" and svc.get("ssh_info"):
            s = dict(svc["ssh_info"])
            if not a.show_password and s.get("password"):
                s["password"] = "*" * len(s["password"])
            print(json.dumps(s, ensure_ascii=False))
            return
    sys.exit("该实例没有 SSH 映射，可能尚未运行")


def cmd_private_images(a):
    params = {"page": a.page, "page_size": a.page_size}
    d = call("GET", "/image/private/list", params).get("data", {})
    items = d.get("image_list") or d.get("list") or []
    print(f"共 {d.get('total', len(items))} 个私有镜像")
    for im in items:
        print(" ", json.dumps(im, ensure_ascii=False))


def cmd_gpus(a):
    for g in call("GET", "/gpu/list").get("data", {}).get("gpu_list", []):
        p = g.get("price", {})
        print(f"{g.get('gpu_uuid')}  {g.get('gpu_name')}  状态{g.get('status')}  "
              f"{p.get('hour')}/时  {p.get('day')}/天")


def cmd_images(a):
    params = {"page": a.page, "page_size": a.page_size}
    if a.cuda:
        params["cuda_version"] = a.cuda
    if a.python:
        params["python_version"] = a.python
    d = call("GET", "/image/market/list", params).get("data", {})
    print(f"共 {d.get('total')} 个镜像，第 {d.get('page')} 页")
    for im in d.get("image_list", []):
        c = im.get("components", {})
        print(f"{im.get('uuid')}  CUDA {c.get('CUDA')}  PyTorch {c.get('PyTorch')}  "
              f"Python {c.get('Python')}  Ubuntu {c.get('Ubuntu')}  "
              f"{round((im.get('size') or 0) / 2**30, 1)}G")


def cmd_create(a):
    body = {"image_uuid": a.image, "gpu_uuid": a.gpu, "gpu_nums": a.nums}
    res = call("POST", "/instance/create_by_image", body=body)
    d = res.get("data", {})
    print(f"创建成功 instance_uuid={instance_uuid_of(d)}  {status_text(d.get('status'))}  "
          f"{d.get('gpu_name')} x{d.get('gpu_nums')}")


def _simple_action(path):
    def run(a):
        res = call("POST", path, body={"instance_uuid": a.uuid})
        print(f"{path.split('/')[-1]} -> code={res.get('code')} {res.get('msg')}")
    return run


def cmd_save_image(a):
    body = {"instance_uuid": a.uuid}
    if a.name:
        body["image_name"] = a.name
    if a.remark:
        body["remark"] = a.remark
    res = call("POST", "/instance/save_image", body=body)
    print(f"save_image -> code={res.get('code')} {res.get('msg')}")
    print("保存期间实例保持运行，完成后自动关机；用 wait --field save_image_status --until 2 等它传完")


def cmd_wait(a):
    t0 = time.time()
    while True:
        d = call("GET", "/instance/info", {"instance_uuid": a.uuid}).get("data", {})
        cur = d.get(a.field)
        label = status_text(cur) if a.field == "status" else f"{cur} {SAVE_STATUS.get(cur, '未知')}"
        if cur == a.until:
            print(f"已到达目标值 {label}，耗时 {time.time() - t0:.0f}s")
            return
        if a.field == "status" and a.until == 2 and cur in STOPPED:
            sys.exit(f"实例处于 {label}，等不到运行中，请先 start")
        if a.field == "save_image_status" and cur == 3:
            sys.exit("镜像保存失败（save_image_status=3）")
        if time.time() - t0 > a.timeout:
            sys.exit(f"等待超时（当前 {label}）")
        print(f"  等待中… {label}  {time.time() - t0:.0f}s")
        time.sleep(a.interval)


def main():
    ap = argparse.ArgumentParser(description="晨羽智云开放 API 封装")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("balance").set_defaults(fn=cmd_balance)
    sub.add_parser("instances").set_defaults(fn=cmd_instances)
    p = sub.add_parser("info"); p.add_argument("uuid"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("ssh"); p.add_argument("uuid")
    p.add_argument("--show-password", action="store_true"); p.set_defaults(fn=cmd_ssh)
    sub.add_parser("gpus").set_defaults(fn=cmd_gpus)
    p = sub.add_parser("private-images"); p.add_argument("--page", type=int, default=1)
    p.add_argument("--page_size", type=int, default=20); p.set_defaults(fn=cmd_private_images)
    p = sub.add_parser("images"); p.add_argument("--page", type=int, default=1)
    p.add_argument("--page_size", type=int, default=10)
    p.add_argument("--cuda", default=""); p.add_argument("--python", default="")
    p.set_defaults(fn=cmd_images)
    p = sub.add_parser("create"); p.add_argument("--image", required=True)
    p.add_argument("--gpu", required=True); p.add_argument("--nums", type=int, default=1)
    p.set_defaults(fn=cmd_create)
    for name, path in (("start", "/instance/startup"), ("shutdown", "/instance/shutdown"),
                       ("restart", "/instance/restart"), ("destroy", "/instance/destroy")):
        p = sub.add_parser(name); p.add_argument("uuid")
        p.set_defaults(fn=_simple_action(path))
    p = sub.add_parser("save-image"); p.add_argument("uuid")
    p.add_argument("--name", default="", help="私有镜像名，需唯一")
    p.add_argument("--remark", default="")
    p.set_defaults(fn=cmd_save_image)
    p = sub.add_parser("wait"); p.add_argument("uuid")
    p.add_argument("--field", default="status", choices=["status", "save_image_status"])
    p.add_argument("--until", type=int, default=2)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--interval", type=int, default=10)
    p.set_defaults(fn=cmd_wait)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
