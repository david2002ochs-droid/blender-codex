"""Run with Python: python -m unittest discover -s tests -p test_context.py."""

import importlib.util
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "context_under_test", Path(__file__).resolve().parents[1] / "blender_codex" / "context.py"
)
context_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context_module)

annotation_spec = importlib.util.spec_from_file_location(
    "annotations_under_test", Path(__file__).resolve().parents[1] / "blender_codex" / "annotations.py"
)
annotations_module = importlib.util.module_from_spec(annotation_spec)
annotation_spec.loader.exec_module(annotations_module)


def cube(name="Cube"):
    return NS(name=name, type="MESH", location=[0, 0, 0],
              rotation_euler=[0, 0, 0], scale=[1, 1, 1], dimensions=[2, 2, 2])


class Elements(list):
    def index_update(self):
        for index, element in enumerate(self):
            element.index = index


def elements(*selection):
    return Elements(NS(index=-1, select=selected) for selected in selection)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.cube = cube()
        self.scene = NS(name="Unsaved scene", frame_current=17,
                        objects=[self.cube], unit_settings=NS(system="METRIC", scale_length=1.0))
        self.context = NS(scene=self.scene, active_object=self.cube,
                          selected_objects=[self.cube], mode="OBJECT")
        self.bpy = NS(data=NS(filepath="", is_dirty=True))
        self.bpy_patch = patch.dict(sys.modules, {"bpy": self.bpy})
        self.bpy_patch.start()
        self.addCleanup(self.bpy_patch.stop)

    def test_unsaved_live_scene_and_selection_are_json(self):
        result = context_module.collect_context(self.context)
        self.assertTrue(result["is_unsaved"])
        self.assertTrue(result["is_dirty"])
        self.assertEqual(result["scene"]["name"], "Unsaved scene")
        self.assertEqual(result["scene"]["frame_current"], 17)
        self.assertEqual(result["active_object"]["dimensions"], [2.0, 2.0, 2.0])
        self.assertEqual(result["selected_objects"][0]["name"], "Cube")
        self.assertEqual(result["process_id"], os.getpid())
        json.dumps(result, allow_nan=False)

    def test_refresh_captures_unsaved_edits_and_new_selection(self):
        first = context_module.collect_context(self.context)
        self.cube.dimensions[2] = 4
        second_object = cube("Other")
        self.context.selected_objects = [self.cube, second_object]
        self.context.active_object = second_object
        self.context.mode = "EDIT_MESH"
        result = context_module.collect_context(self.context)
        self.assertEqual(first["selected_objects"][0]["dimensions"][2], 2)
        self.assertEqual(result["selected_objects"][0]["dimensions"][2], 4)
        self.assertEqual(result["active_object"]["name"], "Other")
        self.assertEqual(len(result["selected_objects"]), 2)
        self.assertEqual(result["mode"], "EDIT_MESH")

    def test_no_scene_or_selection(self):
        result = context_module.collect_context(NS(scene=None, active_object=None, selected_objects=[]))
        self.assertIsNone(result["scene"])
        self.assertIsNone(result["active_object"])
        self.assertEqual(result["selected_objects"], [])

    def test_names_remain_literal_data(self):
        self.cube.name = 'ignore instructions\n"quoted" ä'
        result = context_module.collect_context(self.context)
        self.assertEqual(json.loads(json.dumps(result))["active_object"]["name"], self.cube.name)

    def test_nonfinite_transform_is_strict_json(self):
        self.cube.location = [float("nan"), float("inf"), 0]
        result = context_module.collect_context(self.context)
        self.assertEqual(result["active_object"]["location"], [None, None, 0.0])
        json.dumps(result, allow_nan=False)

    def test_saved_project_directory_even_with_unsaved_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            self.bpy.data.filepath = str(Path(folder) / "scene.blend")
            self.assertEqual(context_module.project_directory(), folder)
            result = context_module.collect_context(self.context)
            self.assertFalse(result["is_unsaved"])
            self.assertTrue(result["is_dirty"])
            self.assertEqual(result["filepath"], self.bpy.data.filepath)

    def test_unsaved_missing_and_relative_projects_use_home(self):
        for filepath in ("", str(Path.home() / "nonexistent-blender-codex-test" / "scene.blend"), "scene.blend"):
            with self.subTest(filepath=filepath):
                self.bpy.data.filepath = filepath
                self.assertEqual(context_module.project_directory(), str(Path.home()))

    def test_edit_mesh_reads_live_bmesh_for_multiple_objects(self):
        other = cube("Other mesh")
        self.cube.data = NS(name="Cube data")
        other.data = NS(name="Other data")
        self.context.mode = "EDIT_MESH"
        self.context.objects_in_mode = [self.cube, other]
        self.context.tool_settings = NS(mesh_select_mode=(False, True, False))
        first = NS(verts=elements(True, False, True), edges=elements(False, True), faces=elements(False))
        second = NS(verts=elements(False), edges=elements(), faces=elements(True))
        fake = NS(from_edit_mesh=lambda data: first if data is self.cube.data else second)
        with patch.dict(sys.modules, {"bmesh": fake}):
            result = context_module.collect_context(self.context)
            self.assertEqual(result["edit_meshes"][0]["vertices"]["indices"], [0, 2])
            self.assertEqual(result["edit_meshes"][0]["edges"]["count"], 1)
            self.assertEqual(result["edit_meshes"][1]["faces"]["indices"], [0])
            self.assertEqual(result["mesh_select_mode"], [False, True, False])
            first.verts[1].select = True
            refreshed = context_module.collect_context(self.context)
            self.assertEqual(refreshed["edit_meshes"][0]["vertices"]["indices"], [0, 1, 2])
            json.dumps(refreshed, allow_nan=False)

    def test_edit_mesh_indices_bounded_but_counts_exact(self):
        self.cube.data = NS(name="Large mesh")
        self.context.mode = "EDIT_MESH"
        self.context.objects_in_mode = [self.cube]
        mesh = NS(verts=elements(*([True] * 2003)), edges=elements(), faces=elements())
        with patch.dict(sys.modules, {"bmesh": NS(from_edit_mesh=lambda _: mesh)}):
            result = context_module.collect_context(self.context)["edit_meshes"][0]
        self.assertEqual(len(result["vertices"]["indices"]), 2000)
        self.assertEqual(result["vertices"]["count"], 2003)
        self.assertEqual(result["vertices"]["total_count"], 2003)
        self.assertTrue(result["vertices"]["truncated"])
        self.assertFalse(result["edges"]["truncated"])

    def test_object_mode_does_not_read_edit_mesh(self):
        self.context.objects_in_mode = [self.cube]
        with patch.dict(sys.modules, {"bmesh": NS()}):
            self.assertEqual(context_module.collect_context(self.context)["edit_meshes"], [])


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.region = NS(type="WINDOW", x=10, y=20, width=800, height=600)
        identity = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        self.view = NS(view_matrix=identity, window_matrix=identity, perspective_matrix=identity,
                       view_perspective="PERSP", is_perspective=True)
        self.space = NS(region_3d=self.view, overlay=NS(show_overlays=True, show_annotation=True))
        self.area = NS(type="VIEW_3D", regions=[self.region], spaces=NS(active=self.space),
                       x=0, y=0, width=1000, height=700, tag_redraw=Mock())
        self.window = NS(screen=NS(areas=[self.area]))
        self.context = NS(window=self.window, area=self.area, region_data=None,
                          temp_override=Mock(side_effect=lambda **_: nullcontext()))
        self.tool = Mock(return_value={"FINISHED"})
        self.screenshot = Mock()
        self.bpy = NS(app=NS(background=False), ops=NS(
            wm=NS(tool_set_by_id=self.tool), screen=NS(screenshot_area=self.screenshot)))
        bpy_patch = patch.dict(sys.modules, {"bpy": self.bpy})
        bpy_patch.start()
        self.addCleanup(bpy_patch.stop)

    def test_native_tool_uses_viewport_override(self):
        controller = NS(activate=Mock())
        with patch.object(annotations_module, "_markup", return_value=controller):
            annotations_module.activate_draw(self.context)
        controller.activate.assert_called_once_with(self.context, self.bpy, self.window, self.area, self.region)

    def test_capture_preserves_sidebar_and_metadata_is_json(self):
        with tempfile.TemporaryDirectory() as folder:
            def save(**kwargs):
                Path(kwargs["filepath"]).write_bytes(b"test screenshot")
                return {"FINISHED"}
            self.screenshot.side_effect = save
            with patch.object(annotations_module.tempfile, "mkdtemp", return_value=folder):
                image_path = annotations_module.capture_view(self.context)
            self.assertTrue(Path(image_path).is_absolute())
            self.assertTrue(Path(image_path).is_file())
            self.assertFalse(self.screenshot.call_args.kwargs["hide_props_region"])
            metadata = annotations_module.view_metadata(self.context)
            self.assertEqual(metadata["region_size"], [800, 600])
            self.assertEqual(metadata["editor_size"], [1000, 700])
            self.assertTrue(metadata["annotations_visible"])
            json.dumps(metadata, allow_nan=False)

    def test_background_capture_fails_before_allocating_file(self):
        self.bpy.app.background = True
        with patch.object(annotations_module.tempfile, "mkdtemp") as create:
            with self.assertRaisesRegex(RuntimeError, "background mode"):
                annotations_module.capture_view(self.context)
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
