# validator.py
import subprocess
import tempfile
import os
import re
from typing import List, Tuple

class LuaValidator:
    """Валидатор Lua-кода"""
    
    def __init__(self):
        self.lua_executable = "lua5.5"  # или "lua"
    
    def extract_code(self, wrapped_code: str) -> str:
        """Извлечение кода из lua{}lua"""
        match = re.search(r'lua\{(.*?)\}lua', wrapped_code, re.DOTALL)
        if match:
            return match.group(1).strip()
        return wrapped_code

    def validate_format(self, code: str) -> List[str]:
        """Проверка формата обёртки"""
        errors = []
        if not (code.strip().startswith('lua{') and code.strip().endswith('}lua')):
            errors.append("Код должен быть обёрнут в lua{ ... }lua")
        return errors

    def validate_jsonpath(self, code: str) -> List[str]:
        """Проверка отсутствия JsonPath"""
        errors = []
        clean_code = self.extract_code(code)

        forbidden_patterns = [
            (r'\$\.[a-zA-Z_][a-zA-Z0-9_]*', "JsonPath (например, $.variables)"),
            (r'JsonPath', "JsonPath (текст)"),
            (r'getVariable', "getVariable (запрещён)"),
            (r'setVariable', "setVariable (запрещён)"),
        ]

        for pattern, description in forbidden_patterns:
            matches = re.findall(pattern, clean_code)
            if matches:
                errors.append(f"Запрещён {description}: {matches[:3]}")

        return errors

    def validate_array_usage(self, code: str) -> List[str]:
        """Проверка работы с массивами"""
        errors = []
        clean_code = self.extract_code(code)

        # Проверка создания массивов
        if '_utils.array.new()' not in clean_code:
            # Не обязательно, но если используется массив, должна быть эта функция
            if 'table.insert' in clean_code and '_utils.array.new()' not in clean_code:
                errors.append("При использовании table.insert рекомендуется _utils.array.new() для создания массива")

        # Проверка пометки массивов
        if 'markAsArray' in clean_code and '_utils.array.markAsArray' not in clean_code:
            errors.append("Используйте _utils.array.markAsArray() для пометки существующей переменной массивом")

        # Проверка ipairs (индексация с 1)
        if 'ipairs' in clean_code:
            # ipairs это нормально, индексация в Lua с 1
            pass

        return errors

    def validate_variables(self, code: str) -> List[str]:
        """Проверка использования переменных платформы"""
        errors = []
        clean_code = self.extract_code(code)

        # Должны использоваться wf.vars или wf.initVariables
        has_wf_vars = 'wf.vars' in clean_code or 'wf.initVariables' in clean_code
        if not has_wf_vars:
            errors.append("Код должен использовать wf.vars или wf.initVariables")

        return errors

    def validate_syntax_luac(self, code: str) -> Tuple[bool, List[str]]:
        """Проверка синтаксиса через luac"""
        clean_code = self.extract_code(code)
        errors = []

        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False) as f:
            f.write(clean_code)
            temp_file = f.name

        try:
            result = subprocess.run(
                ['luac', '-p', temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                # Парсим ошибки luac
                for line in result.stderr.split('\n'):
                    if line.strip():
                        errors.append(line.strip())

            return result.returncode == 0, errors

        except subprocess.TimeoutExpired:
            return False, ["Таймаут проверки синтаксиса"]
        except FileNotFoundError:
            return self._basic_syntax_validation(clean_code)
        finally:
            os.unlink(temp_file)

    def _basic_syntax_validation(self, code: str) -> Tuple[bool, List[str]]:
        """Базовая проверка синтаксиса без luac"""
        errors = []

        # Проверка баланса скобок
        brackets = [
            ('(', ')', 'круглые'),
            ('{', '}', 'фигурные'),
            ('[', ']', 'квадратные'),
        ]
        for open_b, close_b, name in brackets:
            if code.count(open_b) != code.count(close_b):
                errors.append(f"Несбалансированные {name} скобки")

        # Проверка ключевых конструкций
        if 'if' in code and 'end' not in code:
            errors.append("Возможно отсутствует 'end' для 'if'")
        if 'for' in code and 'end' not in code:
            errors.append("Возможно отсутствует 'end' для 'for'")
        if 'while' in code and 'end' not in code:
            errors.append("Возможно отсутствует 'end' для 'while'")
        if 'function' in code and 'end' not in code:
            errors.append("Возможно отсутствует 'end' для 'function'")

        return len(errors) == 0, errors
    
    def check_platform_rules(self, code: str) -> List[str]:
        """Проверка правил платформы MWS Octapi"""
        clean_code = self.extract_code(code)
        violations = []
        
        # Проверка формата
        if not (code.strip().startswith('lua{') and code.strip().endswith('}lua')):
            violations.append("Код должен быть обернут в lua{}lua")
        
        # Проверка запрещенных паттернов
        forbidden = ['$.', 'JsonPath', 'getVariable', 'setVariable']
        for pattern in forbidden:
            if pattern in clean_code:
                violations.append(f"Запрещенный паттерн: {pattern}")
        
        # Проверка использования wf.vars
        if 'wf.vars' not in clean_code and 'wf.initVariables' not in clean_code:
            violations.append("Не используются переменные платформы")
        
        return violations