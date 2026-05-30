import re


_CPP_KEYWORDS = frozenset({
    "alignas", "alignof", "and", "and_eq", "asm", "auto", "bitand", "bitor",
    "bool", "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t",
    "class", "compl", "concept", "const", "consteval", "constexpr", "constinit",
    "const_cast", "continue", "co_await", "co_return", "co_yield", "decltype",
    "default", "delete", "do", "double", "dynamic_cast", "else", "enum",
    "explicit", "export", "extern", "false", "float", "for", "friend", "goto",
    "if", "inline", "int", "long", "mutable", "namespace", "new", "noexcept",
    "not", "not_eq", "nullptr", "operator", "or", "or_eq", "private", "protected",
    "public", "register", "reinterpret_cast", "requires", "return", "short",
    "signed", "sizeof", "static", "static_assert", "static_cast", "struct",
    "switch", "template", "this", "thread_local", "throw", "true", "try",
    "typedef", "typeid", "typename", "union", "unsigned", "using", "virtual",
    "void", "volatile", "wchar_t", "while", "xor", "xor_eq",
    "stdin", "stdout", "stderr", "_int32"
})


def generic_split(line: str, sep: str | None = None) -> list[str]:
    if '>' not in line and "[" not in line:
        return line.split(sep)
    result = []
    generic_level = 0
    word = ""
    parts = line.split(sep)
    for part in parts:
        word += part
        generic_level += part.count("<")
        generic_level -= part.count(">")
        if generic_level == 0:
            result.append(word)
            word = ""
        else:
            if sep:
                word += sep
            elif sep is None:
                word += " "
    return result


def generic_type_split(line: str, sep: str | None = None) -> list[str]:
    if '>' not in line and "[" not in line:
        return line.split(sep)
    result = []
    generic_level = 0
    array_level = 0
    word = ""
    parts = line.split(sep)
    for part in parts:
        word += part
        generic_level += part.count("<")
        generic_level -= part.count(">")
        array_level += part.count("[")
        array_level -= part.count("]")
        if generic_level == 0 and array_level == 0:
            result.append(word)
            word = ""
        else:
            if sep:
                word += sep
            elif sep is None:
                word += " "
    return result


def generic_quotes_type_split(line: str, sep: str | None = None) -> list[str]:
    if '>' not in line and "[" not in line and '"' not in line:
        return line.split(sep)
    result = []
    generic_level = 0
    array_level = 0
    quotes_count = 0
    word = ""
    parts = line.split(sep)
    for part in parts:
        word += part
        generic_level += part.count("<")
        generic_level -= part.count(">")
        array_level += part.count("[")
        array_level -= part.count("]")
        quotes_count += part.count("\"")
        if generic_level == 0 and array_level == 0 and quotes_count % 2 == 0:
            result.append(word)
            word = ""
        else:
            if sep:
                word += sep
            elif sep is None:
                word += " "
    return result


def parse_generic_params(s: str) -> str:
    if not s:
        return ""
    s = s[s.find(">") + 1:] if s.startswith("<") else s
    generic_depth = 0
    i = len(s)

    while True:
        lt = s.rfind("<", 0, i)
        if lt == -1:
            return ""
        segment = s[lt:i]
        generic_depth += segment.count(">") - 1

        if generic_depth == 0:
            if lt > 0 and s[lt - 1] == ".":
                return ""
            return s[lt:]
        i = lt


def match_string(search_str: str | None, target_str: str, exact: bool = True, regex: bool = False, case_sensitive: bool = True) -> bool:
    if search_str is None:
        return True
    if regex:
        return bool(
            re.fullmatch(search_str, target_str, 0 if case_sensitive else re.IGNORECASE) if exact else re.search(search_str, target_str, 0 if case_sensitive else re.IGNORECASE)
        )
    else:
        return (search_str if case_sensitive else search_str.lower()) == (target_str if case_sensitive else target_str.lower()) if exact else (search_str if case_sensitive else search_str.lower()) in (target_str if case_sensitive else target_str.lower())

def is_compiler_generated(name: str):
    if len(name) > 2:
        if "__" in name[2:]:
            return True
        return name.startswith("<") or "<>" in name
    return False

def safe_cpp_name(name: str) -> str:
    name = name.replace("-", "_")
    return f"{name}_" if name in _CPP_KEYWORDS else name
