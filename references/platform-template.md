# Platform profile template

Copy to `references/platform-<name>.md`, fill every section, then link the new file from `SKILL.md`.

Delete the guidance lines as you fill the file; keep the headings.

## Connect

```text
ssh <user>@<host> -p <port>
```

How the instance address and credentials are obtained, and whether password or key auth is used. Note the Windows path if password auth is required.

## Hardware

| Item | Value |
| --- | --- |
| GPU | model and VRAM |
| Driver / CUDA | |
| CPU | |
| Memory | host value and **container limit** |
| Disk | root size and any large shared mounts |
| OS | |

## Software

| Item | Value |
| --- | --- |
| ComfyUI | path, version, frontend |
| Python | version and interpreter path |
| torch / triton | |
| sageattention | version, and whether `sageattn3` is present |
| comfy-kitchen | |
| Custom nodes | count and the ones this pipeline needs |

## Start command

The exact detached launch command. Note if the image ships a start script and whether that script does anything destructive.

## Model roots

Where models live, and which roots are symlinked onto shared storage. Note any root that a plain `find` will not descend into.

## Model inventory

What is pre-installed for the models this pipeline uses, and at which precisions. Note anything that is missing and would have to come from a download.

## Nodes that differ from a newer local install

Every class whose presence or input list differs. Record the replacement to use and the values it needs.

## Measured throughput

Timings per segment at a given resolution, so a later run can be compared and a regression spotted.

## Provider-specific traps

Anything surprising: destructive helper scripts, symlink layouts that mislead scanning, memory accounting, network restrictions, ports, billing behaviour.
