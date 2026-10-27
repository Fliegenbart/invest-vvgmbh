"""Claude's JSON-schema subset, with full application validation kept separate."""
from __future__ import annotations

from copy import deepcopy


def claude_json_schema(schema):
    """Move API-unsupported limits into hints; never mutate the original schema."""
    out = deepcopy(schema)
    hints = []
    unsupported = ('minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum',
                   'multipleOf', 'minLength', 'maxLength', 'maxItems', 'uniqueItems')
    for key in unsupported:
        if key in out:
            hints.append(f'{key}={out.pop(key)}')
    if out.get('minItems', 0) not in (0, 1):
        hints.append(f'minItems={out.pop("minItems")}')
    for container in ('properties', '$defs', 'definitions'):
        if container in out:
            out[container] = {name: claude_json_schema(child) for name, child in out[container].items()}
    if isinstance(out.get('items'), dict):
        out['items'] = claude_json_schema(out['items'])
    for union in ('anyOf', 'allOf'):
        if union in out:
            out[union] = [claude_json_schema(child) for child in out[union]]
    if out.get('type') == 'object':
        out.setdefault('additionalProperties', False)
    if hints:
        out['description'] = (out.get('description', '') + ' Application constraints: '
                              + '; '.join(hints) + '.').strip()
    return out


def canonicalize_enum_case(value, schema, root=None):
    """Normalize only unambiguous enum casing; retain unknown values for rejection."""
    root = schema if root is None else root
    if '$ref' in schema and schema['$ref'].startswith('#/'):
        target = root
        for part in schema['$ref'][2:].split('/'):
            target = target[part.replace('~1', '/').replace('~0', '~')]
        return canonicalize_enum_case(value, target, root)
    if isinstance(value, str):
        allowed = schema.get('enum', [schema['const']] if 'const' in schema else [])
        matches = [item for item in allowed if isinstance(item, str) and item.casefold() == value.casefold()]
        return matches[0] if len(matches) == 1 else value
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        return {key: canonicalize_enum_case(item, properties.get(key, {}), root) for key, item in value.items()}
    if isinstance(value, list) and isinstance(schema.get('items'), dict):
        return [canonicalize_enum_case(item, schema['items'], root) for item in value]
    return value
