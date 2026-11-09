"""Native markup lifecycle with an owned annotation copy and scoped Escape."""
from contextlib import nullcontext
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("markup_under_test", Path(__file__).resolve().parents[1] / "blender_codex/markup.py")
markup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markup)


class MarkupImportTests(unittest.TestCase):
    def test_packaged_lazy_import_without_loading_addon_entrypoint(self):
        folder = Path(__file__).resolve().parents[1] / "blender_codex"
        package = ModuleType("markup_package_fixture")
        package.__path__ = [str(folder)]
        name = package.__name__ + ".annotations"
        module_spec = importlib.util.spec_from_file_location(name, folder / "annotations.py")
        module = importlib.util.module_from_spec(module_spec)
        with patch.dict(sys.modules, {package.__name__: package, name: module}):
            module_spec.loader.exec_module(module)
            controller = module._markup()
            self.assertEqual(controller.__name__, package.__name__ + ".markup")
            self.assertFalse(controller.is_drawing(NS()))

    def test_standalone_lazy_import_without_bpy(self):
        folder = Path(__file__).resolve().parents[1] / "blender_codex"
        module_spec = importlib.util.spec_from_file_location("annotations_import_fixture", folder / "annotations.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        with patch.dict(sys.modules):
            sys.modules.pop("_blender_codex_markup", None)
            controller = module._markup()
            self.assertEqual(controller.__name__, "_blender_codex_markup")
            self.assertFalse(controller.is_drawing(NS()))


class Layers(list):
    def new(self, name, set_active=True):
        layer = NS(info=name, lock=False, strokes=[])
        self.append(layer)
        if set_active:
            self.active = layer
        return layer


class Data:
    def __init__(self, name, collection):
        self.name, self.collection, self.users = name, collection, 0
        self.layers = Layers()

    def copy(self):
        result = self.collection.new(self.name + " copy")
        result.layers = copy.deepcopy(self.layers)
        return result


class Collection(list):
    def new(self, name):
        data = Data(name, self)
        self.append(data)
        return data

    def remove(self, data):
        assert data.users == 0, "Never remove user-linked annotation data"
        super().remove(data)


class Scene:
    def __init__(self):
        self._annotation = None

    @property
    def annotation(self):
        return self._annotation

    @annotation.setter
    def annotation(self, value):
        if self._annotation is not None:
            self._annotation.users -= 1
        self._annotation = value
        if value is not None:
            value.users += 1


class MarkupTests(unittest.TestCase):
    def setUp(self):
        markup._draw = None
        markup._operator_class = None
        self.collection = Collection()
        self.scene = Scene()
        self.original = self.collection.new("User notes")
        self.user_layer = self.original.layers.new("User layer")
        self.user_layer.strokes = [[(1, 2, 3), (4, 5, 6)]]
        self.scene.annotation = self.original
        self.region = NS(type="WINDOW")
        self.area = NS(type="VIEW_3D", tag_redraw=Mock())
        self.window = NS(screen=NS(areas=[self.area]), workspace=NS(tools=NS(
            from_space_view3d_mode=Mock(return_value=NS(idname="builtin.move")))))
        self.timers = []
        self.handlers = []
        self.manager = NS(event_timer_add=lambda _seconds, **_kw: self.add_timer(),
                          event_timer_remove=lambda timer: self.timers.remove(timer),
                          modal_handler_add=self.handlers.append)
        self.context = NS(scene=self.scene, window=self.window, area=self.area, mode="OBJECT",
                          window_manager=self.manager, temp_override=lambda **_kwargs: nullcontext())
        self.tool = Mock(return_value={"FINISHED"})

        def guard(_invoke, session_token):
            operator = markup._operator_class()
            operator.session_token = session_token
            return operator.invoke(self.context, None)

        self.bpy = NS(data=NS(annotations=self.collection), types=NS(Operator=object),
                      props=NS(StringProperty=lambda **_kw: None),
                      utils=NS(register_class=Mock(), unregister_class=Mock()),
                      ops=NS(wm=NS(tool_set_by_id=self.tool), codex_markup=NS(escape_guard=guard)))
        self.patch = patch.dict(sys.modules, {"bpy": self.bpy})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(markup.unregister)

    def add_timer(self):
        timer = object()
        self.timers.append(timer)
        return timer

    def activate(self):
        markup.activate(self.context, self.bpy, self.window, self.area, self.region)

    def test_cancel_discards_only_owned_copy_and_restores_tool(self):
        self.activate()
        temporary = self.scene.annotation
        self.assertIsNot(temporary, self.original)
        temporary.layers.active.strokes.append([(9, 9, 9)])
        self.assertTrue(temporary.layers[0].lock)
        self.assertFalse(self.user_layer.lock)
        self.assertTrue(markup.is_drawing(self.context))
        self.assertTrue(markup.cancel_draw(self.context))
        self.assertIs(self.scene.annotation, self.original)
        self.assertEqual(self.user_layer.strokes, [[(1, 2, 3), (4, 5, 6)]])
        self.assertNotIn(temporary, self.collection)
        self.assertEqual([call.kwargs["name"] for call in self.tool.call_args_list], ["builtin.annotate", "builtin.move"])
        self.assertFalse(self.timers)
        self.assertFalse(markup.is_drawing(self.context))
        self.assertFalse(markup.cancel_draw(self.context))

    def test_viewport_escape_and_unrelated_events(self):
        self.activate()
        operator = self.handlers[-1]
        self.assertEqual(operator.modal(self.context, NS(type="LEFTMOUSE", value="PRESS")), {"PASS_THROUGH"})
        self.assertEqual(operator.modal(self.context, NS(type="ESC", value="RELEASE")), {"PASS_THROUGH"})
        other = NS(window=self.window, area=NS(type="NODE_EDITOR"))
        self.assertEqual(operator.modal(other, NS(type="ESC", value="PRESS")), {"PASS_THROUGH"})
        self.assertTrue(markup.is_drawing(self.context))
        self.assertEqual(operator.modal(self.context, NS(type="ESC", value="PRESS")), {"FINISHED"})
        self.assertIs(self.scene.annotation, self.original)

    def test_repeated_draw_is_same_operation(self):
        self.activate()
        session = markup._draw
        self.activate()
        self.assertIs(markup._draw, session)
        self.assertEqual(len(self.handlers), 1)
        self.assertEqual(len(self.collection), 2)

    def test_no_existing_annotations_restore_none(self):
        self.scene.annotation = None
        self.activate()
        temporary = self.scene.annotation
        markup.cancel_draw(self.context)
        self.assertIsNone(self.scene.annotation)
        self.assertNotIn(temporary, self.collection)
        self.assertIn(self.original, self.collection)

    def test_activation_failure_rolls_back_owned_data(self):
        self.tool.side_effect = [{"CANCELLED"}, {"FINISHED"}]
        with self.assertRaisesRegex(RuntimeError, "native Annotate"):
            self.activate()
        self.assertIs(self.scene.annotation, self.original)
        self.assertEqual(len(self.collection), 1)
        self.assertIsNone(markup._draw)

    def test_does_not_unlink_data_user_shared_elsewhere(self):
        self.activate()
        shared = Scene()
        shared.annotation = self.scene.annotation
        temporary = shared.annotation
        markup.cancel_draw(self.context)
        self.assertIs(self.scene.annotation, self.original)
        self.assertIs(shared.annotation, temporary)
        self.assertIn(temporary, self.collection)

    def test_area_disappearance_cleans_up_on_modal_event(self):
        self.activate()
        operator = self.handlers[-1]
        self.window.screen.areas.clear()
        self.assertEqual(operator.modal(self.context, NS(type="TIMER", value="NOTHING")), {"FINISHED"})
        self.assertIs(self.scene.annotation, self.original)


if __name__ == "__main__":
    unittest.main()
