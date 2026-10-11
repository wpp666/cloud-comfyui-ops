---
name: cloud-comfyui-ops
description: Deploy and run ComfyUI workflows on rented GPU cloud boxes, covering SSH access, node and model verification, config adaptation, asset upload, and result retrieval. Use when moving a local ComfyUI pipeline to a cloud GPU provider such as 晨羽智云 or 仙宫云. Do not use for local-only runs.
---

# Cloud ComfyUI Ops

Move a ComfyUI pipeline that already works locally onto a rented GPU cloud box. The hard part is almost never compute; it is finding out what the image actually contains, adapting the config, and getting files in and out reliably.

Read [references/procedure.md](references/procedure.md) for the full step-by-step. Read [references/pitfalls.md](references/pitfalls.md) before the first run on an unfamiliar provider. Platform profiles are `references/platform-*.md`; start from [references/platform-chenyu.md](references/platform-chenyu.md) and copy [references/platform-template.md](references/platform-template.md) when adding a provider.

When the pipeline being moved is a local MV pipeline, the `mv-local-pipeline` skill defines its stages, scripts, and asset layout.

## Hard rules

- **Ask the server, not the filesystem.** Whether a node exists, and whether a model name is legal, is decided by `GET /object_info`. Directory scans miss symlinked model roots and miss older node packs that lack a node.
- **Never upload large model files from the local machine.** Let the cloud download them; HuggingFace and ModelScope are reachable from these boxes. Upload only artifacts the user produced: key frames, audio, prompts, manifests.
- **Keep machine paths out of pipeline scripts.** They belong in the project's `pipeline_config.json`; adapt that file per environment. A script that hardcodes a path is a script that cannot move.
- **Never write credentials into files, logs, or documentation.** Pass the SSH password through an environment variable such as `SSHPW` and leave it there.
- **Give every run its own output directory.** Use the pipeline's `--out-dir` so a new setting never overwrites a previous result and results stay comparable.
- Report generated files as clickable links and let the user judge. Do not rank candidates.

## Procedure

1. **Connect.** On Windows there is no `sshpass` and OpenSSH cannot take a password non-interactively; use [scripts/rc.py](scripts/rc.py) (paramiko, password from `SSHPW`).
2. **Probe the box.** `python rc.py 'bash -s' < scripts/probe_env.sh`, or upload and run `scripts/probe_env.sh`.
3. **Start ComfyUI detached.** `setsid nohup python3 main.py --listen 0.0.0.0 --disable-pinned-memory --enable-triton-backend > comfy.log 2>&1 < /dev/null &`
4. **Verify the graph.** Run [scripts/verify_nodes.py](scripts/verify_nodes.py) with every node class and `Class:widget` model key the pipeline needs.
5. **Write the environment config.** Model names exactly as `/object_info` reports them, plus any node that differs between local and cloud.
6. **Upload the project's own artifacts only.** Pack the files the manifest references into one tar and unpack them into the project root on the box.
7. **Dry-run, then run detached and poll.** Fetch results back with `rc.py --get`.

## Adding a provider

Copy `references/platform-template.md` to `references/platform-<name>.md` and fill it in: connect method, GPU and VRAM, ComfyUI path and version, python and key packages, which custom nodes exist, model roots, where H3-class weights live, the start command, and any provider-specific trap. Then link it from this file.
