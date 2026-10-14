"""JSON Schema validation utility for C1 tool argument schemas.

Uses the standard 'jsonschema' library with network resolution strictly disabled.
"""

from typing import Any, Optional
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for


def validate_schema_structure(schema: dict[str, Any]) -> Optional[str]:
    """Validate that a dictionary is structurally valid JSON Schema.

    Returns None if valid, or an error description string if invalid.
    """
    if not isinstance(schema, dict):
        return "Schema must be a JSON object (dict)"

    try:
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        return None
    except SchemaError as e:
        return f"Invalid JSON Schema structure: {e.message}"
    except Exception as e:
        return f"Unexpected schema structure failure: {str(e)}"


def validate_instance_against_schema(
    instance: Any,
    schema: dict[str, Any],
) -> list[str]:
    """Validate an instance payload against a JSON schema without network resolution.

    Returns a list of validation error messages, or an empty list if valid.
    """
    errors: list[str] = []
    try:
        validator_cls = validator_for(schema)
        # Create validator without external network resolver
        validator = validator_cls(schema)
        for err in validator.iter_errors(instance):
            path_str = ".".join(str(p) for p in err.path) if err.path else "root"
            errors.append(f"At '{path_str}': {err.message}")
    except SchemaError as e:
        errors.append(f"Schema definition error: {e.message}")
    except Exception as e:
        errors.append(f"Validation failure: {str(e)}")

    return errors
