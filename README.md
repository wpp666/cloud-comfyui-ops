# cloud-comfyui-ops

An agent skill for deploying and running ComfyUI workflows on rented GPU cloud boxes.

The hard part of moving a working local pipeline to a cloud GPU is almost never compute. It is finding out what that image actually contains, adapting the config, and getting files in and out reliably. This skill packages that procedure plus a growing set of per-provider profiles.

## What it covers

- Connecting to a rented GPU instance over SSH, including password auth from Windows.
- Probing the box: GPU, **container** memory limit, ComfyUI version, python packages, custom nodes, egress.
- Verifying that every node class and every model name a graph needs actually exists on that box.
- Adapting an environment config file instead of editing pipeline scripts.
- Uploading only self-produced artifacts and letting the cloud download the weights.
- Running detached, polling, and fetching results back.

## Layout

```text
SKILL.md                      procedure, hard rules, how to add a provider
references/procedure.md       the 7-step walkthrough with commands
references/pitfalls.md        13 cross-provider traps
references/platform-chenyu.md 晨羽智云 profile (RTX 5090 instance)
references/platform-template.md  template for a new provider
scripts/rc.py                 SSH exec / put / get (paramiko, password from SSHPW)
scripts/probe_env.sh          one-shot environment probe
scripts/verify_nodes.py       validate node classes and model names via /object_info
```

## Install

Copy this directory into your agent's skills folder, for example:

```text
~/.trae-cn/skills/cloud-comfyui-ops/
```

## Quick start

```powershell
$env:SSHPW = "<ssh password>"
python scripts/rc.py --put scripts/probe_env.sh /root/mv/probe_env.sh
python scripts/rc.py "bash /root/mv/probe_env.sh"
python scripts/rc.py "python3 /root/mv/verify_nodes.py MiniMaxH3ReferenceToVideo --model UNETLoader:unet_name --grep minimax"
```

## Adding a provider

Copy `references/platform-template.md` to `references/platform-<name>.md`, fill in every section, then link the new file from `SKILL.md`. The generic layer (procedure and pitfalls) does not change per provider.

## Security

Scripts read the SSH password from the `SSHPW` environment variable and never write it to disk. No credentials, hostnames or tokens are stored in this repository.
