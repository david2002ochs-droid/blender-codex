import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("forms_under_test", Path(__file__).resolve().parents[1] / "blender_codex/request_forms.py")
forms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(forms)


class FormTests(unittest.TestCase):
    def test_flat_form_types_required_enums_bounds_and_no_defaults_invented(self):
        schema = {"type": "object", "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 8, "default": "not-consent"},
            "count": {"type": "integer", "minimum": 1, "maximum": 3}, "enabled": {"type": "boolean"},
            "choices": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}}, "required": ["name", "count"]}
        values = {"name": "Cube", "count": 2, "enabled": False, "choices": ["a"]}
        self.assertEqual(forms.validate_form(schema, values), values)
        for invalid in ({}, {"name": "", "count": 2}, {"name": "Cube", "count": True},
                        {"name": "Cube", "count": 5}, {"name": "Cube", "count": 2, "choices": ["invented"]}):
            with self.assertRaises(ValueError):
                forms.validate_form(schema, invalid)

    def test_unknown_or_nested_schemas_are_not_claimed_as_supported(self):
        for schema in ({}, {"type": "object", "properties": {"x": {"type": "object"}}},
                       {"type": "object", "properties": {"x": {"type": "string", "pattern": ".*"}}}):
            self.assertFalse(forms.supported_form(schema))

    def test_user_questions_keep_exact_question_ids_and_require_explicit_answers(self):
        questions = [{"id": "question-real", "question": "Choose"}]
        self.assertEqual(forms.validate_answers(questions, {"question-real": ["Blue"]}),
                         {"question-real": {"answers": ["Blue"]}})
        for invalid in ({}, {"other": ["Blue"]}, {"question-real": []}, {"question-real": "Blue"}):
            with self.assertRaises(ValueError):
                forms.validate_answers(questions, invalid)


if __name__ == "__main__":
    unittest.main()
