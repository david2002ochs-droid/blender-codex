# Optional Hi3D image-to-3D workflow

Hi3D is a separate cloud provider. The normal Codex/Blender chat works without its credentials. Generation uploads selected reference images and may consume paid credits under your provider account.

## Credentials

Copy `.env.example` to a local `.env` and fill in your Access Key and Secret Key:

```dotenv
HI3D_CLIENT_ID=""
HI3D_CLIENT_SECRET=""
```

The provider panel also accepts session-only values or an explicit credentials-file path. Complete pairs are read from provider settings, the environment, a selected `.env`, the Blender project directory or the checkout, in that order. Values from different sources are not combined. Reconnect after changing provider configuration.

`.env` files are ignored by Git and excluded from the add-on package. Keep real keys out of issues and screenshots. A Codex login does not replace a Hi3D account.

## Generate or resume

Open **3D Providers** to test access/balance, select references, inspect the cost estimate, explicitly start generation, follow status and import the downloaded GLB.

The chat's `image_to_3d` tool accepts either one `image_path`, or 2–4 named `views` (`front`, `back`, `left`, `right`) with a required front view. It also accepts `quality` and an existing `task_id`. Use a fresh chat after tool-schema changes.

Resume status polling with the existing task ID. Local Stop does not cancel a job already submitted to Hi3D. If submission loses its connection, inspect the provider console before starting another paid job.

Downloaded GLB files receive basic format/length checks and a hash. Inspect actual mesh quality, scale, topology and rigging after import. A successful download alone does not confirm a Blender import.

## References

- [Hi3D platform](https://platform.hi3d.ai)
- [Authentication API](https://docs.hi3d.ai/en/api/api-reference/list/get-token)
- [Provider pricing](https://docs.hi3d.ai/en/api/getting-started/pricing)
- [Reference-image workflow](asset-reference-workflow.md)

Automated provider tests use simulated responses. They do not establish a successful paid cloud generation.
