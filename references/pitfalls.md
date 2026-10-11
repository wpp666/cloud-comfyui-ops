# Pitfalls

Cross-platform traps. Each one cost real time; check the list before the first run on a new provider.

| # | Symptom | Root cause | Do this instead |
| --- | --- | --- | --- |
| 1 | Concluded a model was missing and uploaded it, then found it already there | `find` does not follow symlinks, and model directories are usually layered symlinks onto a shared disk | Decide model availability from `GET /object_info`. Use `ls -L` / `find -L` only as a secondary check |
| 2 | Used a node that the cloud's older node pack does not have | Checked the directory listing, not the node registry | `GET /object_info/<Class>` for every class in the graph before writing config |
| 3 | Model name copied from the local machine is rejected | Provider images differ; the same weights sit under several roots (`minimax-h3/` vs `MiniMax/`) | Take names verbatim from `/object_info`; prefer the root whose filename matches the local file |
| 4 | Remote command behaved as if quotes vanished; `grep -E "a\|b"` turned into a shell pipe | PowerShell 5.1 strips embedded double quotes when passing arguments to native commands | Keep remote commands free of `"`: use `grep -e a -e b`; if quoting is unavoidable, upload a script file and run that |
| 5 | `$n:` fails to parse in PowerShell | `$var:` is read as a drive-qualified variable | Write `${n}` |
| 6 | Uploading a 500 MB model from the office takes minutes | Local egress is the bottleneck | Let the cloud download it. Only upload artifacts the user produced |
| 7 | Redirected log is empty while the job clearly runs | `python > file` block-buffers stdout when not a TTY | Run `python3 -u`, or read the server's own console log |
| 8 | A previous good result got overwritten | Fixed output directory | One `--out-dir` per configuration |
| 9 | Planned for the host's memory and hit swap | Provider reports host RAM; the container cgroup is the real limit | Read `ram_total` from `GET /system_stats` |
| 10 | A node input that works locally does nothing on the cloud | Node versions differ; unknown inputs are silently ignored, not rejected | Compare the node's `required`/`optional` lists on both sides and drop what the old build does not have |
| 11 | Process died when the SSH session ended | Started without detaching | `setsid nohup ... > log 2>&1 < /dev/null &` |
| 12 | Attention acceleration did nothing, or crashed on a new architecture | The vendor-specific attention node or kernel is missing on the cloud, or the kernel has no build for that GPU | Check what the node pack actually exposes; on Blackwell prefer the `*_triton` Sage modes over CUDA-specific ones |
| 13 | Billed time wasted on avoidable failures | Ran the paid job before verifying | Dry run + node/model verification first, then start; stop the instance once fetched |

## Rules of thumb

- Never trust a filesystem scan for capability. Trust the server.
- Never trust a model name copied from another machine.
- Server-side download beats client-side upload for anything measured in gigabytes.
- One configuration change, one output directory.
- The provider's console is a second source of truth for what is actually executing.
