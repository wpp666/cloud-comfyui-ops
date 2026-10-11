# Platform profile: 晨羽智云 (chenyu.cn)

Verified 2026-10-12 on a 5090 instance. Re-verify after a provider image update.

## Connect

```text
ssh root@<instance-id>.<region>.chenyu.cn -p <port>
```

Instance host, port and root password come from the console. On Windows use `scripts/rc.py` with `SSHPW`; there is no `sshpass`.

## Hardware

| Item | Value |
| --- | --- |
| GPU | RTX 5090, 32607 MiB (32 GB) |
| Driver / CUDA | 610.43.02 / UMD 13.3 |
| CPU | 192 cores |
| Memory | host 503 GB, **container limit 96 GB** |
| Disk | root overlay 100 GB free; shared `/models`, `/chenyudata` on large mounts |
| OS | Ubuntu 24.04.1, kernel 6.8 |

## Software

| Item | Value |
| --- | --- |
| ComfyUI | `/root/ComfyUI`, version **0.37.0**, frontend 1.53.6 |
| Python | `python3` 3.12.3 |
| torch | 2.8.0+cu128 |
| triton | 3.4.0 |
| sageattention | 2.2.0 (**no** `sageattn3` package) |
| comfy-kitchen | 0.2.35 |
| Custom nodes | 67, including `comfyui-kjnodes` and `comfyui-videohelpersuite` |

## Start command

```bash
cd /root/ComfyUI
setsid nohup python3 main.py --listen 0.0.0.0 --disable-pinned-memory \
  --enable-triton-backend > /root/mv/comfy.log 2>&1 < /dev/null &
```

There is also `/root/restart.sh`, but it also runs `/root/link.sh`, which re-creates a large symlink tree and is much slower. Prefer the direct command.

## Model roots

```text
/root/ComfyUI/models/diffusion_models/{MiniMax, minimax-h3, minimax-h3-other}/
/root/ComfyUI/models/text_encoders/{MiniMax, minimax-h3}/
/root/ComfyUI/models/vae/{MiniMax, minimax-h3}/
/root/ComfyUI/models/loras/{MiniMax, minimax-h3}/
```

Everything is a symlink into `/chenyudata/ComfyUI/models`. **A bare `find` will not descend into these**, which is how a model can look missing while it is present. `minimax-h3/` holds the set whose filenames match a typical local install.

## MiniMax H3 inventory (pre-installed)

| Kind | Options |
| --- | --- |
| ref2va | `pruned_int8_convrot` 20G · `int8_convrot` 32G · `pruned_fp8_scaled` 20G · `pruned_nvfp4_convrot_int8` · `bf16` 62G |
| fl2va | `int8_convrot` 32G · `pruned_int8_convrot` · `bf16` 62G |
| hybrid | `minimax-h3-other/minimax_h3_hybrid_fl2va_ref2va_b25-49-int8` |
| text encoder | `int8_convrot` 26G · `int4_convrot` 14G · `nvfp4_awq` 15G · `bf16` 48G · `Q4_K_M.gguf` 14G |
| video VAE | `fp16` 4.9G · `int8_convrot` 3.0G |
| audio VAE | `fp32` 578M |
| accel LoRA | `MiniMax-H3-Ref2VA-Acc-8Step_comfy` (ref2va, 8-step) · `lightx2v_turbo_4step_v0.1` · `fl2v_turbo_8step_v1.0` and other turbo variants |

MoE text encoders also exist in GGUF form, which needs the GGUF CLIP loader rather than plain `CLIPLoader`.

## Nodes that differ from a newer local install

- `MiniMaxH3MemoryEfficientSageAttentionPatch` — **absent**. Use `PathchSageAttentionKJ` with `sage_attention` set to `sageattn_qk_int8_pv_fp16_triton` (Blackwell; the CUDA-specific kernels are less reliable on sm_120).
- `VHS_VideoCombine` — older build: `required` is `images, frame_rate, loop_count, filename_prefix, format, pingpong, save_output`; `optional` is `audio, meta_batch, vae`. It has **no** `pix_fmt`, `crf`, `save_metadata`, `trim_to_audio`. Extra inputs are ignored, so H.264 output still works but those knobs do nothing.

## Measured throughput (MiniMax H3, 832x480, 24 fps, same prompts and assets)

| Config | S01 | S02 |
| --- | --- | --- |
| pruned int8 + 4-step | 105 s | 85 s |
| full int8 32G + 8-step | 160 s | 131 s |

Roughly 3.3–3.9x a local RTX 3070 Ti on the same settings.

## Provider-specific traps

- `/root/ComfyUI/models/vae/MiniMax/` is a real directory while its siblings are symlinked trees; a plain `find` at depth 3 will find files there but miss the symlinked roots. Verify against `/object_info`, not `find`.
- `link.sh` performs a destructive-looking symlink rebuild and also copies two `Joy_caption` adapter configs. Do not run it casually.
- Memory: `free -g` shows the host. Plan against `ram_total` from `GET /system_stats` (96 GB here), otherwise a 62 GB bf16 model plus a 26–48 GB text encoder will swap.

## Instance lifecycle over the open API

Everything the console does is available over the open API, which makes the whole rent → run → fetch → destroy loop scriptable. Use [scripts/chenyu_api.py](../scripts/chenyu_api.py); the key is read from `CHENYU_API_KEY` and never written to disk.

```text
Base URL   https://www.chenyu.cn/api/open/v2
Auth       Authorization: Bearer <API key>
Docs       https://enterprise.chenyu.cn/api-reference/introduction
```

| Operation | Method and path |
| --- | --- |
| Balance | `GET /balance/info` |
| Instances | `GET /instance/list` |
| Instance detail, including `server_map` with SSH host / port / user / password | `GET /instance/info?instance_uuid=` |
| GPU models and prices | `GET /gpu/list` |
| Market images | `GET /image/market/list` |
| Create from image | `POST /instance/create_by_image` with `{image_uuid, gpu_uuid, gpu_nums}` |
| Start / shutdown / restart / destroy | `POST /instance/{startup,shutdown,restart,destroy}` with `{instance_uuid}` |
| Scheduled shutdown, idle shutdown, rename, save as image | `POST /instance/{set_shutdown_timer,set_idle_close,update_title,save_image}` |

Instance status: `0` created, `1` booting (first boot), `2` running, `3` / `21` shutting down, `4` / `22` powered off, `23` powered off (abnormal), `24` booting, `27` restarting. Wait for `2` before connecting.

`server_map` returns the SSH credentials, so no manual copy-paste is needed to drive `rc.py`:

```powershell
$env:CHENYU_API_KEY = "sk-..."
python scripts/chenyu_api.py ssh <instance_uuid>          # host / port / user, password masked
python scripts/chenyu_api.py ssh <instance_uuid> --show-password
```

### Known-good identifiers for this account

```text
gpu_uuid   a7f3d92e4c5b4a7e9b8c6f1e2d3a4b5c   NVIDIA GeForce RTX 5090
image_uuid 5d032d73ca9941ea976b5410bfd9fd2d   image 4035b0d9f87447cd858f981f7e0d5faa:v2.7
```

### Cost-saving loop

The instance bills while it runs, so create it for the job and get rid of it afterwards.

```text
1. chenyu_api.py create --image <image_uuid> --gpu <gpu_uuid>
2. chenyu_api.py wait <instance_uuid>                  # until status 2
3. chenyu_api.py ssh <instance_uuid> --show-password   # feed host/port/user into rc.py
4. upload the scripts and the project artifacts, start ComfyUI, dry run
5. run the batch, poll, fetch the results
6. chenyu_api.py shutdown <instance_uuid>              # keep the disk, quick to resume
   chenyu_api.py destroy  <instance_uuid>              # work is finished, release everything
```

Two rules before you destroy:

- **`destroy` wipes the whole overlay**, including everything deployed under `/root`. Weights on the shared mounts (`/chenyudata`, `/models`) survive; your project tree does not. Keep the local project and the upload package so a fresh instance can be re-seeded in a couple of minutes.
- **Never shut down or destroy an instance with a batch still running.** Check the output-file count and the generator process first.

