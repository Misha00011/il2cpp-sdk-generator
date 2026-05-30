# IL2CPP Dump Parser & SDK Generator

Инструмент для парсинга `dump.cs` файлов, генерируемых [Il2CppDumper](https://github.com/Perfare/Il2CppDumper), с возможностью поиска по типам и генерации SDK для работы с памятью процесса.

## Возможности

- Парсинг классов, структур, интерфейсов, перечислений и их членов из `dump.cs`
- Поиск и фильтрация типов по имени, namespace, модификаторам, полям, методам, родительским типам
- Поддержка generic-типов, generic-инстансов классов и методов
- Генерация SDK в нескольких форматах:

| Формат | Описание |
|---|---|
| `CSharpConfig` | Воспроизведение оригинального `dump.cs` |
| `CppOffsetsConfig` | Один файл `offsets.h` — смещения полей и RVA методов |
| `CppShortConfig` | Три файла: `offsets.h`, `enums.h`, `methods.h` с указателями на функции |

> **Примечание:** полный C++ SDK (`CppFull`) с генерацией структур и классов находится в разработке.

## Установка

Требования: Python 3.10+, сторонних зависимостей нет.

```bash
git clone https://github.com/username/il2cpp-dump-parser
cd il2cpp-dump-parser
```

## Использование

### Парсинг дампа

```python
from dump_parser import DumpParser

dump = DumpParser().parse_dump("dump.cs")
```

### Поиск типов

```python
from search_manager import DumpSearcher, ClassFilter, EnumFilter, MethodFilter

searcher = DumpSearcher(dump)

# найти класс по имени
cls = searcher.find_class(ClassFilter(name="PlayerController"))

# найти все классы в namespace с методом Update
results = searcher.find_classes(
    ClassFilter(
        namespace="Game.Player",
        has_methods=[MethodFilter(name="Update")]
    )
)
```

### Генерация SDK

```python
from sdk_manager import SDKManager, CppShortConfig

# выбрать нужные типы
searcher.select_classes(ClassFilter(namespace="Game.Player"))
searcher.select_enums()

# сгенерировать SDK
SDKManager(searcher.get_dump_info()).save_sdk(CppShortConfig(), "output/")
```

Результат в `output/`:

```cpp
// offsets.h
namespace offsets
{
    namespace Game
    {
        namespace Player
        {
            namespace PlayerController
            {
                namespace Fields
                {
                    constexpr ptrdiff_t _health = 0x40;
                }
            }
        }
    }
}

// methods.h
namespace sdk
{
    namespace Game
    {
        namespace Player
        {
            namespace PlayerController
            {
                namespace Methods
                {
                    inline void (*TakeDamage)(void* __this, float amount);
                }
            }
        }
    }

    inline void init(uintptr_t base)
    {
        Game::Player::PlayerController::Methods::TakeDamage =
            reinterpret_cast<void(*)(void*, float)>(base + 0x58A8248);
    }
}
```

## Структура проекта

```
dump_parser.py      — парсинг dump.cs
dump_types.py       — типы данных (ClassInfo, MethodInfo, FieldInfo, ...)
search_manager.py   — поиск и фильтрация, DumpSearcher / ClassSearcher
sdk_manager.py      — генерация SDK
string_utils.py     — вспомогательные утилиты
```

## Планы

- [ ] Полный C++ SDK (`CppFull`) — генерация структур с полями
- [ ] Маппинг reference-типов вместо `void*`

## Лицензия

MIT
