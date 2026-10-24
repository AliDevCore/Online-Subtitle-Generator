# Performance & Hardware Resource Management

OnlineSub provides a dedicated **Performance Settings** subsystem to configure and balance local hardware utilization.

---

## 1. Initial Defaults

The application defaults are strictly initialized as:

| Parameter | Default Value | Description |
|---|---|---|
| **CPU Usage Target** | `100%` | Maximum local CPU performance without intentional throttling |
| **Process Priority** | `Normal` | Standard Windows scheduling priority |
| **CPU Threads** | `Automatic` | Allocates physical cores to prevent thread oversubscription |
| **RAM Limit** | `Automatic` | System memory budget with pre-flight checks |

---

## 2. Strict Separation: Local Workloads vs. Cloud Processing

A fundamental architectural guarantee in OnlineSub is the strict boundary between local resource controls and remote cloud API execution:

### Local Workloads (Controlled by Performance Settings)
- Local FFmpeg media probing and audio segment slicing.
- Format conversions and resamplings.
- Local Faster-Whisper ASR inference (CTranslate2 CPU threads and memory).
- Local SRT serialization, chronological cue merging, and validation.

### Cloud Workloads (Excluded from Local Throttling)
- When using **Google Gemini**, **Cloudflare Workers AI**, or **Hugging Face**, speech transcription and translation run entirely on remote servers.
- OnlineSub **never** artificially throttles execution during network wait states.
- Setting a CPU Usage Target of 50% will regulate local FFmpeg preprocessing without slowing down remote HTTP request exchanges.

---

## 3. Best-Effort Local CPU Controller Mechanism

The `ResourceController` operates via an adaptive closed-loop feedback design:

1. **Measurement & Normalization**: Measures `psutil.Process().cpu_percent()` divided by the logical core count to obtain true whole-system utilization for the application.
2. **Smoothing & Hysteresis**: Applies exponential moving average smoothing ($\alpha = 0.3$) with a $5\%$ hysteresis band to prevent rapid oscillations.
3. **Adaptive Back-Off**: When local CPU-intensive processing exceeds the configured target (e.g. 50%), the controller introduces dynamic millisecond pauses ($5\text{ms} - 35\text{ms}$) between chunk processing steps.
4. **100% Target Rule**: When the CPU Usage Target is $100\%$ (default), the controller completely bypasses throttling logic.

---

## 4. Hardware Detection & Memory Safety

At startup and inside the Performance Settings dialog, OnlineSub inspects the host hardware:
- Detects CPU manufacturer and model name via Windows Registry.
- Counts physical cores and logical processors.
- Queries total and available RAM.
- Inspects GPU devices via CimInstance `Win32_VideoController`.
- **Pre-flight RAM warnings**: Before initializing local Faster-Whisper models (e.g. `medium` requiring $\sim 5\text{ GB}$ RAM), OnlineSub warns the user if available system memory is insufficient.
