from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from string_utils import *


class RefKind(StrEnum):
    REF = "ref"
    IN = "in"
    OUT = "out"


class ModifierType(StrEnum):
    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"
    ABSTRACT = "abstract"
    VIRTUAL = "virtual"
    OVERRIDE = "override"
    CONST = "const"
    STATIC = "static"
    READONLY = "readonly"
    SEALED = "sealed"
    EXTERN = "extern"


class ClassType(StrEnum):
    CLASS = "class"
    STRUCT = "struct"
    INTERFACE = "interface"


class AttributeType(StrEnum):
    IN = "[In]"
    OUT = "[Out]"


class TypeInfo:
    def __init__(self, string: str = ""):
        self.type: str = ""
        self.pointer_depth: int = 0
        self.ref_kind: RefKind | None = None
        self.generic_params: tuple[TypeInfo, ...] = ()
        self.array_type: str | None = None
        self._cached_signature: str | None = None
        self._hash: int | None = None
        if string:
            self.parse_type(string)

    def __str__(self):
        if self._cached_signature is None:
            self._cached_signature = TypeInfo._compute_signature(self)
        return self._cached_signature

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self.__str__())
        return self._hash

    def __eq__(self, other: TypeInfo) -> bool:
        return hash(self) == hash(other)

    def _compute_signature(self) -> str:
        result = []
        if self.ref_kind is not None:
            result.append(f"{str(self.ref_kind)} ")
        result.append(self.type)
        if self.generic_params:
            result.append(f"<{', '.join([str(p) for p in self.generic_params])}>")
        if self.pointer_depth:
            result.append("*" * self.pointer_depth)
        if self.array_type:
            result.append(self.array_type)
        return "".join(result)

    def parse_type(self, string: str) -> None:
        splitted = generic_type_split(string)
        if len(splitted) == 2:
            self.ref_kind = RefKind(splitted[0])
        while splitted[-1][-1] == '*':
            splitted[-1] = splitted[-1][:-1]
            self.pointer_depth += 1
        array_type: str = ""
        while splitted[-1][-1] == "]":
            array_start = splitted[-1].rfind("[")
            array_type = splitted[-1][array_start:] + array_type
            splitted[-1] = splitted[-1][:array_start]
        if array_type:
            self.array_type = array_type
        generic_params = parse_generic_params(splitted[-1])
        if generic_params:
            self.type = splitted[-1].replace(generic_params, "", 1)
            self.generic_params = tuple(TypeInfo(param) for param in generic_type_split(generic_params[1:-1], ","))
        else:
            self.type = splitted[-1]

    def copy_from(self, other: TypeInfo) -> None:
        self.type = other.type
        self.pointer_depth = other.pointer_depth
        self.ref_kind = other.ref_kind
        self.generic_params = tuple(p.copy() for p in other.generic_params)
        self.array_type = other.array_type

    def copy(self) -> TypeInfo:
        ret = TypeInfo()
        ret.copy_from(self)
        return ret


class NamedTypeInfo(TypeInfo):
    def __init__(self, string: str = ""):
        super().__init__()
        self.alias: str | None = None
        self.name: str = ""
        self.default_value: str | None = None
        if string:
            self.parse_type(string)

    def __str__(self):
        if self._cached_signature is None:
            self._cached_signature = NamedTypeInfo._compute_signature(self)
        return self._cached_signature

    def __eq__(self, other: NamedTypeInfo) -> bool:
        return hash(self) == hash(other)

    def _compute_signature(self):
        return f"{super().__str__()} {self.name}{f' = {self.default_value}' if self.default_value else ''}"

    def get_name(self) -> str:
        return self.name if not self.alias else self.alias

    def parse_type(self, string: str) -> None:
        def_val_start = string.rfind(" = ")
        if def_val_start != -1:
            self.default_value = string[def_val_start + 3:]
            string = string[:def_val_start]
        name_start = string.rfind(" ")
        self.name = string[name_start + 1:]
        string = string[:name_start]
        super().parse_type(string)

    def copy_from(self, other: NamedTypeInfo) -> None:
        TypeInfo.copy_from(self, other)
        self.alias = other.alias
        self.name = other.name
        self.default_value = other.default_value

    def copy(self) -> NamedTypeInfo:
        ret = NamedTypeInfo()
        ret.copy_from(self)
        return ret


class FieldInfo(NamedTypeInfo):
    def __init__(self, string: str = ""):
        super().__init__()
        self.modifiers: tuple[ModifierType, ...] = ()
        self.offset: int | None = None
        self.metadata_offset: int | None = None
        if string:
            self.parse_type(string)

    def __str__(self):
        return (f"{' '.join(self.modifiers)} {super().__str__()};"
                f"{f' // 0x{hex(self.offset)[2:].upper()}' if self.offset is not None else ''}")

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self.__str__())
        return self._hash

    def __eq__(self, other: FieldInfo) -> bool:
        return hash(self) == hash(other)

    def copy_from(self, other: FieldInfo) -> None:
        NamedTypeInfo.copy_from(self, other)
        self._hash = None
        self.modifiers = other.modifiers
        self.offset = other.offset
        self.metadata_offset = other.metadata_offset

    def copy(self) -> FieldInfo:
        ret = FieldInfo()
        ret.copy_from(self)
        return ret


class MethodParam(NamedTypeInfo):
    def __init__(self):
        super().__init__()
        self.attributes: tuple[AttributeType, ...] = ()

    def __str__(self):
        if self._cached_signature is None:
            self._cached_signature = self._compute_signature()
        return self._cached_signature

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self.__str__())
        return self._hash

    def __eq__(self, other: MethodParam) -> bool:
        return hash(self) == hash(other)

    def _compute_signature(self) -> str:
        return f'{(" ".join(self.attributes) + " ") if self.attributes else ""}{super().__str__()}'

    def copy_from(self, other: MethodParam) -> None:
        NamedTypeInfo.copy_from(self, other)
        self.attributes = tuple(other.attributes)

    def copy(self) -> MethodParam:
        ret = MethodParam()
        ret.copy_from(self)
        return ret


@dataclass
class GenericMethodInstance:
    alias: str | None = None
    return_type: TypeInfo = field(default_factory=TypeInfo)
    parameters: tuple[MethodParam, ...] = ()
    offset: int = 0x0
    rva: int = 0x0
    generic_params: tuple[TypeInfo, ...] = ()

    def copy_from(self, other: GenericMethodInstance) -> None:
        self.alias = other.alias
        self.return_type.copy_from(other.return_type)
        self.parameters = tuple(p.copy() for p in other.parameters)
        self.offset = other.offset
        self.rva = other.rva
        self.generic_params = tuple(p.copy() for p in other.generic_params)

    def copy(self) -> GenericMethodInstance:
        ret = GenericMethodInstance()
        ret.copy_from(self)
        return ret


class MethodInfo(GenericMethodInstance):
    def __init__(self):
        super().__init__()
        self.name: str = ""
        self.modifiers: tuple[ModifierType, ...] = ()
        self.generic_instances: list[GenericMethodInstance] = []
        self._hash: int | None = None
        self._cached_signature: str | None = None

    def __str__(self):
        result = self.get_signature()
        if self.offset == -1:
            result = f'\n\t// RVA: -1 Offset: -1\n\t' + result
        else:
            result = f'\n\t// RVA: 0x{hex(self.rva)[2:].upper()} Offset: 0x{hex(self.offset)[2:].upper()}\n\t' + result
        return result

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(self.get_signature())
        return self._hash

    def _compute_signature(self):
        params = f'<{", ".join([str(p) for p in self.generic_params])}>' if self.generic_params else ''
        return (f"{' '.join(self.modifiers)} {self.return_type} {self.name}{params}"
                f"({', '.join([str(p) for p in self.parameters])})"
                f"{';' if 'abstract' in self.modifiers else ' { }'}")

    def get_name(self) -> str:
        return self.name if not self.alias else self.alias

    def get_signature(self) -> str:
        if self._cached_signature is None:
            self._cached_signature = self._compute_signature()
        return self._cached_signature

    def __eq__(self, other: MethodInfo) -> bool:
        return hash(self) == hash(other)

    def copy_from(self, other: MethodInfo) -> None:
        GenericMethodInstance.copy_from(self, other)
        self._hash = None
        self.name = other.name
        self.modifiers = tuple(other.modifiers)
        self.generic_instances = [i.copy() for i in other.generic_instances]
        self._hash = other._hash
        self._cached_signature = other._cached_signature

    def copy(self) -> MethodInfo:
        ret = MethodInfo()
        ret.copy_from(self)
        return ret


@dataclass
class GenericClassInstance:
    alias: str | None = None
    methods: list[MethodInfo] = field(default_factory=list)
    parents: tuple[TypeInfo, ...] = ()
    generic_params: tuple[TypeInfo, ...] = ()

    def copy_from(self, other: GenericClassInstance) -> None:
        self.alias = other.alias
        self.methods = [m.copy() for m in other.methods]
        self.parents = tuple(p.copy() for p in other.parents)
        self.generic_params = tuple(p.copy() for p in other.generic_params)

    def copy(self) -> GenericClassInstance:
        ret = GenericClassInstance()
        ret.copy_from(self)
        return ret
        


class ClassInfo(GenericClassInstance):
    def __init__(self):
        super().__init__()
        self.namespace: str = ""
        self.name: str = ""
        self.type: ClassType | None = None
        self.type_def_index: int = 0
        self.modifiers: tuple[ModifierType, ...] = ()
        self.fields: list[FieldInfo] = []
        self.generic_instances: list[GenericClassInstance] = []
        self._cached_signature: str | None = None

    def __str__(self):
        return (f'// Namespace: {self.namespace}\n'
                f'{self.get_signature()}')

    def get_name(self) -> str:
        return self.name if not self.alias else self.alias

    def is_empty(self) -> bool:
        return not bool(self.fields or self.methods or self.generic_instances)

    def _compute_signature(self):
        params = f'<{", ".join([str(p) for p in self.generic_params])}>' if self.generic_params else ''
        return (f"{' '.join(self.modifiers)} {self.type} {self.name}{params}"
                f"{(' : ' + ', '.join([str(p) for p in self.parents])) if self.parents else ''}"
                f" // TypeDefIndex: {self.type_def_index}")

    def get_signature(self) -> str:
        if self._cached_signature is None:
            self._cached_signature = self._compute_signature()
        return self._cached_signature

    def copy_from(self, other: ClassInfo) -> None:
        GenericClassInstance.copy_from(self, other)
        self.namespace = other.namespace
        self.name = other.name
        self.type = other.type
        self.type_def_index = other.type_def_index
        self.modifiers = other.modifiers
        self.fields = [f.copy() for f in other.fields]
        self.generic_instances = [g.copy() for g in other.generic_instances]
        self._cached_signature = other._cached_signature

    def copy(self) -> ClassInfo:
        ret = ClassInfo()
        ret.copy_from(self)
        return ret


@dataclass
class EnumVariable:
    name: str = ""
    value: int = 0


@dataclass
class EnumInfo:
    alias: str | None = None
    namespace: str = ""
    name: str = ""
    type_def_index: int = 0
    variables: list[EnumVariable] = field(default_factory=list)
    modifiers: list[ModifierType] = field(default_factory=list)
    value_type: str = ""

    def copy(self) -> EnumInfo:
        ret = EnumInfo(
            alias=self.alias, namespace=self.namespace, name=self.name,
            type_def_index=self.type_def_index, value_type=self.value_type,
            variables=list(self.variables),
            modifiers=list(self.modifiers)
        )
        return ret

    def get_name(self) -> str:
       return self.name if not self.alias else self.alias


class ImageInfo:
    images_count: int = 0

    def __init__(self):
        self.name: str = ""
        self.type_def_start: int = 0
        self.type_def_end: int = 99999

    def __str__(self):
        return f'// Image {ImageInfo.images_count}: {self.name} - {self.type_def_start}'


@dataclass
class DumpInfo:
    images: list[ImageInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    enums: list[EnumInfo] = field(default_factory=list)

    def get_image_name(self, idx: int) -> str:
        for image in self.images:
            if image.type_def_end >= idx >= image.type_def_start:
                return image.name
        return ""
