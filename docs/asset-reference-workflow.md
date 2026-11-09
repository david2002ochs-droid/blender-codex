# Asset reference workflow

Research checked 7 November 2026. These are proposed operating defaults and original image-prompt templates, not a benchmarked guarantee of model quality.

The system instructions in `blender_codex/instructions.txt` distinguish the image-generation prompt from the workflow that selects, checks and submits references. The current implementation exposes one dynamic function tool named `image_to_3d`, backed by Hi3D. Its arguments are `image_path`, `views`, `quality` and `task_id`. It accepts the old `hi3d_image_to_3d` name only for dispatch compatibility with existing chats; the public registry exposes one name. Availability in a running installation must be checked against that chat's actual schema.

## View selection

| Asset | Suggested reference set when the tool supports it |
| --- | --- |
| Simple object with little important hidden detail | One complete front or mild three-quarter view |
| Object with important rear construction | Front, side, back |
| Asymmetric object | Front, back, left, right |
| Humanoid for animation | Full-body front, side, back, same A-pose or rig-required T-pose; fourth view for asymmetry |
| Static figurine or creature | Preserve intended pose/anatomy; choose views exposing its structure |

Two complementary views can be useful under a tighter budget, but do not specify the entire surface. Generated additional views infer the hidden geometry; they do not recover ground truth from a single original. Verify their design consistency before using them together.

Hi3D documents 2–4 multi-view images, with the front required. Its API uses separate `multi_images` files in front/back/left/right order and a four-bit `multi_images_bit` mask for partial sets. A three-view front/back/left set therefore corresponds to `1110`. The adapter handles that provider payload; these fields are not public agent-tool arguments. For a new job, call `image_to_3d` with either one absolute local `image_path`, or `views` containing 2–4 objects with unique `view` values (`front`, `back`, `left`, `right`) and absolute local `image_path` values. Front is required. The wrapper accepts views in any input order and normalizes provider ordering. A collage uploaded through the single-image field does not constitute multi-view input.

Resume with the existing `task_id` rather than submit the images again; image inputs are ignored for a resume. An older resumed Codex chat can retain its old tool schema: the client registers dynamic tool specifications on `thread/start`, not `thread/resume`. Use a fresh plugin chat for the new schema, and do not claim the running test candidate has been upgraded merely because source files changed. Multi-view generation has not been validated by spending on a live provider job in this change.

## Character image prompt

Fill the bracketed design details. This template creates a single canonical front reference. A-pose is an operating choice for an animation asset, not appropriate for every character request.

> Create a clean reconstruction reference of one [character description], [style], wearing [specific clothing and materials], with [distinctive features and which anatomical side carries each]. Full body, true front view, neutral A-pose, arms separated from the torso, legs slightly apart, empty relaxed hands, unobstructed face, complete head and feet. Use a shaded orthographic presentation, plain background and soft even lighting. Center the character with clear padding. Show only this character, without a scene, stand, text or view labels. Preserve the specified anatomy and costume.

For later views, attach the canonical image to an actual image-editing/reference-conditioned tool and use:

> Show this exact character in [true left side / rear / true right side] view. Keep the same body shape, facial identity, costume construction, materials, physical left/right details, rest pose, image scale and lighting. Rotate the viewpoint around the unchanged character. Do not mirror, redesign, add accessories or crop the body. Return one clean view on the same plain background, with no labels.

## Object image prompt

> Create a reconstruction reference of one [object], [style], made of [materials and finish], with [explicit dimensions/proportions, part count and identifying construction details]. Show the entire object in [front / mild three-quarter] view with its main form and depth clearly readable. Center it on a plain background with padding, soft diffuse lighting and sharp surface detail. Include only the requested asset. Keep its openings and component boundaries visible; omit unrelated props, display stands, text and watermarks. Preserve the requested material appearance.

Derive side/back references from the same canonical image rather than repeating the text prompt independently:

> Show the exact same object from [true side / rear], keeping its construction, dimensions, component count, materials and markings unchanged. Keep the same object scale and diffuse lighting. Use a shaded orthographic view on the same plain background. Return a single uncropped object, without labels. Reveal the rear/side construction consistently with the canonical design.

These prompts guide rendered appearance. Rigging, topology, dimensions in Blender and printability remain separate checks on the actual generated mesh. Detail close-ups may guide review, but must not replace the full-body/object image or be mislabeled as a provider's front/back/side input.

## Sources and limits

- [Hi3D FAQ](https://docs.hi3d.ai/en/api/getting-started/faq): single-view versus 2–4-image multi-view input, required front view.
- [Hi3D Create Task](https://docs.hi3d.ai/en/api/api-reference/list/create-task): mutually exclusive single/multi input, explicit slot order and bit mask.
- [Meshy Multi-View Best Practices](https://help.meshy.ai/en/articles/16102789-meshy-multi-view-best-practices-angles-and-images): consistent subjects and views; more images do not always improve results.
- [Meshy Multi-View Help](https://help.meshy.ai/en/articles/12634481-how-to-use-multi-view): matching framing and splitting reference sheets into separate views.
- [Meshy Character Pose Guide](https://help.meshy.ai/en/articles/16102152-fix-character-pose-face-and-hand-issues-in-meshy): complete visible characters, rest poses and limitations of hands, faces and rigs. Meshy pose controls are not a capability of our current Hi3D wrapper.
- [Meshy 3D-ready Image Guide](https://docs.meshy.ai/en/webapp/guides/image/ai-image-generation): whole-subject front/three-quarter image, simple background, reference-based generation.
- [Meshy Prompt Templates](https://help.meshy.ai/en/articles/16103167-meshy-prompt-templates-for-3d-assets): subject/material/style/structure. These templates primarily concern text-to-3D; they are not drop-in image-generation system instructions.
