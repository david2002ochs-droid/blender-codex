# Built Deepblick UI

index.html/app.js/styles.css are generated from frontend/src and unchanged
production views pinned in frontend/vendor/deepblick/SOURCE.json. Rebuild with
scripts/build-chat-ui.ps1; do not hand-edit generated assets. Source/license and
build details are in frontend/README.md and frontend/BUILD.json.

Launch #token=... for chat; #token=...&surface=image-editor for contextual images.
The permanent upper toolbar has been removed; legacy surface=markup renders empty.
Each document clears the fragment, keeps its token only in memory, and sends
X-Codex-Token on state/action/resource requests. Both share one backend session.
No cookie/storage authentication, Harness RPC redirection or second agent loop.

GET /api/state is polled while visible. POST /api/action uses the backend's real
send/stop/approval/form/model/policy/upload actions. The adapter supplies native
Deepblick view props/keyed stores. Model/policy controls require actual backend
capabilities/catalogs. Message and tool keys come from actual backend identities.
The original ConversationContent/Hero/Composer/attachment flow is used. Header
opens history on demand; collapsed history reserves zero rail width. Plus Zeichnen
uses draw/markup_cancel and explicit include_view at normal chat Send.

Image annotation requires can_annotate_images plus state.image_markup and real
image_markup/open,close,commit actions. Original image pixels stay immutable;
numbered comments and marked PNG are admitted to current chat draft on commit,
never automatically sent. These capabilities must not be advertised before the
backend implements nonce/thread validation and resource admission.

Resources use registered IDs and authenticated same-origin GET URLs. Images/text
are fetched before rendering; unsupported formats offer the original download
without claiming conversion. Credentials never appear in normal chat. Technical
paths are confined to Settings; Hi3D is a separate optional provider area.

CSP: local scripts only; local styles plus component inline styles; font-src self
data:; img-src self blob: data:. No eval, CDN, remote script or raw message HTML.
Distributed MIT/third-party notices must accompany the built assets.

There is no product demo mode. Browser fixtures exist only in the test server in
tests/test_deepblick_frontend.cjs. Native downloads and live scene changes need
Blender-host verification beyond that browser contract smoke.
