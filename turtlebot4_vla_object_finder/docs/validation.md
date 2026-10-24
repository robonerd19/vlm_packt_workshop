# Runtime validation

> **Inference backend changed.** This document describes the llama.cpp server with
> Qwen2-VL-2B. The project now runs `qwen2.5vl:3b` in the official Ollama
> container (see `compose.yaml` and the README); interfaces, search, and
> navigation are unchanged, but model, latency, and memory figures here are for
> the earlier backend.

The default demo now uses TurtleBot 4 Standard in the official warehouse.
The earlier small-room results below are retained as historical evidence.

## TurtleBot 4 warehouse validation (2026-10-04)

The robot geometry, mass/inertias, collision meshes, wheel separation/radius,
OAK-D camera frames, warehouse object layout, and navigation map come from
the official Jazzy TurtleBot 4/Create3 packages. Sensor rates are reduced to
RGB-D 2 Hz and RPLIDAR 5 Hz/180 samples. A single Gazebo differential-drive
plugin owns motion; docking and hardware-status emulation are omitted.
The spawn/home pose is (-3, -1), facing the standing person.

Completed on the same 24 GB Intel x86-64 development host:

- Docker image build and geometry regression suite: 13 tests passed.
- Final mock integration passed, including missing-object failure, concurrent
  request rejection, and confirmed cancellation.
- Live RGB-D calibration/frame alignment, TF, and advancing clock passed;
  optical frame is oakd_rgb_camera_optical_frame, 320x240 RGB/32FC1 depth.
  A rendered robot-camera image was inspected.
- Real Qwen request `go to the standing person` returned bbox
  [449,166,519,562] in the normalized 0-1000 coordinate convention. Depth/TF
  produced approach goal approximately (-0.082, -0.933), and real Nav2
  succeeded (status 4). Inference took about 54 seconds with four threads.
- Real cancellation confirmed CANCELED (status 5), and a subsequent return
  home succeeded. Gazebo ground-truth pose after home was about
  (-2.790, -0.935), within the configured 0.25 m goal tolerance; the robot
  remained upright.
- Gazebo real-time-factor samples during inference were 1.0008 and 1.0000.
  These are samples, not a sustained target-hardware performance benchmark.
- The GUI-only Docker launcher connected to the warehouse, resolved its
  assets, and rendered both TurtleBot 4 and the warehouse. Exported GUI
  viewport images were visually inspected. The compact GUI used about
  666 MiB working memory; its measured cgroup peak and events are saved in
  warehouse-gui-memory.txt. The GUI cgroup reached its 768 MiB limit and
  reported reclaim events during repeated screenshots, with no swap or OOM.

The original 1 GiB simulation allocation failed during full-warehouse startup:
Gazebo was killed, with cgroup oom=1 and oom_kill=1. The revised warehouse
allocation is 1.5 GiB, alongside 3 GiB inference and 768 MiB application/Nav2
(5.25 GiB combined limits). Those running containers reported zero swap and
zero OOM/OOM-kill events after the successful tests. The earlier 1 GiB
small-room allocation is not claimed to pass this warehouse configuration.

A 240-second diagnostic recording includes the failed initial allocation and
the later warehouse trials. The largest simultaneous Docker working-memory
sum across the warehouse trials was 4.251 GiB. The final spawn/configuration
interval in that recording sampled up to 3.726 GiB; charged/reclaimable model
cache varied during the build and trials. Use 4.25 GiB as the observed
conservative working-memory figure, not as a whole-PC requirement.
Final-container cache-inclusive cgroup peaks were approximately 3.000 GiB
inference, 1.188 GiB simulation, and 0.580 GiB application. Their sum is
4.768 GiB; individual peaks are not necessarily simultaneous. Inference
had limit-reclaim events, but no OOM.

The first close-up object request failed safely for insufficient valid depth.
Moving the initial robot pose farther back gave a full-body view and the
subsequent real task passed. General VLM accuracy and arbitrary warehouse
objects remain unbenchmarked; these earlier results validated visible-object navigation before search was added.

The complete 8 GB AMD PC acceptance test is still outstanding. Host-wide
usage reached 15.130 GiB with unrelated workloads/builds and pre-existing
swap, so this host cannot prove that the entire application, OS, browser,
and optional GUI fit an 8 GB physical machine. GUI usage was measured
separately from the headless three-container recording.

Evidence in ignored artifacts/: warehouse-verification-final.log,
warehouse-sensors-final.log, warehouse-camera-final.jpg, warehouse-home.json,
warehouse-cancellation.json, warehouse-poses.txt, warehouse-stats.txt,
warehouse-resources.jsonl, warehouse-inference.log,
warehouse-final-mock-verification.log,
warehouse-gui-delivery-screenshots/, and warehouse-gui-memory.txt.

## Earlier small-room validation

Validated on 2026-10-04 in this checkout using Docker on an Intel Core
i7-13650HX x86-64 development host with approximately 24 GB installed RAM.
The intended deployment remains an AMD x86-64 PC with 8 GB RAM and AVX2.
The physical 8 GB AMD machine acceptance test has not been performed.

## Completed checks

- Native Jazzy colcon build: all six packages passed. Both Docker images built.
- Geometry regression suite: 13 tests passed inside the ROS image. Includes
  calibration, box bounds, valid depth, hollow chair/table foreground selection,
  sparse noise, mixed-depth rejection, projection, and stand-off geometry.
- Model files downloaded at a pinned revision and SHA-256 verified.
- Mock HTTP → ROS action → navigation integration passed, including a missing
  object, concurrent-request rejection (HTTP 409), and confirmed cancellation.
- Real Gazebo sensors delivered RGB, registered depth, calibration, odometry,
  scan, TF, and advancing simulated time. A rendered camera image was inspected.
- Mesa reported llvmpipe and no acceleration. No GPU devices were requested;
  llama.cpp ran with zero GPU layers and vision-projector offload disabled.
- Real Nav2 reached the manual map goal (1.0, 0.0).
- Real Qwen inference located the red chair and blue table in separate requests;
  depth and TF produced approach poses, and Nav2 returned SUCCEEDED (status 4)
  for both. Return-home navigation also passed.
- Cancellation of a real return-home Nav2 goal returned CANCELED (status 5)
  and the application reported confirmed cancellation.
- Compose configuration, browser JavaScript syntax, and robot/world XML passed
  static checks. Camera and HTTP integration were exercised; interactive browser
  clicks and browser layout were not tested because no browser was available.

The original robot tipped during turns. Front and rear caster supports and
bounded drive acceleration corrected that behavior. Regulated Pure Pursuit
with rotate-to-heading reached the tested goals. AMCL uses base_footprint and
Nav2 servers receive the complete nested costmap configuration as standalone
processes. These results use real simulation odometry and localization.

## Memory and latency

Limits stayed at 3 GiB inference, 1 GiB simulation, and 768 MiB application/Nav2;
combined limits are 4.75 GiB. Swap limits equal memory limits, disallowing
container swap. Each container reported zero swap usage, zero OOM events,
zero OOM kills, and OOMKilled=false after the object-navigation tests.

A 240-second recording spanning real chair navigation, return home, and table
inference observed a maximum simultaneous Docker working-memory sum of
**3.666 GiB**. Docker's reported working memory excludes reclaimable file cache.
Individual cgroup lifetime peaks, which include charged cache, were:

- Inference: 3.000 GiB.
- Simulation: 0.647 GiB.
- Application/Nav2: 0.372 GiB.

Their sum is 4.019 GiB; these individual peaks need not occur simultaneously.
Inference reported memory-limit reclaim events (`memory.events max = 1774`),
but no OOM. Its cache-inclusive peak reached the configured ceiling; it does
not have demonstrated cache-inclusive headroom under that ceiling.

Chair inference took approximately 47 seconds with four inference threads
on this host. This is a latency sample, not an AMD CPU performance guarantee.
Allow time for image inference before expecting navigation to start.

Host-wide usage peaked at 13.647 GiB with approximately 3.6 GiB of pre-existing
host swap in use. This host runs unrelated applications and containers; those
numbers cannot establish that the whole demo PC fits within 8 GB. The project
containers ran without swap, but the OS, browser, Docker overhead, cold model
loading, and sustained simulation performance must still be measured together
on the target 8 GB AMD machine. Simulation real-time factor was not benchmarked.

## Local evidence and reproduction

Generated logs and model assets are ignored by Git. Evidence from this run is
in `artifacts/`: `simulation-verification.log`, `table-verification.log`,
`home-after-chair.ndjson`, `real-cancellation.json`, `manual-nav.log`,
`mock-verification.log`, `camera-later.jpg`, and `resources-final.jsonl`.

Follow the commands in [README](../README.md) to rebuild, run the mock checks,
launch the simulation, verify real navigation, and measure the target machine.
These historical runs required visible targets. The new bounded search is described
in README; two successful objects are not an accuracy benchmark.


## Bounded object search (2026-10-04)

The navigator now checks the current view, scans eight headings while stopped,
then visits up to three connected, clearance-safe map viewpoints. Nav2 owns all
motion. Each view requires a new stationary RGB-D frame. A fully framed candidate
requires a separate cropped-image identity confirmation before depth projection
and approach. Its final form describes the crop without naming the target, then
normalizes common object-class synonyms and checks requested attributes. Unknown
classes fall back to a short text-only comparison. The 900-second search budget
reserves both visual-call timeouts plus the optional 15-second text comparison.

- All 22 geometry, map-connectivity, clipped-box, and identity-contract tests passed
  in the rebuilt ROS image.
- Final mock HTTP → ROS integration passed: a hidden fixture was found after
  turning; an absent object exhausted eight views across two configured viewpoints;
  concurrent requests returned HTTP 409; approach and search cancellation returned
  action status 5. Mock configuration uses four headings and one map location.
- The real CPU model/Gazebo search test, before the final identity-check refinement, began with TurtleBot 4 facing away from the person.
  The first two views produced boundary-clipped shelf detections, which were
  skipped. The third view showed the actual person, produced normalized box
  `[343,161,420,562]`, and passed cropped identity confirmation. Nav2 succeeded
  with action status 4 at target `(-0.0843, -0.8152)` metres after 224.4 seconds.
  Saved third-view and arrival images were inspected and show the person.
- The final rebuilt application also passed the real HTTP → RGB-D detection →
  independent crop description → class/attribute check → Nav2 pipeline at home:
  normalized person box `[451,161,519,562]`, target `(-0.0816,-0.9332)`, and
  successful action status 4. This final run validated the revised checker
  integrated with navigation; the preceding rotated-view search run validated
  search motion, with the earlier checker.
- The final identity checker was tested directly on saved real camera crops:
  floor markings were labelled "yellow pen" and rejected as a person; the actual
  person was labelled "man in purple shirt and khaki shorts standing in front of
  an orange door" and accepted. This tests the same model and crop-check function
  used by the navigator. Descriptions themselves can still be wrong.
- A map-selected viewpoint at `(-5.9950, -0.7450)` was reached by real Nav2 in
  Gazebo, followed by a successful return home. This was an isolated Nav2 action
  test of viewpoint reachability; the automatic transition to mapped search was
  covered by the mock integration.
- Earlier trials exposed shelf/floor false positives. Navigation success alone
  was insufficient evidence that the requested object had been found; these trials
  motivated the framing and identity checks. The small VLM can still misidentify
  objects, and this is not an accuracy benchmark.

Evidence: `artifacts/search-real-verification.log`, `search-view-1.jpg` through
`search-view-3.jpg`, `search-person-arrival.jpg`, `search-final-mock-verification.log`,
`search-identity-verification.log`, `search-map-navigation.log`,
and `search-confirmed-resources.jsonl`. The initial failed trials are retained in
`search-initial-false-positive.log` and `search-clipped-only-verification.log`.

Whole-warehouse coverage and a physical 8 GB AMD PC remain unvalidated. This is
bounded search on an existing map, not SLAM or an exhaustive search guarantee.


During a 120-second measurement of the deployed preset, the three demo containers
peaked at a sampled combined Docker usage of 4.131 GiB. Cgroup peaks were about
3.000 GiB inference, 1.218 GiB simulation, and 0.450 GiB application (individual
peaks are not necessarily simultaneous). Each reported zero OOM/kill events and
zero container swap. Inference reclaimed memory at its 3 GiB limit. The host also
ran unrelated applications and an isolated mock-test container during part of the
measurement, so host-wide figures do not validate an 8 GB PC. See
`search-deployed-resources.jsonl` and `search-delivery-memory.json` for the raw data.

## CPU/GPU selection (2026-10-04)

The CUDA image was built and tested on an NVIDIA RTX 4060 Laptop GPU (8 GB
VRAM), driver 580.173.02, compute capability 8.9. Both inference images use the
same pinned llama.cpp revision and Qwen2-VL model/projector files.

- `bash scripts/run_demo.sh --device gpu` started CUDA inference. The model
  process used 2,518 MiB VRAM after loading and 2,614 MiB during the test.
- With the robot first rotated away from the standing person, the HTTP/ROS
  verification required search motion and multiple camera checks. Detection,
  cropped identity confirmation, and Nav2 approach completed with action status
  4. The resulting approach target was approximately `(-0.071, -0.834)`.
- A CPU switch attempted during that request exited with the active/moving
  guard message, without replacing inference.
- After completion, `--device cpu` replaced inference with the CPU image and
  removed Docker GPU device reservations. Simulation and application container
  IDs stayed identical, the application remained ready, and a subsequent home
  request succeeded with action status 4.
- The CPU image rejects GPU mode without a CUDA device. The CUDA image started
  without Docker GPU access also exited unsuccessfully (missing host
  `libcuda.so.1`); it did not fall back to CPU inference.
- Shell syntax and resolved CPU/GPU Compose configurations passed validation.

During the GPU portion of the resource capture, 15 samples peaked at a combined
Docker memory usage of 2.147 GiB across the three services, in addition to GPU
VRAM. The capture then includes the switch back to CPU; its final cgroup peaks
must not be interpreted as GPU-only measurements. This was a 24 GB Intel host,
so it does not validate a physical 8 GB AMD PC.

Evidence: `artifacts/gpu-search-verification.log`, `gpu-inference.log`,
`gpu-turn-away.log`, `gpu-vram.txt`, `gpu-mode-resources.jsonl`,
`gpu-active-switch-guard.log`, `gpu-no-device-guard.log`, `cpu-mode-switch.log`,
`gpu-ros-container-ids.txt`, `cpu-ros-container-ids.txt`, and
`cpu-switch-home.jsonl`. The demo was stopped after verification.
