# -*- coding: utf-8 -*-
"""临时工具：通过 SSH 在云主机上执行命令 / 传文件。
密码从环境变量 SSHPW 读取，不落盘。
  python rc.py <shell command>
  python rc.py --put <local> <remote>
  python rc.py --get <remote> <local>
"""
import os
import sys

import paramiko

HOST = os.environ.get("SSHHOST", "02104a3b093b456ca37637c64368046c71.gz14.chenyu.cn")
PORT = int(os.environ.get("SSHPORT", "28844"))
USER = os.environ.get("SSHUSER", "root")
PW = os.environ["SSHPW"]


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PW,
              timeout=30, banner_timeout=60, auth_timeout=60)
    return c


def run(cmd, timeout=600):
    c = connect()
    try:
        _, so, se = c.exec_command(cmd, timeout=timeout)
        out = so.read().decode("utf-8", "replace")
        err = se.read().decode("utf-8", "replace")
        return so.channel.recv_exit_status(), out, err
    finally:
        c.close()


def main():
    if sys.argv[1] == "--put":
        c = connect()
        try:
            sftp = c.open_sftp()
            sftp.put(sys.argv[2], sys.argv[3])
            print(f"put ok -> {sys.argv[3]}")
        finally:
            c.close()
        return
    if sys.argv[1] == "--get":
        c = connect()
        try:
            sftp = c.open_sftp()
            sftp.get(sys.argv[2], sys.argv[3])
            print(f"get ok -> {sys.argv[3]}")
        finally:
            c.close()
        return
    rc, out, err = run(" ".join(sys.argv[1:]))
    print(f"[rc={rc}]")
    if out:
        print(out)
    if err.strip():
        print("--- stderr ---")
        print(err)


if __name__ == "__main__":
    main()
