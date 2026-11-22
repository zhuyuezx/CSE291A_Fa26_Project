# Phase 2 fleet: AWS deployment

Four inference endpoints (two CPU, two GPU) and one router node, all in one Region and one subnet. Every endpoint serves the **same model file** (Qwen3.5-2B Q4_K_M, SHA-256 `aaf42c8b…`) with the same llama.cpp release (`b12617`). Differences in speed therefore come from the hardware, not the model.

## Fleet

| ID | Instance | Hardware | Memory | On-demand $/h | Role |
|---|---|---|---|---|---|
| C1 | `c7g.xlarge` | Graviton3 (Arm), 4 vCPU = 4 cores | 8 GiB | 0.145 | CPU endpoint |
| C2 | `c7i.xlarge` | Xeon Sapphire Rapids (x86, AVX-512 + AMX), 4 vCPU = 2 cores × 2 threads | 8 GiB | 0.179 | CPU endpoint |
| G1 | `g6f.large` | 1/8 NVIDIA L4, **3 GB VRAM**, 2 vCPU | 8 GiB | ~0.20 | small GPU |
| G2 | `g4dn.xlarge` | NVIDIA T4, 16 GB VRAM, 4 vCPU | 16 GiB | 0.526 | full GPU |
| R | `c7g.large` | Graviton3, 2 vCPU | 4 GiB | ~0.07 | router + load generator |

Fleet total: about **$1.12/h** (us-west-2 list prices, Nov 2026; G1 price is from us-east-1). An 8-hour session costs about $9, well under the $20/day cap.

What each pair varies:

- **C1 vs. C2:** CPU architecture at equal vCPUs, memory, and roughly equal price. C2 has half the physical cores, because an x86 vCPU is a hyperthread.
- **G1 vs. G2:** GPU share and VRAM. G1 is a slice of a GPU with 3 GB, close to an edge accelerator. The 2B model plus its vision projector (1.95 GB) fits; the 4B (3.4 GB) does not. G2 is a whole older GPU.
- **CPU vs. GPU:** the GPUs should be much faster when idle. Whether the CPU nodes still help when the GPUs are busy is the main question Phase 2 has to answer from measurements.

## Before launching

1. **Region:** launch everything in one Region (us-west-2 suggested). Check that `g6f.large` is offered there by searching for it in the instance-type picker.
2. **Quotas** (Service Quotas → Amazon EC2). New accounts often start the GPU quota at 0, and raising it can take a day.
   - *Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances*: at least **10** vCPUs (C1 + C2 + R).
   - *Running On-Demand G and VT instances*: at least **6** vCPUs (G1 + G2).
3. **Security group** `cse291a-fleet`:
   - Inbound TCP 22 from *My IP*.
   - Inbound TCP 8080 from the security group itself (source: the group's own `sg-…` id).
   - Never open 8080 to `0.0.0.0/0`: llama-server has no authentication.

## Launch settings (EC2 console)

| Node | AMI | Root volume |
|---|---|---|
| C1, R | Ubuntu Server **26.04** LTS, **64-bit (Arm)** | 30 GB gp3 (R: 20 GB) |
| C2 | Ubuntu Server **26.04** LTS, 64-bit (x86) | 30 GB gp3 |
| G2 | *Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)*: includes the driver and CUDA | AMI default |
| G1 | Ubuntu Server 24.04 LTS, 64-bit (x86), plus the GRID driver (see below) | 40 GB gp3 |

The CPU nodes share one OS release, so C1 and C2 build llama.cpp with the same compiler. The GPU nodes use 24.04, which NVIDIA's drivers support. `node_info.txt` records the OS and compiler on every node.

For every node:

- Use the team key pair (`.pem`).
- Under *Network settings → Edit*, pick the **same subnet**, so all nodes share one Availability Zone. Select the `cse291a-fleet` security group.
- Add the tags `Project=cse291a` and `Name=C1`, `C2`, and so on.
- Under *Advanced details*, set *Shutdown behavior* to **Stop**.

## Set up an endpoint

From the repo root on your machine:

```bash
scp -i team.pem Phase2/deploy/setup_node.sh ubuntu@<public-ip>:
ssh -i team.pem ubuntu@<public-ip> 'bash setup_node.sh'
```

The script installs build tools and builds llama.cpp `b12617` (CUDA when a GPU is present). It downloads and hash-checks the 0.8B and 2B models, starts `llama-server` on port 8080 under systemd, and writes `/opt/llm/node_info.txt`. A CPU build takes a few minutes; the CUDA build is slower, especially on G1's 2 vCPUs. Re-running the script is safe.

Check a node from any other node in the security group:

```bash
curl http://<private-ip>:8080/health
curl http://<private-ip>:8080/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Say hi"}],"max_tokens":16}'
```

The response's `timings` field gives prefill and decode token counts and milliseconds.

For a first prefill and decode comparison, stop the server so the benchmark has the machine to itself:

```bash
sudo systemctl stop llama-server
source /opt/llm/server.env
/opt/llm/llama.cpp/build/bin/llama-bench -m "$MODEL_PATH" -t "$THREADS" -ngl 99 -p 512,2048 -n 128 -r 3
sudo systemctl start llama-server
```

To change server settings (slots, context, model), edit `/opt/llm/server.env` and run `sudo systemctl restart llama-server`. To serve a different staged model, re-run the script with `SERVE=qwen3.5-0.8b bash setup_node.sh`.

## G1 (g6f) driver

Fractional-GPU instances need the **NVIDIA GRID driver, between versions 18.4 and 19.5**, not the standard data-center driver. The Deep Learning AMI that G2 uses does not support G6f, so G1 starts from plain Ubuntu 24.04. See AWS's [GRID driver instructions](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/nvidia-GRID-driver.html).

The driver lives in the S3 bucket `ec2-linux-nvidia-drivers`, which needs AWS credentials to read. Instead of giving the instance an IAM role, make a temporary download link in CloudShell:

```bash
aws s3 ls --recursive s3://ec2-linux-nvidia-drivers/ | grep -E 'grid-(18\.[4-9]|19\.[0-5])/.*\.run$'
aws s3 presign s3://ec2-linux-nvidia-drivers/<key from the list> --expires-in 3600
```

On the instance, install `build-essential` and the kernel headers, blacklist `nouveau` and reboot, download the driver with the link, and run the installer. Then install the CUDA toolkit without its driver (from NVIDIA's apt repository, matching the driver's CUDA version), check `nvidia-smi`, and run `setup_node.sh`.

Set G1 up last. If the driver takes more than an hour, continue with C1, C2, and G2: that still meets the option's requirement of two CPU instance types.

## Cost hygiene

- **Stop** (not terminate) every node at the end of a session. The disk keeps the build and models, at about $0.08 per GB-month.
- Add a CloudWatch alarm on each instance (*Actions → Monitor and troubleshoot → Manage CloudWatch alarms*) that **stops** the instance when average CPU is below 5% for 1 hour.
- Terminate everything once the final runs are done.
