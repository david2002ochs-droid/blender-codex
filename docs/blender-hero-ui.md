# Blender welcome screen

`frontend/src/blender-hero.tsx` supplies the Blender-specific new-chat artwork: a perspective floor, axes and an orange wireframe cube. The illustration uses SVG/CSS; it has no raster dependency or interactive scene controls.

The footer reports connection status. Connection settings can be saved while idle and are disabled during an active response. The backend owns automatic connection recovery; the native host owns window movement and resizing.

`tests/test_blender_hero.cjs` loads the compiled interface at widths of 240, 430 and 684 pixels. It checks layout, overflow and busy/idle settings with explicit backend fixtures. It does not start Blender or prove a live model turn.
