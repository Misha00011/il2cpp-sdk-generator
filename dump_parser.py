from dump_types import *
import re


class DumpParser:
    image_pattern = re.compile(r"// Image.*: (.+) - (\d+)")
    namespace_pattern = re.compile(r"// Namespace: (.*)")
    method_offset_pattern = re.compile(r"RVA: (-?(?:0x)?[A-Z0-9]+) Offset: (-?(?:0x)?[A-Z0-9]+)")

    def __init__(self, path: str | None = None):
        self.__dump_info: DumpInfo | None = None
        self.__path: str = path

    def __parse_method_param(self, string: str) -> MethodParam:
        ret = MethodParam()
        if string:
            splitted = string.split(" ", maxsplit=2)
            for i, s in enumerate(splitted):
                if s[0] != '[':
                    ret.attributes = tuple(AttributeType(t) for t in splitted[:i])
                    splitted = splitted[i:]
                    break
            NamedTypeInfo.parse_type(ret, " ".join(splitted))
        return ret

    def __parse_field(self, line: str) -> FieldInfo:
        ret = FieldInfo()
        line = line.strip()
        is_constant_field = " const " in line
        if is_constant_field:
            line = line.rstrip(";")
        else:
            line, offset_str = line.rsplit("; // ", maxsplit=1)
            ret.offset = int(offset_str, base=16)

        metadata_offset = line.rfind("/*Met")  # parsing /*Metadata offset
        if metadata_offset != -1:
            ret.metadata_offset = int(line[metadata_offset + 18:-2], base=16)
            line = line[:metadata_offset - 1]

        splitted_line = generic_quotes_type_split(line)
        for i, modifier in enumerate(splitted_line):
            if modifier not in ModifierType._value2member_map_:
                ret.modifiers = tuple([ModifierType(m) for m in splitted_line[:i]])
                splitted_line = splitted_line[i:]
                break
        ret.type = splitted_line[0]
        ret.name = splitted_line[1]
        if len(splitted_line) > 2:
            ret.default_value = " ".join(splitted_line[3:])
        return ret

    def __parse_method(self, method_info: MethodInfo, line: str) -> None:
        line = line.strip()
        line = line[:line.rfind(")")]
        line, params = line.split("(", maxsplit=1)

        if params:
            splitted_params = generic_quotes_type_split(params, ', ')
            method_info.parameters = tuple(self.__parse_method_param(p) for p in splitted_params)

        splitted_type = generic_type_split(line)
        for i, modifier in enumerate(splitted_type):
            if modifier not in ModifierType._value2member_map_:
                method_info.modifiers = tuple(ModifierType(m) for m in splitted_type[:i])
                splitted_type = splitted_type[i:]
                break

        method_info.return_type = TypeInfo(" ".join(splitted_type[:-1]))

        g_params = parse_generic_params(splitted_type[-1]) if splitted_type[-1][-1] == ">" else ""
        if g_params:
            method_info.name = splitted_type[-1].replace(g_params, "", 1)
            method_info.generic_params = tuple(TypeInfo(p) for p in generic_split(g_params[1:-1], ","))
        else:
            method_info.name = splitted_type[-1]

    def __parse_class_header(self, line: str) -> ClassInfo:
        ret = ClassInfo()
        line, type_def_index = line.split(" // TypeDefIndex: ")
        ret.type_def_index = int(type_def_index)
        splitted_line = line.split(" : ", 1)

        # inheritance check
        if len(splitted_line) == 2:
            ret.parents = tuple(TypeInfo(t) for t in generic_split(splitted_line[1], ","))

        splitted_line = generic_split(splitted_line[0])

        ret.modifiers = tuple(ModifierType(m) for m in splitted_line[:-2])
        ret.type = ClassType(splitted_line[-2])
        ret.name = splitted_line[-1]
        if ret.name.endswith(">"):
            g_params = parse_generic_params(ret.name)
            if g_params:
                ret.name = ret.name.replace(g_params, "", 1)
                ret.generic_params = tuple(TypeInfo(t) for t in generic_split(g_params[1:-1], ","))
        return ret

    def __parse_enum_header(self, line: str) -> EnumInfo:
        ret = EnumInfo()
        splitted_line = line.split()
        type_index = splitted_line.index("enum")

        ret.modifiers = tuple(ModifierType(m) for m in splitted_line[:type_index])
        ret.name = splitted_line[type_index + 1]
        ret.name = ret.name.replace(parse_generic_params(ret.name), "")
        ret.type_def_index = int(splitted_line[-1])
        return ret

    def __parse_enum_variable(self, line: str) -> EnumVariable:
        ret = EnumVariable()
        line = line[13:-1]  # removing "public const " and ";"
        line = line.replace(" =", "", 1)
        splitted_line = line.split()

        ret.value = int(splitted_line[-1])
        ret.name = splitted_line[-2]
        return ret

    def __resolve_generic_method(self, class_info: ClassInfo, line: str) -> None:
        line: str = line.lstrip("|-")
        line = line.replace(class_info.name, "", 1)
        splitted_line = generic_split(line, ".")
        class_generic_params = splitted_line[0]

        g_class_instance: GenericClassInstance
        g_method_info: GenericMethodInstance = class_info.methods[-1].generic_instances[-1]

        g_method_info.parameters = tuple(p.copy() for p in class_info.methods[-1].parameters)
        g_method_info.return_type.copy_from(class_info.methods[-1].return_type)

        # checking class instances (first generic param)
        if class_generic_params:
            class_generic_params = generic_split(class_generic_params[1:-1], ",")
            for instance_info in class_info.generic_instances:
                if instance_info.generic_params == class_generic_params:
                    g_class_instance = instance_info
                    break
            else:
                class_info.generic_instances.append(GenericClassInstance())
                g_class_instance = class_info.generic_instances[-1]
                g_class_instance.generic_params = tuple(TypeInfo(p) for p in class_generic_params)
                g_class_instance.parents = tuple(p.copy() for p in class_info.parents)

            # renaming parents params
            for parent in g_class_instance.parents:
                new_generic_params = list(parent.generic_params)
                for i in range(len(g_class_instance.generic_params)):
                    for j in range(len(parent.generic_params)):
                        old_s = str(parent.generic_params[j])
                        new_s = re.sub(rf"\b{re.escape(class_info.generic_params[i].type)}\b",
                                       g_class_instance.generic_params[i].type, old_s)
                        if old_s != new_s:
                            new_generic_params[j] = TypeInfo(new_s)
                parent.generic_params = tuple(new_generic_params)

            # adding the method to a generic class instance
            if not g_class_instance.methods or not g_class_instance.methods[-1] == class_info.methods[-1]:
                g_class_instance.methods.append(class_info.methods[-1].copy())
                g_method_info = g_class_instance.methods[-1].generic_instances[-1]
                del class_info.methods[-1].generic_instances[0]
            else:
                g_method_info = class_info.methods[-1].generic_instances.pop()
                g_class_instance.methods[-1].generic_instances.append(g_method_info)

            # renaming template class args in the method signature
            for i in range(len(class_info.generic_params)):
                for param in g_method_info.parameters:
                    param.type = re.sub(rf"\b{re.escape(class_info.generic_params[i].type)}\b",
                                        class_generic_params[i], param.type)
                g_method_info.return_type.type = re.sub(rf"\b{re.escape(class_info.generic_params[i].type)}\b",
                                                        class_generic_params[i], g_method_info.return_type.type)

        # parsing generic params
        if splitted_line[-1][-1] == ">":
            # ['', 'CallStatic<__Il2CppFullySharedGenericType>'] output example
            g_method_info.generic_params = tuple(TypeInfo(p) for p in generic_split(parse_generic_params(splitted_line[-1])[1:-1], ","))
            # renaming template method args in the method signature
            for i in range(len(class_info.methods[-1].generic_params)):
                for param in g_method_info.parameters:
                    param.type = re.sub(rf"\b{re.escape(class_info.methods[-1].generic_params[i].type)}\b",
                                        g_method_info.generic_params[i].type, param.type)
                g_method_info.return_type.type = re.sub(rf"\b{re.escape(class_info.methods[-1].generic_params[i].type)}\b",
                                                        g_method_info.generic_params[i].type,
                                                        g_method_info.return_type.type)

    def __resolve_namespaces(self) -> None:
        types: list[ClassInfo | EnumInfo] = [*self.__dump_info.classes, *self.__dump_info.enums]
        types.sort(key=lambda t: t.type_def_index)
        change_count: int = 0

        for i, t in enumerate(types):
            if "." in t.name:
                change_count += 1
            else:
                for j in range(change_count):
                    types[i - j - 1].namespace = t.namespace
                change_count = 0

    def parse_dump(self, path: str | None = None) -> DumpInfo:
        path = path if path else self.__path
        if path:
            self.__dump_info = DumpInfo()
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    print(f'[+] Parsing "{path}"...')
                    enum_flag: bool = False
                    class_flag: bool = False
                    fields_flag: bool = False
                    methods_flag: bool = False
                    method_start_flag: bool = False
                    generic_method_flag: bool = False
                    comments_flag: bool = False
                    current_namespace: str = ""
                    lines: list[str] = file.readlines()
                    parse_flag: bool = False
                    start_idx: int = 0

                    # parsing images
                    for line in lines:
                        start_idx += 1
                        match = re.match(DumpParser.image_pattern, line)
                        if match:
                            self.__dump_info.images.append(ImageInfo())
                            self.__dump_info.images[-1].name = match.group(1)
                            self.__dump_info.images[-1].type_def_start = int(match.group(2))
                            if len(self.__dump_info.images) > 1:
                                self.__dump_info.images[-2].type_def_end = int(match.group(2)) - 1
                        else:
                            break

                    skip_count: int = 0
                    # parsing the main content
                    for i in range(start_idx, len(lines)):
                        if skip_count > 0:
                            skip_count -= 1
                            continue

                        striped_line = lines[i].strip()
                        if striped_line:
                            # skipping comments
                            if striped_line[0] == "[":
                                comments_flag = True
                            if striped_line[-1] == "]":
                                comments_flag = False
                                continue
                        if comments_flag:
                            continue

                        # skipping types end {} already skipped with { type start
                        if striped_line == "}":
                            enum_flag = class_flag = fields_flag = methods_flag = False
                            skip_count = 1
                            continue

                        # parsing enum's content
                        if enum_flag:
                            self.__dump_info.enums[-1].variables.append(self.__parse_enum_variable(striped_line))
                            continue

                        # parsing class content
                        if class_flag:
                            if not fields_flag and not methods_flag:
                                if "// Fields" in striped_line:
                                    fields_flag = True
                                    continue
                                elif "// Methods" in striped_line:
                                    methods_flag = True
                                    skip_count = 1
                                    continue
                            if fields_flag:
                                if striped_line:
                                    self.__dump_info.classes[-1].fields.append(self.__parse_field(striped_line))
                                else:
                                    fields_flag = False
                                continue

                            if methods_flag:
                                if generic_method_flag:
                                    # checking if generic definition has ended
                                    if striped_line == "*/":
                                        generic_method_flag = False
                                        continue
                                    # skipping empty generic definition lines
                                    if striped_line == "|":
                                        continue

                                # searching for RVA and offset
                                regex_match = re.search(DumpParser.method_offset_pattern, striped_line)
                                if regex_match:
                                    if not generic_method_flag:
                                        self.__dump_info.classes[-1].methods.append(MethodInfo())
                                        self.__dump_info.classes[-1].methods[-1].rva = int(regex_match.group(1), 16)
                                        self.__dump_info.classes[-1].methods[-1].offset = int(regex_match.group(2), 16)
                                        # checking if generic methods definition started
                                        if "GenericInstMethod :" in lines[i + 2]:
                                            generic_method_flag = True
                                        method_start_flag = True
                                    else:
                                        self.__dump_info.classes[-1].methods[-1].generic_instances.append(GenericMethodInstance())
                                        self.__dump_info.classes[-1].methods[-1].generic_instances[-1].rva = int(regex_match.group(1), 16)
                                        self.__dump_info.classes[-1].methods[-1].generic_instances[-1].offset = int(regex_match.group(2), 16)
                                    continue

                                # parsing the generic method instance
                                if generic_method_flag and not method_start_flag:
                                    self.__resolve_generic_method(self.__dump_info.classes[-1], striped_line)
                                if method_start_flag:
                                    method_start_flag = False
                                    # parsing the method name, return type, params, modifiers
                                    self.__parse_method(self.__dump_info.classes[-1].methods[-1], striped_line)
                                    if generic_method_flag:
                                        skip_count = 2
                                    continue

                        # checking for a namespace (type start pattern)
                        regex_match = re.match(DumpParser.namespace_pattern, lines[i])
                        if regex_match:
                            current_namespace = regex_match.group(1)
                            parse_flag = True
                            continue

                        if parse_flag:
                            parse_flag = False

                            if "enum" in striped_line:  # parsing enum header
                                enum_flag = True
                                self.__dump_info.enums.append(self.__parse_enum_header(striped_line))
                                self.__dump_info.enums[-1].namespace = current_namespace
                                self.__dump_info.enums[-1].value_type = lines[i + 3].split(maxsplit=2)[1]
                                skip_count = 3  # skipping the enum start
                            else:  # parsing a class header
                                class_flag = True
                                self.__dump_info.classes.append(self.__parse_class_header(striped_line))
                                self.__dump_info.classes[-1].namespace = current_namespace

                                if lines[i + 1] == "{}\n":  # empty class
                                    skip_count = 2
                                else:
                                    skip_count = 1  # skipping the class start
                self.__resolve_namespaces()
                return self.__dump_info
            except FileNotFoundError as ex:
                print("File not found!")
        else:
            print("[DumpParser] file not selected")
