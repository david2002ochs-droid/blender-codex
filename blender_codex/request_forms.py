"""Bounded flat MCP form validation; unknown schemas never imply consent."""
import math


def supported_form(schema):
    if not isinstance(schema, dict) or schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        return False
    properties = schema["properties"]
    if len(properties) > 32 or any(key not in properties for key in schema.get("required", [])):
        return False
    allowed = {"type", "title", "description", "enum", "enumNames", "default", "minLength", "maxLength",
               "minimum", "maximum", "items", "minItems", "maxItems", "oneOf", "format"}
    for spec in properties.values():
        if not isinstance(spec, dict) or set(spec) - allowed or spec.get("type") not in ("string", "boolean", "integer", "number", "array"):
            return False
        if "oneOf" in spec:  # Do not silently under-validate an alternate schema.
            return False
        if spec.get("type") == "array" and (not isinstance(spec.get("items"), dict)
                or spec["items"].get("type") != "string" or set(spec["items"]) - {"type", "enum"}):
            return False
    return True


def validate_form(schema, values):
    if not supported_form(schema) or not isinstance(values, dict):
        raise ValueError("This request requires a supported flat form and explicit field values.")
    properties = schema["properties"]
    if set(values) - set(properties) or any(key not in values for key in schema.get("required", [])):
        raise ValueError("Form fields are missing or unknown.")
    for key, value in values.items():
        spec = properties[key]
        kind = spec["type"]
        valid = ((kind == "string" and isinstance(value, str) and len(value) <= 8192)
                 or (kind == "boolean" and isinstance(value, bool))
                 or (kind == "integer" and type(value) is int)
                 or (kind == "number" and type(value) in (int, float) and math.isfinite(value))
                 or (kind == "array" and isinstance(value, list) and len(value) <= 64 and
                     all(isinstance(x, str) and len(x) <= 8192 for x in value)))
        if not valid or ("enum" in spec and value not in spec["enum"]):
            raise ValueError("A form field has an invalid value.")
        if isinstance(value, (str, list)):
            for bound, comparison in (("minLength" if kind == "string" else "minItems", lambda a, b: a < b),
                                      ("maxLength" if kind == "string" else "maxItems", lambda a, b: a > b)):
                if bound in spec and comparison(len(value), spec[bound]):
                    raise ValueError("A form field is outside its allowed length.")
        if kind in ("integer", "number"):
            if ("minimum" in spec and value < spec["minimum"]) or ("maximum" in spec and value > spec["maximum"]):
                raise ValueError("A form number is outside its allowed range.")
        if kind == "array" and "enum" in spec["items"] and any(x not in spec["items"]["enum"] for x in value):
            raise ValueError("A form selection is not allowed.")
    return values


def validate_answers(questions, answers):
    if not isinstance(answers, dict) or set(answers) != {q["id"] for q in questions}:
        raise ValueError("Answer each requested question explicitly.")
    result = {}
    for question in questions:
        value = answers[question["id"]]
        if not isinstance(value, list) or not value or len(value) > 16 or not all(isinstance(x, str) and len(x) <= 8192 for x in value):
            raise ValueError("Question answers must be nonempty lists of strings.")
        result[question["id"]] = {"answers": value}
    return result
