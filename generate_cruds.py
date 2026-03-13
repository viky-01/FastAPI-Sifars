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
        fields[field_name] = (col_type, nullable)

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
        return await super().create(data.model_dump())

    async def patch(self, id: int, data: {class_name}Schema = Body(...)):
        return await super().patch(id, data.model_dump())
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
    has_date = any("date" in map_sqlalchemy_to_pydantic(t) for t, _ in fields.values())
    has_datetime = any(
        "datetime" in map_sqlalchemy_to_pydantic(t) for t, _ in fields.values()
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
    for field_name, (sql_type, nullable) in fields.items():
        pydantic_type = map_sqlalchemy_to_pydantic(sql_type)
        if nullable:
            pydantic_type = f"Optional[{pydantic_type}]"
        content += f"    {field_name}: {pydantic_type}\n"

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

            # Update __init__.py
            update_init(entity_dir)
            update_main_init(entity, class_name, table_name)

            logger.debug(f"Generated files for {entity}")


if __name__ == "__main__":
    main()
