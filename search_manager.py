from __future__ import annotations
from dataclasses import dataclass

from string_utils import *
from dump_types import *


@dataclass(slots=True)
class TypeFilter:
    type_name: str | None = None
    exact_type: bool = True
    regex_type: bool = False
    case_sensitive_type: bool = True

    min_pointer_depth: int | None = None
    max_pointer_depth: int | None = None

    is_reference: bool | None = None
    is_array: bool | None = None

    generic_params: list[TypeFilter] | None = None
    min_generic_params_count: int | None = None
    max_generic_params_count: int | None = None
    exact_generic_params_order: bool = True


@dataclass(slots=True)
class NamedTypeFilter(TypeFilter):
    name: str | None = None
    exact_name: bool = True
    regex_name: bool = False
    case_sensitive_name: bool = True

    has_default: bool | None = None


@dataclass(slots=True)
class MethodFilter:
    alias: str | None = None
    name: str | None = None
    exact_name: bool = True
    regex_name: bool = False
    case_sensitive_name: bool = True

    return_type: TypeFilter | None = None

    params: list[NamedTypeFilter] | None = None
    min_params_count: int | None = None
    max_params_count: int | None = None
    exact_params_order: bool = True

    generic_params: list[TypeFilter] | None = None
    min_generic_params_count: int | None = None
    max_generic_params_count: int | None = None
    exact_generic_params_order: bool = True

    modifiers: list[ModifierType] | None = None


@dataclass(slots=True)
class FieldFilter(NamedTypeFilter):
    alias: str | None = None
    modifiers: list[ModifierType] | None = None
    offset: int | None = None


@dataclass(slots=True)
class ClassFilter:
    alias: str | None = None
    name: str | None = None
    exact_name: bool = True
    regex_name: bool = False
    case_sensitive_name: bool = True

    namespace: str | None = None
    image: str | None = None

    class_type: ClassType | None = None
    modifiers: list[ModifierType] | None = None

    parents: list[TypeFilter] | None = None
    min_parents_count: int | None = None
    max_parents_count: int | None = None

    generic_params: list[TypeFilter] | None = None
    min_generic_params_count: int | None = None
    max_generic_params_count: int | None = None
    exact_generic_params_order: bool = True

    min_methods_count: int | None = None
    max_methods_count: int | None = None

    min_fields_count: int | None = None
    max_fields_count: int | None = None

    has_methods: list[MethodFilter] | None = None
    has_fields: list[FieldFilter] | None = None
    select_has_methods: bool = True
    select_has_fields: bool = True


@dataclass(slots=True)
class EnumFilter:
    alias: str | None = None
    name: str | None = None
    exact_name: bool = True
    regex_name: bool = False
    case_sensitive_name: bool = True

    image: str | None = None
    namespace: str | None = None

    modifiers: list[ModifierType] | None = None

    min_variables_count: int | None = None
    max_variables_count: int | None = None

    value_type: str | None = None

    has_variables: list[EnumVariableFilter] | None = None


@dataclass(slots=True)
class EnumVariableFilter:
    name: str | None = None
    exact_name: bool = True
    regex_name: bool = False
    case_sensitive_name: bool = True

    min_value: int | None = None
    max_value: int | None = None


def _match_bipartite(filters: list, items: list, match_func) -> list | None:
    candidates = [[item for item in items if match_func(f, item)] for f in filters]
    result: list = [None] * len(filters)
    used: set[int] = set()

    def backtrack(filter_idx: int) -> bool:
        if filter_idx == len(filters):
            return True
        for item in candidates[filter_idx]:
            item_id = id(item)
            if item_id in used:
                continue
            used.add(item_id)
            result[filter_idx] = item
            if backtrack(filter_idx + 1):
                return True
            used.discard(item_id)
            result[filter_idx] = None
        return False

    return result if backtrack(0) else None


def match_type(type_filter: TypeFilter, type_info: TypeInfo) -> bool:
    if type_filter.is_reference is not None:
        if type_filter.is_reference != bool(type_info.ref_kind):
            return False

    if type_filter.is_array is not None:
        if type_filter.is_array != bool(type_info.array_type):
            return False

    if type_filter.min_pointer_depth is not None:
        if type_info.pointer_depth < type_filter.min_pointer_depth:
            return False

    if type_filter.max_pointer_depth is not None:
        if type_info.pointer_depth > type_filter.max_pointer_depth:
            return False

    if type_filter.type_name is not None:
        if not match_string(
            type_filter.type_name,
            type_info.type,
            type_filter.exact_type,
            type_filter.regex_type,
            type_filter.case_sensitive_type,
        ):
            return False

    if type_filter.min_generic_params_count is not None:
        if len(type_info.generic_params) < type_filter.min_generic_params_count:
            return False

    if type_filter.max_generic_params_count is not None:
        if len(type_info.generic_params) > type_filter.max_generic_params_count:
            return False

    if type_filter.generic_params is not None:
        if not match_generic_params(
            type_filter.generic_params,
            type_info.generic_params,
            type_filter.exact_generic_params_order,
        ):
            return False

    return True


def match_named_type(type_filter: NamedTypeFilter, type_info: NamedTypeInfo) -> bool:
    if not match_type(type_filter, type_info):
        return False

    if type_filter.has_default is not None:
        if type_filter.has_default and type_info.default_value is None:
            return False

        if not type_filter.has_default and type_info.default_value is not None:
            return False

    if type_filter.name is not None:
        if not match_string(
            type_filter.name,
            type_info.name,
            type_filter.exact_name,
            type_filter.regex_name,
            type_filter.case_sensitive_name,
        ):
            return False

    return True


def match_method(method_filter: MethodFilter, method_info: MethodInfo) -> bool:
    if method_filter.name is not None:
        if not match_string(
            method_filter.name,
            method_info.name,
            method_filter.exact_name,
            method_filter.regex_name,
            method_filter.case_sensitive_name,
        ):
            return False

    if method_filter.modifiers:
        if not set(method_filter.modifiers).issubset(set(method_info.modifiers)):
            return False

    if method_filter.return_type is not None:
        if not match_type(method_filter.return_type, method_info.return_type):
            return False

    if method_filter.min_params_count is not None:
        if len(method_info.parameters) < method_filter.min_params_count:
            return False

    if method_filter.max_params_count is not None:
        if len(method_info.parameters) > method_filter.max_params_count:
            return False

    if method_filter.params is not None:
        if not match_params(
            method_filter.params,
            method_info.parameters,
            method_filter.exact_params_order,
        ):
            return False

    if method_filter.min_generic_params_count is not None:
        if len(method_info.generic_params) < method_filter.min_generic_params_count:
            return False

    if method_filter.max_generic_params_count is not None:
        if len(method_info.generic_params) > method_filter.max_generic_params_count:
            return False

    if method_filter.generic_params is not None:
        if not match_generic_params(
            method_filter.generic_params,
            method_info.generic_params,
            method_filter.exact_generic_params_order,
        ):
            return False

    return True


def match_field(field_filter: FieldFilter, field_info: FieldInfo) -> bool:
    if not match_named_type(field_filter, field_info):
        return False

    if field_filter.modifiers:
        if not set(field_filter.modifiers).issubset(set(field_info.modifiers)):
            return False

    if field_filter.offset is not None:
        if field_info.offset != field_filter.offset:
            return False

    return True


def match_class(class_filter: ClassFilter, class_info: ClassInfo, image_name: str = "") -> bool:
    if class_filter.namespace is not None:
        if class_info.namespace != class_filter.namespace:
            return False

    if class_filter.name is not None:
        if not match_string(
            class_filter.name,
            class_info.name,
            class_filter.exact_name,
            class_filter.regex_name,
            class_filter.case_sensitive_name,
        ):
            return False

    if class_filter.class_type is not None:
        if class_info.type != class_filter.class_type:
            return False

    if class_filter.modifiers:
        if not set(class_filter.modifiers).issubset(set(class_info.modifiers)):
            return False

    if class_filter.image is not None and class_filter.image != image_name:
            return False

    if class_filter.min_methods_count is not None:
        if len(class_info.methods) < class_filter.min_methods_count:
            return False

    if class_filter.max_methods_count is not None:
        if len(class_info.methods) > class_filter.max_methods_count:
            return False

    if class_filter.min_fields_count is not None:
        if len(class_info.fields) < class_filter.min_fields_count:
            return False

    if class_filter.max_fields_count is not None:
        if len(class_info.fields) > class_filter.max_fields_count:
            return False

    if class_filter.min_parents_count is not None:
        if len(class_info.parents) < class_filter.min_parents_count:
            return False

    if class_filter.max_parents_count is not None:
        if len(class_info.parents) > class_filter.max_parents_count:
            return False

    if class_filter.parents is not None:
        if _match_bipartite(class_filter.parents, list(class_info.parents), match_type) is None:
            return False

    if class_filter.min_generic_params_count is not None:
        if len(class_info.generic_params) < class_filter.min_generic_params_count:
            return False

    if class_filter.max_generic_params_count is not None:
        if len(class_info.generic_params) > class_filter.max_generic_params_count:
            return False

    if class_filter.generic_params is not None:
        if not match_generic_params(
            class_filter.generic_params,
            class_info.generic_params,
            class_filter.exact_generic_params_order,
        ):
            return False

    return True


def match_enum(f: EnumFilter, enum: EnumInfo, image_name: str = "") -> bool:
    if f.name is not None and not match_string(f.name, enum.name, f.exact_name, f.regex_name, f.case_sensitive_name):
        return False
    if f.namespace is not None and enum.namespace != f.namespace:
        return False
    if f.value_type is not None and enum.value_type != f.value_type:
        return False
    if f.min_variables_count is not None and len(enum.variables) < f.min_variables_count:
        return False
    if f.max_variables_count is not None and len(enum.variables) > f.max_variables_count:
        return False
    if f.modifiers is not None and not set(f.modifiers).issubset(set(enum.modifiers)):
        return False
    if f.image is not None and image_name != f.image:
        return False
    return True


def match_enum_variable(variable_filter: EnumVariableFilter, variable: EnumVariable) -> bool:
    if variable_filter.name is not None:
        if not match_string(
            variable_filter.name,
            variable.name,
            variable_filter.exact_name,
            variable_filter.regex_name,
            variable_filter.case_sensitive_name,
        ):
            return False

    if variable_filter.min_value is not None:
        if variable.value < variable_filter.min_value:
            return False

    if variable_filter.max_value is not None:
        if variable.value > variable_filter.max_value:
            return False

    return True


def match_has_methods(filters: list[MethodFilter], cls: ClassInfo) -> list[MethodInfo] | None:
    return _match_bipartite(filters, cls.methods, lambda f, m: match_method(f, m) or 
                            any(match_generic_method_instance(f, m, i) for i in m.generic_instances))


def match_has_fields(filters: list[FieldFilter], fields: list[FieldInfo]) -> list[FieldInfo] | None:
    return _match_bipartite(filters, fields, match_field)


def match_has_variables(filters: list[EnumVariableFilter], variables: list[EnumVariable]) -> list[EnumVariable] | None:
    return _match_bipartite(filters, variables, match_enum_variable)


def match_params(filters: list[NamedTypeFilter], params: list[MethodParam], exact_order: bool) -> bool:
    if len(filters) > len(params):
        return False
    if exact_order:
        return all(match_named_type(f, params[i]) for i, f in enumerate(filters))
    return _match_bipartite(filters, params, match_named_type) is not None


def match_generic_params(
    params_filters: list[TypeFilter],
    generic_params: tuple[TypeInfo, ...],
    exact_order: bool,
) -> bool:
    if len(params_filters) > len(generic_params):
        return False

    if exact_order:
        for i, param_filter in enumerate(params_filters):
            if not match_type(param_filter, generic_params[i]):
                return False
    else:
        if _match_bipartite(params_filters, generic_params, match_type) is None:
            return False

    return True


def match_generic_method_instance(f: MethodFilter, method: MethodInfo, 
                                   instance: GenericMethodInstance) -> bool:
    if f.name is not None:
        if not match_string(f.name, method.name, f.exact_name, f.regex_name, f.case_sensitive_name):
            return False
    if f.modifiers is not None and not set(f.modifiers).issubset(set(method.modifiers)):
        return False
    if f.return_type is not None and not match_type(f.return_type, instance.return_type):
        return False
    if f.min_params_count is not None and len(instance.parameters) < f.min_params_count:
        return False
    if f.max_params_count is not None and len(instance.parameters) > f.max_params_count:
        return False
    if f.params is not None:
        if not match_params(f.params, list(instance.parameters), f.exact_params_order):
            return False
    if f.generic_params is not None:
        if not match_generic_params(f.generic_params, instance.generic_params, f.exact_generic_params_order):
            return False
    if f.min_generic_params_count is not None and len(instance.generic_params) < f.min_generic_params_count:
        return False
    if f.max_generic_params_count is not None and len(instance.generic_params) > f.max_generic_params_count:
        return False
    return True


class ClassSearcher:
    def __init__(self, class_info: ClassInfo):
        self.__class_info: ClassInfo = class_info
        self.__selected_methods: list[MethodInfo] = []
        self.__selected_fields: list[FieldInfo] = []

    def get_class(self) -> ClassInfo:
        if not self.__selected_methods and not self.__selected_fields:
            return self.__class_info.copy()
        copy = self.__class_info.copy()
        if self.__selected_methods:
            alias_map = {m: m.alias for m in self.__selected_methods}
            copy.methods = [m for m in copy.methods if m in alias_map]
            for m in copy.methods:
                m.alias = alias_map[m]
        if self.__selected_fields:
            alias_map = {f: f.alias for f in self.__selected_fields}
            copy.fields = [f for f in copy.fields if f in alias_map]
            for f in copy.fields:
                f.alias = alias_map[f]
        return copy

    def select_methods(self, methods: list[MethodInfo],
                       select_remaining: bool = False) -> ClassSearcher:
        for method in methods:
            if method not in self.__selected_methods:
                self.__selected_methods.append(method.copy())
        if select_remaining:
            for method in self.__class_info.methods:
                if method not in self.__selected_methods:
                    self.__selected_methods.append(method.copy())
        return self

    def select_fields(self, fields: list[FieldInfo],
                      select_remaining: bool = False) -> ClassSearcher:
        for field in fields:
            if field not in self.__selected_fields:
                self.__selected_fields.append(field.copy())
        if select_remaining:
            for field in self.__class_info.fields:
                if field not in self.__selected_fields:
                    self.__selected_fields.append(field.copy())
        return self

    def find_methods(
        self,
        method_filter: MethodFilter | None = None,
        find_first: bool = False,
        include_generic_instances: bool = True
    ) -> list[MethodInfo]:
        result: list[MethodInfo] = []

        def check_method(method: MethodInfo) -> bool:
            if method_filter is None:
                return True
            if match_method(method_filter, method):
                return True
            if include_generic_instances:
                for instance in method.generic_instances:
                    if match_generic_method_instance(method_filter, method, instance):
                        return True
            return False

        for method in self.__class_info.methods:
            if check_method(method):
                copy = method.copy()
                if method_filter is not None and include_generic_instances:
                    has_specific = (method_filter.return_type is not None
                                    or method_filter.params is not None
                                    or method_filter.min_params_count is not None
                                    or method_filter.max_params_count is not None)
                    if has_specific:
                        copy.generic_instances = [
                            i.copy() for i in method.generic_instances
                            if match_generic_method_instance(method_filter, method, i)
                        ]
                result.append(copy)
                if find_first:
                    return result

        if include_generic_instances:
            seen: set[int] = set(id(m) for m in result)
            for g_class in self.__class_info.generic_instances:
                for method in g_class.methods:
                    if id(method) in seen:
                        continue
                    if check_method(method):
                        copy = method.copy()
                        result.append(copy)
                        seen.add(id(method))
                        if find_first:
                            return result

        return result

    def find_method(
        self,
        method_filter: MethodFilter | None = None,
    ) -> MethodInfo | None:
        result = self.find_methods(method_filter, find_first=True)
        return result[0] if result else None

    def find_fields(
        self,
        field_filter: FieldFilter | None = None,
        find_first: bool = False,
    ) -> list[FieldInfo]:
        result: list[FieldInfo] = []
        for field in self.__class_info.fields:
            if field_filter is not None and not match_field(field_filter, field):
                continue

            result.append(field.copy())

            if find_first:
                return result

        return result

    def find_field(
        self,
        field_filter: FieldFilter | None = None,
    ) -> FieldInfo | None:
        result = self.find_fields(field_filter, find_first=True)
        return result[0] if result else None


class DumpSearcher:
    def __init__(self, dump_info: DumpInfo):
        self.data = dump_info
        self.__selected_classes: list[ClassInfo] = []
        self.__selected_enums: list[EnumInfo] = []

    def select_classes(
        self,
        filters: list[ClassFilter] | ClassFilter | None = None,
        select_remaining: bool = False,
    ) -> DumpSearcher:
        for cls in self.find_classes(filters, raw_return=True):
            if cls not in self.__selected_classes:
                self.__selected_classes.append(cls)
        if select_remaining:
            for cls in self.data.classes:
                if cls not in self.__selected_classes:
                    self.__selected_classes.append(cls.copy())
        return self

    def select_enums(
        self,
        filters: list[EnumFilter] | EnumFilter | None = None,
        select_remaining: bool = False,
    ) -> DumpSearcher:
        selected_indices = {e.type_def_index for e in self.__selected_enums}
        for enum in self.find_enums(filters):
            if enum.type_def_index not in selected_indices:
                self.__selected_enums.append(enum)
                selected_indices.add(enum.type_def_index)
        if select_remaining:
            for enum in self.data.enums:
                if enum.type_def_index not in selected_indices:
                    self.__selected_enums.append(enum.copy())
                    selected_indices.add(enum.type_def_index)
        return self

    def get_dump_info(self) -> DumpInfo:
        images = list(self.data.images)
        if not self.__selected_classes and not self.__selected_enums:
            return DumpInfo(
                images=images,
                classes=[c.copy() for c in self.data.classes],
                enums=[e.copy() for e in self.data.enums],
            )
        return DumpInfo(
            images=images,
            classes=[c.copy() for c in self.__selected_classes],
            enums=[e.copy() for e in self.__selected_enums],
        )

    def find_classes(
        self,
        filters: list[ClassFilter] | ClassFilter | None = None,
        find_first: bool = False,
        raw_return: bool = False,
    ) -> list[ClassSearcher | ClassInfo]:
        result: list[ClassSearcher | ClassInfo] = []
        if filters is None:
            return [ClassSearcher(c).get_class() if raw_return else ClassSearcher(c) 
                    for c in self.data.classes]
        if not filters:
            return []
        filters_list = [filters] if isinstance(filters, ClassFilter) else filters

        for f in filters_list:
            for cls in self.data.classes:
                if not match_class(f, cls, self.data.get_image_name(cls.type_def_index)):
                    continue

                searcher = ClassSearcher(cls)

                if f.has_methods is not None:
                    found_methods = match_has_methods(f.has_methods, cls)
                    if found_methods is None:
                        continue
                    if f.select_has_methods:
                        for method, mf in zip(found_methods, f.has_methods):
                            method_copy = method.copy()
                            if mf.alias:
                                method_copy.alias = mf.alias
                            searcher.select_methods([method_copy])

                if f.has_fields is not None:
                    found_fields = match_has_fields(f.has_fields, cls.fields)
                    if found_fields is None:
                        continue
                    if f.select_has_fields:
                        for field, ff in zip(found_fields, f.has_fields):
                            field_copy = field.copy()
                            if ff.alias:
                                field_copy.alias = ff.alias
                            searcher.select_fields([field_copy])

                if f.alias:
                    cls.alias = f.alias

                result.append(searcher.get_class() if raw_return else searcher)
                if find_first:
                    return result

        return result


    def find_class(
        self,
        class_filter: ClassFilter | None = None,
        raw_return: bool = False
    ) -> ClassSearcher | ClassInfo | None:
        result = self.find_classes(class_filter, True, raw_return)
        return result[0] if result else None

    def find_enums(
        self,
        filters: list[EnumFilter] | EnumFilter | None = None,
        find_first: bool = False,
    ) -> list[EnumInfo]:
        result: list[EnumInfo] = []
        if filters is None:
            return [e.copy() for e in self.data.enums]
        if not filters:
            return []
        filters_list = [filters] if isinstance(filters, EnumFilter) else filters

        for f in filters_list:
            for enum in self.data.enums:
                if not match_enum(f, enum, self.data.get_image_name(enum.type_def_index)):
                    continue
                if f.has_variables is not None \
                and match_has_variables(f.has_variables, enum.variables) is None:
                    continue
                enum_copy = enum.copy()
                if f.alias:
                    enum_copy.alias = f.alias
                result.append(enum_copy)
                if find_first:
                    return result

        return result

    def find_enum(
        self,
        enum_filter: EnumFilter | None = None,
    ) -> EnumInfo | None:
        result = self.find_enums(enum_filter, find_first=True)
        return result[0] if result else None
