# Animated companions

Run `run_petlink.bat`, or set `PYTHONPATH` to `src` and run `python -m petlink`.
Right-click for Coral, Ishu or Lola, expression previews, reduced motion and Exit.
Selection, position and reduced motion are saved through Windows QSettings.

`pet_window.py` owns timing and interaction. `character_art.py` loads cached
transparent layers and renders the face independently. Assets are included in
package data. New character art can be swapped without changing model providers.

Blink, wink, gaze, tilt and ear clocks are independent and randomized. The
`idle_intervals` constructor argument accepts per-channel `(minimum, maximum)`
seconds. A precise Qt timer targets 30 FPS; reduced motion uses 10 FPS and stops
body sway, tilt, bounce, ear rotation and tail rotation. Facial responses remain.

Future app integrations call `react` with chat_opened, typing, microphone_on,
thinking, task_completed, reminder or finished, on Qt's UI thread. Chat now
connects its open/typing/thinking/finished events; microphone and task services
are not implemented yet. `set_speech_level`
accepts a normalized audio envelope for mouth motion. Until audio is connected,
Talking is a synthetic preview, not lip synchronization.

Art limitations: hair/headphones share the head layer; capes/bows share the body.
Independent hair strands, ribbon deformation, tail-tip deformation and a bespoke
stretch pose require additional artwork. Ear, head, body, eye, mouth, arm and
whole-tail movement are currently independent.

## Verification

`python -m unittest discover -s tests -p test_animation.py` checks all 21
character/expression combinations, preference reload, double-click suppression
and reaction/audio hooks. Tests use separate temporary settings.

`python tests/preview_pets.py` creates `pets-preview.png` and measures rendering.
Measured on this Windows host with Qt offscreen CPU rendering after warming
all character caches: mean 0.44 ms/frame, p95 0.59 ms, timer mean 32.96 ms
(about 30 FPS), working set 59 MB, approximately 4.7% of one CPU core during
a three-second sample (a repeat measured about 11% of one core, so CPU load
varies). These are short local measurements, not an 8 GB laptop
benchmark or a guarantee for Windows desktop composition.
