# MANUS AD LUNAM — control deck v1.0.0 review

**Review date:** 2026-10-17
**Repository:** `Hanoon-Shameer/Manus-AD-Lunam`
**Reviewed revision:** `367724a` (`main`, at review time)
**Related issue:** [#8 — Review current stage of control deck (v1.0.0)](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/issues/8)

## Executive summary

The repository contains a working-prototype architecture spanning a Python desktop control deck, two ESP32 firmware sketches, and an Android AR terrain scanner/streamer. The main feature paths are present in code, but there is not enough evidence to call the whole system a validated or production-ready v1.0.0. The largest readiness gaps are safety behavior on loss of control packets, speed control not reaching the motors, unreliable camera failure handling, and unverified Android/firmware builds. The project also lacks usable setup and hardware documentation and has only template-level tests.

No application or firmware source was changed as part of this review. Findings below describe code-level behavior and should be checked against the actual rover, camera, ESP32 board versions, and intended operating environment before field use.

## Scope and validation performed

The review covered tracked text-based source, tests, build configuration, Android XML resources, README, and release-artifact metadata across `control_center/`, `firmware/`, and `mesh_mobile_app/`. Binary images and release packages were inventoried, not reverse-engineered as source. The current checkout is at commit `367724a`.

- All six Python files passed Python 3.12 syntax parsing. This does not validate imports, device access, GUI behavior, or serial/hardware behavior.
- The Android Gradle wrapper is not executable in the checkout (`./gradlew test` fails with permission denied). Invoking it as `bash gradlew test` downloaded Gradle 9.4.1 but stopped before compilation because no Android SDK location is configured (`ANDROID_HOME` or `sdk.dir` is missing). Android tests therefore did **not** run; this is an environment/build prerequisite failure, not evidence that the app passes or fails compilation.
- `arduino-cli` is not available in this environment, so firmware compilation was not performed.
- No attached rover, ESP32s, ultrasonic sensor, servo, camera, or Android ARCore device was available for hardware/integration testing.

## What the repository currently implements

### Desktop control deck (`control_center/`)

- A PyQt6 dashboard with operator and rover camera panels, connection/payload/radar cards, and a collapsible system log (`ui_dashboard.py`).
- A startup source dialog for a gesture-camera index/source and rover MJPEG URL.
- OpenCV camera capture on QThreads and MediaPipe hand landmark detection (`stream_manager.py`, `hand_detector.py`).
- Gesture-to-command mapping, including forward/reverse and left/right combinations, with a small frame debounce (`gesture_controller.py`).
- WASD keyboard control that overrides gesture input while keys are held (`ui_dashboard.py`). Commands are represented as `F`, `B`, `S`, `FL`, `FR`, `BL`, and `BR`.
- Serial discovery/connection to an ESP32, newline-delimited command transmission, and parsing of `RADAR:<angle>:<distance>` lines for the UI (`serial_sender.py`).
- Radar angle, distance, range bar, and stale/no-data status display.

### ESP32 firmware (`firmware/`)

- `rover_transmitter.ino` reads a potentiometer, sends command/speed data to a hard-coded receiver MAC over ESP-NOW, and relays radar telemetry to the desktop serial port.
- `rover_reciever.ino` controls motor direction pins, sweeps a servo-mounted ultrasonic sensor, and returns angle/distance telemetry to the transmitter over ESP-NOW.
- Both sketches contain compatibility branches for ESP32 Arduino core 2.x/3.x callback signatures.

### Android app (`mesh_mobile_app/`)

- An ARCore-based camera view, automatic depth-mode attempt, depth-image sampling, and a generated 3D terrain mesh with a grid shader (`MainActivity.kt`, `TerrainMesh.kt`, `TerrainRenderer.kt`, `MeshRenderer.kt`, `BackgroundRenderer.kt`).
- A TCP MJPEG server on a user-selected port, camera-frame capture/downscaling, client status and local IP display (`MjpegServer.kt`, `TerrainRenderer.kt`).
- A basic launch screen, stream controls, notifications, and Android camera permission flow.

## Findings and recommended actions

### High priority — safety, correctness, and release blockers

1. **The rover has no command-loss stop/watchdog.** The receiver changes motor GPIO outputs when a command arrives, but the loop does not track command age or stop when ESP-NOW packets stop. A lost transmitter link can therefore leave the rover driving with the last output state. Add a receiver-side command timeout that immediately calls `stopMotors()`, and test the timeout under packet loss and power-cycle scenarios. (`firmware/rover_reciever.ino` — receive callback and main loop.)

2. **The transmitted speed value is not applied to the motors.** The transmitter packet contains `command[4]` plus a `speed` byte derived from the potentiometer. The receiver's `GestureMessage` only defines the four command bytes, and its movement functions use `digitalWrite`; there is no PWM output path. The potentiometer therefore does not produce variable rover speed. The wire structs and payload lengths should be made identical, and PWM-capable motor-driver outputs should apply a bounded speed value. (`firmware/rover_transmitter.ino` — `GestureMessage`, `loop()`; `firmware/rover_reciever.ino` — message struct and motor functions.)

3. **Camera read failure can busy-spin indefinitely.** `CameraThread.run()` immediately continues when `cap.read()` fails. A disconnected, invalid, or unavailable camera can consume CPU continuously; there is no retry delay, reconnect policy, visible state update, or `try/finally` release path. `stop()` waits for the thread, so a blocked capture read may also make shutdown sluggish. Add bounded backoff/reconnect, feed-state signals, and guaranteed capture cleanup. (`control_center/stream_manager.py` — `run()` and `stop()`.)

4. **The desktop feed status is not connected to actual feed state.** The dashboard initializes the video status card as “ONLINE” and does not update it when camera reads fail. The frame-latency value is computed from the interval between GUI frame callbacks, not capture-to-display latency. Both labels can give operators a misleading view of system health. Expose real camera state and rename/redefine the timing metric. (`control_center/ui_dashboard.py` — dashboard setup and `update_gesture_feed()`.)

5. **MJPEG server bind failure leaves the server marked as running.** `MjpegServer.start()` sets `isRunning = true` before binding. If the bind throws, the catch path reports failure but does not reset the flag. A later start request then returns early because `isRunning` is still true; users may have to force a stop/recreate the server before retrying. Reset state and release any partially-created socket on failure, then test retry after a port conflict. (`mesh_mobile_app/.../MjpegServer.kt` — `start()`.)

6. **The MJPEG camera feed is exposed on every network interface without access control.** The server binds to `0.0.0.0`, uses cleartext HTTP, and has no authentication or client allowlist. Anyone able to reach the selected port on the connected network may be able to view the live camera stream. Make the exposure explicit, restrict the bind/interface where possible, and add an access-control option appropriate to the expected network. Do not assume a private Wi-Fi network is trusted. (`mesh_mobile_app/.../MjpegServer.kt` — socket bind and HTTP response.)

7. **ARCore/depth unavailability is not a clean launch failure.** The app only checks `isSupported`, does not implement the usual install/update request flow, and proceeds to show the AR view after the check even when initialization returns early. When depth is unsupported it still launches the terrain rendering path, which then silently receives no depth data. Keep the start screen usable on failure, distinguish ARCore availability/install/update from depth support, and either provide a meaningful fallback or disable the scanner with an actionable message. (`mesh_mobile_app/.../MainActivity.kt` — `startScanner()` and `checkArCoreAndDepth()`; `TerrainMesh.kt` — depth acquisition.)

8. **Release builds and integration have not been validated.** The desktop release ZIP is a Git LFS pointer in this checkout, not an extracted ZIP (`control_center/release/v1.0.0.zip` points to a 486,285,457-byte LFS object). The Android APK is tracked as a 14 MB binary, but it was not shown to be reproducibly generated from this revision. The Android test task was blocked by missing SDK configuration, and firmware compilation was unavailable. Document and automate repeatable desktop, Android, and firmware build/release steps before declaring the version validated.

### Medium priority — behavior and robustness

9. **Gesture detection depends on hand orientation and heuristic landmarks.** Finger extension is based on fingertip Y being above the PIP Y coordinate; the thumb test compares horizontal tip-to-index distance with a vertical wrist-to-index distance. Tilted or rotated hands can be misclassified. Test the gesture vocabulary under expected operator poses, normalize against hand size/orientation, and provide an on-screen recognized-command indicator before transmission. (`control_center/gesture_controller.py` — `is_finger_open()`, `get_active_fingers()`, and `evaluate_raw_command()`.)

10. **Serial auto-detection can select an unrelated device.** If no recognized USB-serial description is found, the desktop sender falls back to the first enumerated port. It then opens that port and transmits commands. Prefer an explicit port selector or USB VID/PID match, and fail safely rather than silently choosing an arbitrary serial device. (`control_center/serial_sender.py` — `find_esp32_port()`.)

11. **Desktop connection and startup behavior is not fully resilient.** `SerialSender.connect()` waits two seconds after opening the port, and the dashboard constructs/connects the sender before creating the UI. Startup can pause while hardware reboots; read/write failures are logged but do not consistently update the link state or trigger recovery. Move connection work off the UI path and model connected/disconnected/reconnecting states explicitly. (`control_center/serial_sender.py`; `control_center/ui_dashboard.py` — initialization and `reconnect_serial()`.)

12. **Radar measurement may occur before the servo settles.** `updateRadar()` writes the next angle and immediately triggers `pulseIn()`; there is no settle interval or measured servo-position confirmation. This may produce readings that do not correspond to the displayed angle. Characterize the servo/sensor timing and add an appropriate settling/scan schedule. (`firmware/rover_reciever.ino` — `updateRadar()`.)

13. **The rover camera URL has a developer-specific hard-coded default.** The dashboard seeds the rover feed with `http://100.91.87.88:8080`, which may only work in a particular Tailscale/network setup. Keep the configurable dialog, but use an empty/discoverable default and document the expected Android stream URL/port. (`control_center/ui_dashboard.py` — `ROVER_CAM_INDEX`.)

14. **The mesh shader uses `smoothstep()` with reversed edges.** The calls pass `thickness` as the first edge and `thickness * 0.4` as the second, so `edge0 >= edge1`; GLSL specifies this case as undefined. Replace with a mathematically valid edge ordering and compare the rendered grid on target GLES devices. (`mesh_mobile_app/.../MeshRenderer.kt` — fragment shader.)

15. **Display rotation is hard-coded for ARCore geometry.** `TerrainRenderer.onSurfaceChanged()` calls `session.setDisplayGeometry(0, width, height)`. If the device rotates, AR camera/depth coordinates may be misaligned or cropped. Pass the actual display rotation and test portrait/landscape transitions. (`mesh_mobile_app/.../TerrainRenderer.kt` — `onSurfaceChanged()`.)

16. **Depth image resource closure is not protected by `finally`.** `TerrainMesh.updateHeights()` closes the acquired depth image only on the normal path. Unexpected exceptions during coordinate mapping or buffer access can leave an image unreleased and exhaust the ARCore image queue. Use a `try/finally` around all processing after acquisition. (`mesh_mobile_app/.../TerrainMesh.kt` — `updateHeights()`.)

17. **Port input needs validation.** Invalid text silently falls back to port 8081, and numeric values outside the valid TCP port range are passed into the socket constructor. Validate the user input, show a specific error, and only change streaming UI state after the server successfully binds. (`mesh_mobile_app/.../MainActivity.kt` — port confirmation and `toggleStreaming()`.)

18. **Firmware protocol, safety, and diagnostics need an explicit contract.** The ESP-NOW command payload layouts differ between sketches; receiver input is accepted based only on a minimum length and command conversion assumes a terminated string. Define shared command IDs/struct layout, exact packet-size checks, range validation, sequence/timeout behavior, and send-failure handling. Avoid relying on free-form strings for safety-critical movement commands. (`firmware/rover_transmitter.ino`; `firmware/rover_reciever.ino`.)

## Cleanup candidates — confirm intent before removing

These items appear unused or template-derived in the current implementation; retain them if a near-term feature plan depends on them.

- **Jetpack Compose setup:** the production UI is XML/View-based and `MainActivity` does not use Compose. Compose dependencies, the Compose plugin/feature flag, and generated `ui/theme/Color.kt`, `Theme.kt`, and `Type.kt` appear unused. Remove them if Compose is not planned; otherwise add an actual Compose surface and tests.
- **Generated Android starter tests:** `ExampleUnitTest` only asserts `2 + 2`, and `ExampleInstrumentedTest` only checks the package name. They are not meaningful product tests. Replace them with tests for port validation, stream lifecycle, mesh sampling, and UI state, or remove the placeholders.
- **Template Android resources:** the purple/teal palette in `values/colors.xml` appears unused because the current UI uses inline colors; empty backup/data-extraction rules should be customized if user data is added or removed if not needed. Verify resource references before deleting.
- **Checked-in release binaries:** the 14 MB APK and 486 MB Git LFS ZIP may be useful distribution artifacts, but are not source. Prefer release attachments and reproducible build instructions; retain in Git/LFS only if that is the project's intended release policy.
- **No other feature can safely be called unnecessary from code alone.** The radar, rover feed, AR terrain visualization, and keyboard/gesture controls are implemented project capabilities, not cleanup candidates. Product requirements should decide whether any are out of scope.

## Incomplete work / readiness checklist

- Add a useful README: project purpose, supported hardware and pinout/wiring, dependencies, setup/run commands for the desktop app, Android install/build instructions, firmware flashing steps, and end-to-end connection diagram.
- Add a pinned Python dependency manifest (for the current imports: PyQt6, OpenCV, MediaPipe, and pyserial) plus a supported Python/platform matrix and a repeatable desktop packaging process.
- Resolve the firmware command/speed contract and add motor PWM, a communication watchdog, and explicit stop/reconnect behavior before driving tests.
- Add meaningful automated tests for gesture mapping/debounce, telemetry parsing, command encoding, mobile server lifecycle, and depth/mesh behavior where testable without hardware.
- Make `mesh_mobile_app/gradlew` executable in Git; configure Android SDK in developer instructions/CI; build and run unit/instrumented tests on the supported SDK/device matrix.
- Compile both firmware sketches with documented ESP32 board/core/library versions; record receiver/transmitter board identifiers and pin mappings.
- Add hardware-in-the-loop tests for motor direction, PWM speed range, link-loss stop, radar scan timing/accuracy, and telemetry recovery.
- Add explicit camera/network privacy controls and actual feed/connection health reporting.
- Decide whether release binaries belong in Git LFS or GitHub Releases and record artifact version/hash/build provenance.

## Overall assessment

**Status: feature-complete prototype in several paths; not yet validated for a v1.0.0 field release.** The desktop dashboard, ESP-NOW links, radar telemetry, Android depth mesh, and MJPEG transport are represented in source. The review does not establish that all components compile or interoperate on the target hardware. The communication-loss motor behavior and ignored speed value should be addressed before operational rover use; the Android/firmware build gates and real tests should be completed before labeling the system release-ready.
