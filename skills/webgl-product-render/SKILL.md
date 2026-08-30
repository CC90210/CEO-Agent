---
name: webgl-product-render
description: Build and debug photoreal procedural 3D product visualisers in three.js — environment lighting, PBR materials, camera choreography, and the specific defects that survive code review but ruin the render. Use when a 3D model reads as rudimentary or cheap, when camera focus lands on the wrong part, or when geometry floats, clips, or renders invisibly inside other geometry.
tier: tool
owner: bravo
risk: low
triggers: ["3d model looks rudimentary", "car looks cheap", "three.js", "threejs", "webgl scene", "product visualiser", "3d hero", "camera focus wrong", "camera framing 3d", "orbit controls", "hotspot camera", "geometry clipping", "parts floating", "photoreal render", "env map", "pbr materials", "make the 3d look real"]
tags: [tool, 3d, threejs, webgl, render, frontend, camera]
status: '[NEW]'
created_at: 2026-08-01
last_updated: 2026-08-01
---

# WebGL product render

Hard-won on the OASIS car stage. Every rule here is a defect that shipped,
was invisible in the diff, and was found by looking at a frame.

## The order that actually matters

Realism is not won with geometry. In descending order of impact:

1. **Environment map.** A metal or clearcoat surface is almost entirely
   reflection. With no `scene.environment` a dark object has nothing to
   reflect and contains no information — no amount of geometry fixes it.
   Build one procedurally: `PMREMGenerator.fromScene()` over a dark room
   with a few emissive panels. Zero assets.
   - Emissive panels need `toneMapped: false` and colours pushed above 1.0
     via `color.multiplyScalar(n)`, or the bake compresses your lights to
     grey cards before they reach the cube map.
   - Keep the PMREM sigma low (~0.04). Higher smears distinct sources into
     one wash, which is the usual reason people conclude "env maps don't help".
2. **Tone mapping.** Without it everything above 1.0 hard-clips: black
   shapes with blown highlights and no roll-off. `AgXToneMapping` holds
   saturated hue into the highlight; `ACESFilmic` desaturates toward white,
   which will wash out a brand colour exactly where it is brightest.
3. **The lens.** A wide FOV at close range is the signature of a screenshot
   taken inside a 3D editor. Products are shot on a long lens from far
   back. Changing FOV requires scaling every camera distance by
   `tan(oldFov/2) / tan(newFov/2)` or you silently reframe everything.
4. **Smooth shading.** Non-indexed geometry cannot be smooth-shaded:
   `computeVertexNormals()` writes one face normal to all three vertices
   because they are shared with nothing. Emit an index buffer. This is
   invisible in code and looks like "a low-detail model".
5. **Geometry.** Last, not first.

## Ambient and hemisphere lights contribute ZERO specular

They feed only the indirect diffuse term. On a metallic surface they cannot
produce a highlight — they raise the floor and flatten the panel you were
trying to shape. Once an env map exists, delete them and cut directional
intensities hard; the env map is the fill.

A `DirectionalLight` is a point at infinity: it can only ever make a round
hotspot. The long soft streak down a flank comes from a long narrow emitter
in the ENVIRONMENT. Put the intensity where the shape is.

## Mount anything on the SOLVED surface, never the bounding box

The defect that recurred most. A section's stored half-width is its widest
point, reached only at its vertical centre. Anything placed against it —
trim, lights, rails, badges — ends up inside the body above and below that
line, z-fighting (a strobing dashed line that changes every frame) or
floating off it.

- Export a function that answers "where is the surface at height y?" and
  make every consumer call it. Several call sites each hand-rolling a
  geometric guess means the bug is the ABSENT FUNCTION, not the guesses.
- Offset along the true surface NORMAL, not straight out on one axis — a
  pure-axis offset re-buries a part as soon as the surface starts to roll.
- The offset a part needs is its OWN half-thickness plus clearance.
- Anything that RUNS ALONG a curved body must be swept as a tube through
  per-station surface points. A straight box meets the surface at one point
  and lifts off it everywhere else.

## Presence is not visibility

Geometry inside other geometry still renders, still costs its draw call,
and is never seen. On this project it caught a rear light bar, an engine
core, neon strips, and a turbo — four times, same error.

Before shipping any part, ask where the enclosing surface is at that
coordinate. If the part is below the deck / inside the shell, it does not
exist as far as the viewer is concerned.

## Rotation: orient the parent, spin the child

A mesh that has been Euler-rotated to point the right way cannot then be
spun on a single axis — the added rotation composes with the orientation
and tumbles it end over end. Whether it happens to look right depends on
Euler order, which is not something to leave to luck.

    const holder = new THREE.Group();
    holder.rotation.set(...orient);   // parent orients
    holder.add(mesh);                 // child spins on its own axis
    // torus is built around z, cylinder around y — state which at the call site

Blades that must ORBIT a hub go in a group that spins. Spinning each blade
individually rotates it in place like a propeller pinned to a wall.

## Camera choreography

- **Per-subject approach direction, not one shared vector.** Measure what is
  near the subject first: on this car the engine bay sat 0.20 units from an
  axle and a wheel is 0.90 across, so any side-on approach framed a tyre.
  An engine bay is photographed from ABOVE for that exact reason.
- **Per-subject frame height.** A detail shot and a whole-product claim
  cannot share a distance. Derive distance from the framing you want:
  `dist = frameHeight / (2·tan(fov/2))`.
- **Clamp the camera above the geometry it can fall into.**
- **If two code paths reach the same subject, fix both.** A picker and a
  hotspot both flying to the engine is two vectors to maintain; one will be
  forgotten.
- **Frame counters, not timers, for sequences.** `setTimeout` keeps running
  while a tab is backgrounded but the render loop does not, so the subject
  ends up somewhere the camera is not.
- Honour `prefers-reduced-motion` in EVERY animation including the cinematic
  ones — those are the ones the preference exists for.

## Do not

- **Emissive for anything that should read as material.** Emissive ignores
  lighting, renders at full brightness, and clips to flat white under tone
  mapping. Wheels built from ~100 emissive blades became the brightest
  object in frame. Dark machined metal with high `envMapIntensity` looks
  *more* real because it reflects.
- **Sub-pixel detail.** 100+ blades at 0.02 units are invisible at hero
  distance and contribute only aliasing shimmer. Shimmer reads as cheap.
- **Wireframe overlays.** A triangle mesh over a surface is what 3D software
  looks like mid-edit.
- **Idle sway.** Rotating the subject forever turns every flaw toward the
  viewer in turn. Sweep a LIGHT instead: reads as alive, and hides geometry
  rather than parading it.
- **setState in the render loop.** Publishing per-frame data to React
  re-renders the tree at 60fps. Publish only on meaningful change.

## Verify by looking, and break your own checks

Every defect above survived code review. None survived a screenshot.

- Put your render next to the reference at the same angle, repeatedly,
  before showing anyone. Iterating against a person is a multi-day loop;
  iterating against a screenshot is ten minutes.
- Assert placement NUMERICALLY, and make the assertion **signed** — an
  unsigned distance-to-surface cannot tell a part 2cm proud from one 2cm
  buried, which is the only thing you needed to know.
- Never derive the expected value from the thing under test. `2·d·tan(f/2)
  === 2·d·tan(f/2)` is true at every value and catches nothing.
- **Break the code on purpose and watch the check fail** before reporting it
  as proof. If it still passes, the check is decorative.
- Verify against the artifact that SHIPS — the resampled render surface, not
  the authored control points.

## Where a browser-automation round trip is slower than the animation

Screenshots land after the sequence has finished. Drive the page from a
single script (`browser_run_code_unsafe`) and take every capture inside that
one call, with no round trip to outrun. Screenshot the CANVAS rather than
the page, so an empty frame proves the subject left rather than an overlay
having covered it.

Related: [[skills/frontend-design/SKILL]]
