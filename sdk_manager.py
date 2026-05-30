from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import IO
from pathlib import Path

from dump_types import *
from string_utils import safe_cpp_name, is_compiler_generated


@dataclass
class CSharpConfig:
    pass


@dataclass
class _CppConfig:
    use_namespaces: bool = True


@dataclass
class CppOffsetsConfig(_CppConfig):
    include_methods: bool = True


@dataclass
class CppShortConfig(_CppConfig):
    include_offsets: bool = True
    include_enums: bool = True
    include_methods: bool = True


SDKConfig = CSharpConfig | CppOffsetsConfig | CppShortConfig

_OFFSETS_NS = "offsets"
_METHODS_NS = "sdk"


_CS_VALUE_TYPES: dict[str, str] = {
    "bool": "bool",
    "byte": "uint8_t", "sbyte": "int8_t",
    "short": "int16_t", "ushort": "uint16_t",
    "int": "int32_t", "uint": "uint32_t",
    "long": "int64_t", "ulong": "uint64_t",
    "float": "float", "double": "double",
    "char": "uint16_t",
    "void": "void",
    "nint": "intptr_t", "nuint": "uintptr_t",
    "IntPtr": "intptr_t", "UIntPtr": "uintptr_t",
}


def _cs_type_to_cpp(t: TypeInfo) -> str:
    if t.array_type or t.generic_params:
        base = "void*"
    else:
        base = _CS_VALUE_TYPES.get(t.type, "void*")
    if t.pointer_depth:
        base = base + "*" * t.pointer_depth
    if t.ref_kind is not None:
        base = base + "*"
    return base


class _NamespaceWriter:
    def __init__(self, file: IO, base_indent: int = 0):
        self._file = file
        self._base = base_indent
        self._opened: list[str] = []

    def enter(self, parts: list[str]) -> int:
        common = 0
        while (common < len(parts)
               and common < len(self._opened)
               and self._opened[common] == parts[common]):
            common += 1
        for i in range(len(self._opened), common, -1):
            self._file.write(f"{self._indent(i - 1)}}}\n")
        if common == 0 and self._opened:
            self._file.write("\n")
        for i in range(common, len(parts)):
            self._file.write(f"{self._indent(i)}namespace {parts[i]}\n{self._indent(i)}{{\n")
        self._opened = list(parts)
        return len(parts) + self._base

    def close(self) -> None:
        for i in range(len(self._opened), 0, -1):
            self._file.write(f"{self._indent(i - 1)}}}\n")
        self._opened.clear()

    def _indent(self, depth: int) -> str:
        return "\t" * (depth + self._base)


@dataclass
class _TypeEntry:
    ns_parts: list[str]
    type_info: ClassInfo | EnumInfo
    sort_key: str = ""


def _prepare_entries(types: list[ClassInfo | EnumInfo], use_namespaces: bool) -> list[_TypeEntry]:
    filtered = [
        t for t in types
        if not (isinstance(t, ClassInfo) and t.type == ClassType.INTERFACE)
        and not is_compiler_generated(t.get_name())
    ]
    name_counts = Counter(
        str(isinstance(t, ClassInfo)) + (t.namespace if use_namespaces else "") + t.get_name()
        for t in filtered
    )
    entries: list[_TypeEntry] = []
    for t in filtered:
        full = (t.namespace + "." if use_namespaces and t.namespace else "") + t.get_name()
        parts = full.split(".")
        key = str(isinstance(t, ClassInfo)) + (t.namespace if use_namespaces else "") + t.get_name()
        if name_counts[key] > 1:
            parts[0] = f"{parts[0]}_{t.type_def_index}"
        sort_key = (t.namespace if use_namespaces else "") + str(t.type_def_index) + t.get_name()
        entries.append(_TypeEntry(parts, t, sort_key))
    entries.sort(key=lambda e: e.sort_key)
    return entries


@dataclass
class _MethodEntry:
    name: str
    rva: int
    return_type: TypeInfo
    parameters: tuple[MethodParam, ...]
    is_static: bool


def _get_fields_offsets(class_info: ClassInfo) -> tuple[list[FieldInfo], list[FieldInfo]]:
    fields, static_fields = [], []
    for f in class_info.fields:
        if ModifierType.CONST in f.modifiers or is_compiler_generated(f.get_name()):
            continue
        (static_fields if ModifierType.STATIC in f.modifiers else fields).append(f)
    return fields, static_fields


def _collect_methods(class_info: ClassInfo) -> list[_MethodEntry]:
    source: list[MethodInfo] = []
    if class_info.generic_instances:
        for g in class_info.generic_instances:
            source.extend(g.methods)
    else:
        source.extend(class_info.methods)

    raw: list[_MethodEntry] = []
    for method in source:
        if is_compiler_generated(method.get_name()):
            continue
        is_static = ModifierType.STATIC in method.modifiers
        if method.generic_instances:
            for inst in method.generic_instances:
                if inst.rva == -1:
                    continue
                name = inst.alias if inst.alias else method.get_name()
                raw.append(_MethodEntry(name.rsplit(".", maxsplit=1)[-1], inst.rva,
                                        method.return_type, method.parameters, is_static))
        elif method.rva != -1:
            raw.append(_MethodEntry(method.get_name().rsplit(".", maxsplit=1)[-1], method.rva,
                                    method.return_type, method.parameters, is_static))

    counts: dict[str, int] = {}
    for e in raw:
        counts[e.name] = counts.get(e.name, 0) + 1
    for e in raw:
        if counts[e.name] > 1:
            e.name = f"{e.name}__{e.rva:X}"
    return raw


def _open_file(destination, mode: str) -> tuple[IO, bool]:
    if isinstance(destination, (str, Path)):
        return open(destination, mode, encoding="utf-8"), True
    return destination, False


class SDKManager:
    def __init__(self, dump_info: DumpInfo):
        self.__dump = dump_info

    def save_sdk(self, config: SDKConfig, destination: str | Path | IO) -> None:
        if isinstance(config, CSharpConfig):
            self._save_csharp(config, destination)
        elif isinstance(config, CppOffsetsConfig):
            self._save_cpp_offsets(config, destination)
        elif isinstance(config, CppShortConfig):
            self._save_cpp_short(config, destination)
        else:
            raise TypeError(f"Unknown SDK config: {type(config).__name__}")

    def _save_csharp(self, config: CSharpConfig, destination) -> None:
        file, should_close = _open_file(destination, "w")
        try:
            for i, image in enumerate(self.__dump.images):
                file.write(f"// Image {i}: {image.name} - {image.type_def_start}\n")
            if self.__dump.images:
                file.write("\n")
            all_types: list[ClassInfo | EnumInfo] = [*self.__dump.classes, *self.__dump.enums]
            all_types.sort(key=lambda t: t.type_def_index)
            for t in all_types:
                if isinstance(t, ClassInfo):
                    self._write_class_csharp(t, file)
                else:
                    self._write_enum_csharp(t, file)
        finally:
            if should_close:
                file.close()

    def _save_cpp_offsets(self, config: CppOffsetsConfig, destination) -> None:
        file, should_close = _open_file(destination, "w")
        try:
            file.write("#pragma once\n#include <cstddef>\n#include <cstdint>\n\n")
            file.write(f"namespace {_OFFSETS_NS}\n{{\n")
            entries = [e for e in _prepare_entries(self.__dump.classes, config.use_namespaces)
                       if isinstance(e.type_info, ClassInfo)]
            nsw = _NamespaceWriter(file, base_indent=1)
            for entry in entries:
                cls = entry.type_info
                fields, static_fields = _get_fields_offsets(cls)
                methods = _collect_methods(cls) if config.include_methods else []
                if not fields and not static_fields and not methods:
                    continue
                depth = nsw.enter(entry.ns_parts)
                self._write_field_offsets(file, fields, static_fields, depth)
                if methods:
                    self._write_method_offset_consts(file, methods, depth)
            nsw.close()
            file.write("}\n")
        finally:
            if should_close:
                file.close()

    def _save_cpp_short(self, config: CppShortConfig, destination) -> None:
        if isinstance(destination, (str, Path)):
            out_dir = Path(destination)
            out_dir.mkdir(parents=True, exist_ok=True)
            if config.include_offsets:
                with open(out_dir / "offsets.h", "w", encoding="utf-8") as f:
                    f.write("#pragma once\n#include <cstddef>\n\n")
                    self._write_short_offsets(config, f)
            if config.include_enums:
                with open(out_dir / "enums.h", "w", encoding="utf-8") as f:
                    f.write("#pragma once\n#include <cstdint>\n\n")
                    self._write_short_enums(config, f)
            if config.include_methods:
                with open(out_dir / "methods.h", "w", encoding="utf-8") as f:
                    f.write("#pragma once\n#include <cstdint>\n\n")
                    self._write_short_methods(config, f)
        else:
            if config.include_offsets:
                self._write_short_offsets(config, destination)
            if config.include_enums:
                self._write_short_enums(config, destination)
            if config.include_methods:
                self._write_short_methods(config, destination)

    def _write_short_offsets(self, config: CppShortConfig, file: IO) -> None:
        entries = [e for e in _prepare_entries(self.__dump.classes, config.use_namespaces)
                   if isinstance(e.type_info, ClassInfo)]
        file.write(f"namespace {_OFFSETS_NS}\n{{\n")
        nsw = _NamespaceWriter(file, base_indent=1)
        for entry in entries:
            fields, static_fields = _get_fields_offsets(entry.type_info)
            if not fields and not static_fields:
                continue
            depth = nsw.enter(entry.ns_parts)
            self._write_field_offsets(file, fields, static_fields, depth)
        nsw.close()
        file.write("}\n")

    def _write_short_enums(self, config: CppShortConfig, file: IO) -> None:
        entries = [e for e in _prepare_entries(self.__dump.enums, config.use_namespaces)
                   if isinstance(e.type_info, EnumInfo)]
        nsw = _NamespaceWriter(file)
        for entry in entries:
            enum = entry.type_info
            depth = nsw.enter(entry.ns_parts)
            tab = "\t" * depth
            underlying = _CS_VALUE_TYPES.get(enum.value_type, "int32_t")
            file.write(f"{tab}enum {safe_cpp_name(entry.ns_parts[-1])} : {underlying}\n{tab}{{\n")
            for i, var in enumerate(enum.variables):
                sep = "," if i < len(enum.variables) - 1 else ""
                file.write(f"{tab}\t{safe_cpp_name(var.name)} = {var.value}{sep}\n")
            file.write(f"{tab}}};\n")
        nsw.close()

    def _write_short_methods(self, config: CppShortConfig, file: IO) -> None:
        entries = [e for e in _prepare_entries(self.__dump.classes, config.use_namespaces)
                   if isinstance(e.type_info, ClassInfo)]
        init_assignments: list[tuple[str, str, int]] = []
        file.write(f"namespace {_METHODS_NS}\n{{\n")
        nsw = _NamespaceWriter(file, base_indent=1)
        for entry in entries:
            methods = _collect_methods(entry.type_info)
            if not methods:
                continue
            depth = nsw.enter([*entry.ns_parts, "Methods"])
            tab = "\t" * depth
            qualified_ns = "::".join(entry.ns_parts) + "::Methods"
            for m in methods:
                ret = _cs_type_to_cpp(m.return_type)
                param_types: list[str] = []
                param_decls: list[str] = []
                if not m.is_static:
                    param_types.append("void*")
                    param_decls.append("void* __this")
                for p in m.parameters:
                    pt = _cs_type_to_cpp(p)
                    param_types.append(pt)
                    param_decls.append(f"{pt} {safe_cpp_name(p.name)}")
                cast_type = f"{ret}(*)({', '.join(param_types)})"
                file.write(f"{tab}inline {ret} (*{m.name})({', '.join(param_decls)});\n")
                init_assignments.append((f"{qualified_ns}::{m.name}", cast_type, m.rva))
        nsw.close()
        file.write("\n\tinline void init(uintptr_t base)\n\t{\n")
        for path, cast_type, rva in init_assignments:
            file.write(f"\t\t{path} = reinterpret_cast<{cast_type}>(base + 0x{rva:X});\n")
        file.write("\t}\n")
        file.write("}\n")

    @staticmethod
    def _write_field_offsets(file: IO, fields, static_fields, indent: int) -> None:
        tab = "\t" * indent
        if static_fields:
            file.write(f"{tab}namespace StaticFields\n{tab}{{\n")
            for f in static_fields:
                file.write(f"{tab}\tconstexpr ptrdiff_t {safe_cpp_name(f.get_name())} = 0x{f.offset:X};\n")
            file.write(f"{tab}}}\n")
        if fields:
            file.write(f"{tab}namespace Fields\n{tab}{{\n")
            for f in fields:
                file.write(f"{tab}\tconstexpr ptrdiff_t {safe_cpp_name(f.get_name())} = 0x{f.offset:X};\n")
            file.write(f"{tab}}}\n")

    @staticmethod
    def _write_method_offset_consts(file: IO, methods: list[_MethodEntry], indent: int) -> None:
        if not methods:
            return
        tab = "\t" * indent
        file.write(f"{tab}namespace Methods\n{tab}{{\n")
        for m in methods:
            file.write(f"{tab}\tconstexpr uintptr_t {safe_cpp_name(m.name)} = 0x{m.rva:X};\n")
        file.write(f"{tab}}}\n")

    @staticmethod
    def _write_class_csharp(class_info: ClassInfo, file: IO) -> None:
        file.write(f"// Namespace: {class_info.namespace}\n")
        file.write(f"{class_info.get_signature()}\n")
        if class_info.is_empty():
            file.write("{}\n\n")
            return
        file.write("{\n")
        if class_info.fields:
            file.write("\t// Fields\n")
            for f in class_info.fields:
                file.write(f"\t{f}\n")
        if class_info.methods:
            if class_info.fields:
                file.write("\n")
            file.write("\t// Methods\n")
            for idx, method in enumerate(class_info.methods):
                if method.offset == -1:
                    file.write("\n\t// RVA: -1 Offset: -1\n")
                else:
                    file.write(f"\n\t// RVA: 0x{method.rva:X} Offset: 0x{method.offset:X}\n")
                if method.generic_params or class_info.generic_instances:
                    file.write(f"\t{method.get_signature()}\n")
                    file.write("\t/* GenericInstMethod :\n")
                    for g_method in method.generic_instances:
                        file.write("\t|\n")
                        if g_method.offset == -1:
                            file.write("\t|-RVA: -1 Offset: -1\n")
                        else:
                            file.write(f"\t|-RVA: 0x{g_method.rva:X} Offset: 0x{g_method.offset:X}\n")
                        params = (f'<{", ".join(str(p) for p in g_method.generic_params)}>'
                                  if method.generic_params else "")
                        file.write(f"\t|-{class_info.name}.{method.name}{params}\n")
                    for g_class in class_info.generic_instances:
                        g_instances: list[GenericMethodInstance] = []
                        if len(g_class.methods) > idx and g_class.methods[idx] == method:
                            g_instances = g_class.methods[idx].generic_instances
                        else:
                            for _m in g_class.methods:
                                if _m == method:
                                    g_instances = _m.generic_instances
                                    break
                        g_class_params = (f'<{", ".join(str(p) for p in g_class.generic_params)}>'
                                          if class_info.generic_params else "")
                        for g_method in g_instances:
                            file.write("\t|\n")
                            if g_method.offset == -1:
                                file.write("\t|-RVA: -1 Offset: -1\n")
                            else:
                                file.write(f"\t|-RVA: 0x{g_method.rva:X} Offset: 0x{g_method.offset:X}\n")
                            params = (f'<{", ".join(str(p) for p in g_method.generic_params)}>'
                                      if g_method.generic_params else "")
                            file.write(f"\t|-{class_info.name}{g_class_params}.{method.name}{params}\n")
                    file.write("\t*/\n")
                else:
                    file.write(f"\t{method.get_signature()}\n")
        file.write("}\n\n")

    @staticmethod
    def _write_enum_csharp(enum_info: EnumInfo, file: IO) -> None:
        file.write(f"// Namespace:{enum_info.namespace}\n")
        file.write(f"{' '.join(enum_info.modifiers)} enum {enum_info.name}"
                   f" // TypeDefIndex: {enum_info.type_def_index}\n")
        file.write("{\n\t// Fields\n")
        file.write(f"\tpublic {enum_info.value_type} value__; // 0x0\n")
        for var in enum_info.variables:
            file.write(f"\tpublic const {enum_info.name} {var.name} = {var.value};\n")
        file.write("}\n\n")
