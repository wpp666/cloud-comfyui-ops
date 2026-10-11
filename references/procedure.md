# Procedure

The order matters: verifying what the box has comes before writing any config, and the dry run comes before the paid run.

## 1. Connect

Windows has no `sshpass` and OpenSSH will not accept a password as an argument. `paramiko` is the reliable path.

```powershell
$env:SSHPW = "<password>"          # stays in the environment only
python scripts/rc.py "nvidia-smi"
python scripts/rc.py --put .\pkg.tar /root/mv/pkg.tar
python scripts/rc.py --get /root/mv/out/S01.mp4 .\out\S01.mp4
```

Use `AutoAddPolicy` so the first connection does not block on a host-key prompt. If the provider gives an SSH key instead of a password, plain `ssh -i` and `scp` are simpler; `rc.py` is only needed for password auth.

## 2. Probe the box

Collect facts before deciding anything:

```bash
uname -a; nvidia-smi; nproc; free -g; df -h
python3 --version; python3 -m pip list | grep -i -e sage -e triton -e torch
cat <comfy>/comfyui_version.py
ls <comfy>/custom_nodes/
ls <comfy>/models/
```

Record into the platform profile: GPU and VRAM, driver and CUDA, the **container** memory limit (not the host's), ComfyUI path and version, python version, and whether `sageattention`/`triton` are installed.

Watch the memory line carefully. A host may report 500 GB while the container cgroup caps you at 96 GB; `GET /system_stats` reports the limit that actually applies.

## 3. Start ComfyUI detached

```bash
cd <comfy>
setsid nohup python3 main.py --listen 0.0.0.0 --disable-pinned-memory \
  --enable-triton-backend > /root/mv/comfy.log 2>&1 < /dev/null &
```

All four pieces are needed. Without `setsid`/`nohup` the process dies with the SSH channel; without the redirects the channel never closes; without `/dev/null` on stdin it can hang.

Confirm with `curl -s http://127.0.0.1:8188/system_stats`.

## 4. Verify the graph against the server

This is the step that prevents every "model not found" and "node not found" failure.

```bash
python3 verify_nodes.py MiniMaxH3ReferenceToVideo PathchSageAttentionKJ VHS_VideoCombine LoadAudio \
  --model UNETLoader:unet_name --model CLIPLoader:clip_name \
  --model VAELoader:vae_name --model LoraLoaderModelOnly:lora_name --grep minimax
```

For each node class it prints required and optional input names, so wiring differences between versions are visible. For each model widget it prints the legal values, so model names come from the server rather than from a guess based on directory listing. Pasting a model name from the local machine is the most common cross-environment mistake.

## 5. Write the environment config

Adapt the project's `pipeline_config.json`:

- `projects_dir` / `comfy_root` / `server` for this box.
- Every model name exactly as `/object_info` returned it. The same file often exists under several model roots; pick the one whose filename matches the local file.
- Any node that only exists on one side. If the local box has a vendor-specific node the cloud lacks, add a config-driven switch rather than forking the script.

Also check node **inputs**, not just existence. A newer VHS build may offer `pix_fmt`, `crf`, `save_metadata`, `trim_to_audio` while an older one does not; extra inputs are silently ignored, so a feature you rely on can quietly stop applying.

## 6. Upload only your own artifacts

Never upload weights. Build a file list from the manifest, pack it, and unpack into the project root:

```powershell
python -c "import json;from pathlib import Path;R=Path('.');d=json.loads((R/'production/manifest.json').read_text(encoding='utf-8'));n=set(['production/manifest.json']);[ (n.add(t['prompt']), n.add(t['audio']), n.update(t['images_in_order'])) for t in d['tasks']];(R/'files.txt').write_text(chr(10).join(sorted(n))+chr(10),encoding='utf-8')"
tar -cf pkg.tar -C . -T files.txt
python scripts/rc.py --put pkg.tar /root/mv/pkg.tar
python scripts/rc.py "cd /root/mv && tar -xf pkg.tar -C /root/mv/<project>"
```

## 7. Dry-run, run detached, poll, fetch

```bash
cd /root/mv/<project>/production
python3 run_h3_video.py --all --dry                     # confirm segment count, frames, image order
setsid nohup python3 -u run_h3_video.py --all --out-dir <abs>/out_0p6 > /root/mv/gen.log 2>&1 < /dev/null &
```

Use `python3 -u` when redirecting to a file, otherwise stdout is block-buffered and the log looks empty until the process exits. The generator's own log is a second source of truth: ComfyUI prints its progress bar to its own console log.

Poll from the local side by listing the output directory, then `rc.py --get` each result.

## Cost discipline

The box is billed while it runs. Do the dry run, the node verification and the model-name check **before** the paid run, and stop the instance when the batch is fetched.
