import os
import re
from typing import Dict, Tuple

from loguru import logger


def parse_model_file(
    file_path: str, expected_class_name: str
) -> Tuple[str, str, Dict[str, Tuple[str, bool]]]:
    with open(file_path, "r") as f:
        content = f.read()

    lines = content.split("\n")

    class_start = None
    for i, line in enumerate(lines):
        if re.match(rf"class {expected_class_name}\(BaseModel_\):", line):
            class_start = i
            break

    if class_start is None:
        return None, None, {}

    # Find end of class
    class_end = len(lines)
    indent_level = len(line) - len(line.lstrip())
    for i in range(class_start + 1, len(lines)):
        line_indent = len(lines[i]) - len(lines[i].lstrip())
        if line_indent <= indent_level and lines[i].strip():
            class_end = i
            break
        elif lines[i].strip() == "":
            continue

    class_lines = lines[class_start:class_end]
    class_content = "\n".join(class_lines)

    # Find table name
    table_match = re.search(r'__tablename__ = "(\w+)"', class_content)
    table_name = table_match.group(1) if table_match else None

    # Find fields
    fields = {}
    # Match field = Column(Type(...), ...)
    field_pattern = re.compile(r"(\w+) = Column\(([^,]+),?\s*(.*)\)", re.MULTILINE)
    for match in field_pattern.finditer(class_content):
        field_name = match.group(1)
        type_part = match.group(2).strip()
        options = match.group(3)

        # Extract type
        type_match = re.match(r"(\w+)\(", type_part)
        if type_match:
            col_type = type_match.group(1)
        else:
            col_type = type_part

        # Extract nullable
        nullable = True
        if "nullable=False" in options or "nullable = False" in options:
            nullable = False
        unique = "unique=True" in options or "unique = True" in options
        fields[field_name] = (col_type, nullable, unique)

    return expected_class_name, table_name, fields


def map_sqlalchemy_to_pydantic(sql_type: str) -> str:
    """Map SQLAlchemy type to Pydantic type."""
    mapping = {
        "String": "str",
        "Text": "str",
        "Integer": "int",
        "BigInteger": "int",
        "Boolean": "bool",
        "Numeric": "float",
        "Date": "date",
        "DateTime": "datetime",
        "JSON": "Dict[str, Any]",
        "ForeignKey": "int",  # Assuming id is int
    }
    return mapping.get(sql_type, "str")


def generate_repository(entity_name: str, class_name: str, file_path: str):
    content = f"""from ..base import BaseRepository
from ._model import {class_name}


class {class_name}Repository(BaseRepository):
    def __init__(self):
        super().__init__({class_name})
"""
    with open(file_path, "w") as f:
        f.write(content)


def generate_service(entity_name: str, class_name: str, file_path: str):
    content = f"""from ..base import BaseService
from ._repository import {class_name}Repository


class {class_name}Service(BaseService):
    def __init__(self):
        super().__init__({class_name}Repository)
"""
    with open(file_path, "w") as f:
        f.write(content)


def generate_controller(entity_name: str, class_name: str, file_path: str):
    content = f"""from fastapi import Body

from ..base import BaseController
from ._schema import {class_name}Schema
from ._service import {class_name}Service


class {class_name}Controller(BaseController):
    def __init__(self):
        super().__init__({class_name}Service)

    async def create(self, data: {class_name}Schema = Body(...)):
        return await super().create(data=data.model_dump())

    async def patch(self, id: int, data: {class_name}Schema = Body(...)):
        return await super().patch(id=id, data=data.model_dump(exclude_none=True))
"""
    with open(file_path, "w") as f:
        f.write(content)


def generate_schema(
    entity_name: str,
    class_name: str,
    fields: Dict[str, Tuple[str, bool]],
    file_path: str,
):
    imports = "from typing import Any, Dict, Optional\n\n"
    has_date = any("date" in map_sqlalchemy_to_pydantic(t) for t, *_ in fields.values())
    has_datetime = any(
        "datetime" in map_sqlalchemy_to_pydantic(t) for t, *_ in fields.values()
    )
    if has_date or has_datetime:
        imports = "from datetime import date, datetime\n" + imports
    elif has_date:
        imports = "from datetime import date\n" + imports
    elif has_datetime:
        imports = "from datetime import datetime\n" + imports

    content = imports
    content += f"""from ..base import BaseSchema


class {class_name}Schema(BaseSchema):
"""
    for field_name, (sql_type, nullable, *_rest) in fields.items():
        pydantic_type = map_sqlalchemy_to_pydantic(sql_type)
        content += f"    {field_name}: Optional[{pydantic_type}] = None\n"

    with open(file_path, "w") as f:
        f.write(content)


FAKE_VALUES = {
    "String": ("str", lambda name, i: f'"{name}_{i}"'),
    "Text": ("str", lambda name, i: f'"{name}_{i}"'),
    "Integer": ("int", lambda name, i: f"{i}"),
    "BigInteger": ("int", lambda name, i: f"{i}"),
    "Boolean": ("bool", lambda name, i: "True"),
    "Numeric": ("float", lambda name, i: f"{i}.5"),
    "Date": ("str", lambda name, i: f'"2026-01-0{min(i, 9)}"'),
    "DateTime": ("str", lambda name, i: f'"2026-01-0{min(i, 9)}T00:00:00"'),
    "JSON": ("dict", lambda name, i: f'{{"key": "val_{i}"}}'),
}

# Types where make_model needs index interpolation via f-string
_STRING_TYPES = {"String", "Text"}


def _fake(sql_type: str, field_name: str, index: int) -> str:
    _, fn = FAKE_VALUES.get(sql_type, ("str", lambda name, i: f'"{name}_{i}"'))
    return fn(field_name, index)


def generate_test(
    entity_name: str,
    class_name: str,
    table_name: str,
    fields: Dict[str, Tuple[str, bool]],
    file_path: str,
):
    route_prefix = table_name.replace("_", "-")
    endpoint = f"/api/v1/{route_prefix}/"

    # Pick the first non-unique string field as filter_field, fallback to first string
    filter_field = None
    first_string = None
    for fname, (ftype, nullable, *rest) in fields.items():
        if ftype in ("String", "Text"):
            unique = rest[0] if rest else False
            if first_string is None:
                first_string = fname
            if not unique:
                filter_field = fname
                break
    if not filter_field:
        filter_field = first_string or list(fields.keys())[0]

    # Build create_payload
    create_lines = []
    for fname, (ftype, nullable, *_) in fields.items():
        val = _fake(ftype, fname, 1)
        create_lines.append(f'        "{fname}": {val},')

    # Build update_payload (first non-nullable field with different value)
    update_field = None
    for fname, (ftype, nullable, *_) in fields.items():
        if not nullable:
            update_field = fname
            break
    if not update_field:
        update_field = list(fields.keys())[0]
    update_type = fields[update_field][0]
    update_val = _fake(update_type, f"updated_{update_field}", 1)

    # Collect unique fields for uuid suffix in make_model
    unique_fields = {fname for fname, (*_, unique) in fields.items() if unique}

    # Build make_model — use f-strings only for string types, use `index` directly for numbers
    model_lines = []
    for fname, (ftype, nullable, *_) in fields.items():
        if ftype in _STRING_TYPES:
            if fname in unique_fields:
                model_lines.append(
                    f'            "{fname}": f"{fname}_{{index}}_{{_uid}}",'
                )
            else:
                model_lines.append(f'            "{fname}": f"{fname}_{{index}}",')
        elif ftype in ("Integer", "BigInteger"):
            model_lines.append(f'            "{fname}": index,')
        elif ftype == "Numeric":
            model_lines.append(f'            "{fname}": index + 0.5,')
        elif ftype == "Boolean":
            model_lines.append(f'            "{fname}": True,')
        elif ftype == "DateTime":
            model_lines.append(f'            "{fname}": datetime(2026, 1, index),')
        elif ftype == "Date":
            model_lines.append(f'            "{fname}": date(2026, 1, index),')
        elif ftype == "JSON":
            model_lines.append(f'            "{fname}": {{"key": f"val_{{index}}"}},')
        else:
            model_lines.append(f'            "{fname}": f"{fname}_{{index}}",')

    filter_type = fields[filter_field][0]
    fv1 = _fake(filter_type, f"filter_{filter_field}", 1)
    fv2 = _fake(filter_type, f"filter_{filter_field}", 2)

    needs_uid = bool(unique_fields)
    has_dt = any(ft in ("Date", "DateTime") for ft, *_ in fields.values())
    imports = []
    if needs_uid:
        imports.append("import uuid")
    if has_dt:
        imports.append("from datetime import date, datetime")
    imports_str = "\n".join(imports) + ("\n\n" if imports else "")
    uid_line = "        _uid = uuid.uuid4().hex[:8]\n" if needs_uid else ""

    # build_create_payload override for unique fields
    build_create = ""
    if needs_uid:
        override_lines = []
        for fname, (ftype, nullable, *rest) in fields.items():
            unique = rest[0] if rest else False
            if unique and ftype in _STRING_TYPES:
                override_lines.append(
                    f'        payload["{fname}"] = f"{fname}_{{uuid.uuid4().hex[:8]}}"'
                )
        if override_lines:
            build_create = "\n    def build_create_payload(self):\n"
            build_create += "        payload = dict(self.create_payload)\n"
            build_create += "\n".join(override_lines) + "\n"
            build_create += "        return payload\n"

    content = f"""{imports_str}from src.entities.{entity_name}._model import {class_name}
from tests.base_entity_api_test import BaseEntityApiTest


class Test{class_name}Entity(BaseEntityApiTest):
    __test__ = True
    endpoint = "{endpoint}"
    create_payload = {{
{chr(10).join(create_lines)}
    }}
    update_payload = {{"{update_field}": {update_val}}}
    invalid_payload = {{}}
    filter_field = "{filter_field}"
    filter_value = {fv1}
    other_filter_value = {fv2}
{build_create}
    def make_model(self, index: int, **overrides):
{uid_line}        data = {{
{chr(10).join(model_lines)}
        }}
        data.update(overrides)
        return {class_name}(**data)
"""
    with open(file_path, "w") as f:
        f.write(content)


def update_init(entity_dir: str):
    init_path = os.path.join(entity_dir, "__init__.py")
    content = """from ._controller import *
from ._model import *
from ._repository import *
from ._schema import *
from ._service import *

"""
    with open(init_path, "w") as f:
        f.write(content)


def update_main_init(entity: str, class_name: str, table_name: str):
    main_init_path = "src/entities/__init__.py"
    with open(main_init_path, "r") as f:
        content = f.read()

    # Check if already imported
    import_line = f"from .{entity} import *"
    if import_line not in content:
        lines = content.split("\n")
        insert_index = len(lines)
        for i, line in enumerate(lines):
            if line.startswith("from .") and "import *" in line:
                insert_index = i + 1
        lines.insert(insert_index, import_line)
        content = "\n".join(lines)

    # Add the router include using table_name (plural)
    route_prefix = table_name.replace("_", "-")
    router_line = f"""api_router.include_router(
    {class_name}Controller().router, prefix="/{route_prefix}", tags=["{route_prefix}"]
)"""
    if router_line not in content:
        lines = content.split("\n")
        insert_index = len(lines)
        for i, line in enumerate(lines):
            if "api_router.include_router(" in line:
                j = i
                while j < len(lines) and not lines[j].strip().endswith(")"):
                    j += 1
                insert_index = j + 1
        lines.insert(insert_index, router_line)
        content = "\n".join(lines)

    with open(main_init_path, "w") as f:
        f.write(content)


def main():
    entities_dir = "src/entities"
    entities = [
        d
        for d in os.listdir(entities_dir)
        if os.path.isdir(os.path.join(entities_dir, d)) and d not in ["base"]
    ]

    for entity in entities:
        entity_dir = os.path.join(entities_dir, entity)
        model_file = os.path.join(entity_dir, "_model.py")
        controller_file = os.path.join(entity_dir, "_controller.py")

        if os.path.exists(model_file) and not os.path.exists(controller_file):
            logger.debug(f"Generating files for {entity}")

            expected_class_name = "".join(
                word.capitalize() for word in entity.split("_")
            )
            class_name, table_name, fields = parse_model_file(
                model_file, expected_class_name
            )
            logger.debug(
                f"Parsed {entity}: class={class_name}, table={table_name}, fields={fields}"
            )
            if not class_name:
                logger.debug(f"Could not find class {expected_class_name} for {entity}")
                continue

            # Generate repository
            generate_repository(
                entity, class_name, os.path.join(entity_dir, "_repository.py")
            )

            # Generate service
            generate_service(
                entity, class_name, os.path.join(entity_dir, "_service.py")
            )

            # Generate controller
            generate_controller(
                entity, class_name, os.path.join(entity_dir, "_controller.py")
            )

            # Generate schema
            generate_schema(
                entity, class_name, fields, os.path.join(entity_dir, "_schema.py")
            )

            # Generate test
            test_file = os.path.join("tests", f"test_{entity}_entity.py")
            if not os.path.exists(test_file):
                generate_test(entity, class_name, table_name, fields, test_file)

            # Update __init__.py
            update_init(entity_dir)
            update_main_init(entity, class_name, table_name)

            logger.debug(f"Generated files for {entity}")


if __name__ == "__main__":
    main()
