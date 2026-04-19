# agents.py
import json
import requests
from contracts import *
import re

class BaseAgent:
    """Базовый класс для всех агентов"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "deepseek-coder:6.7b-instruct-q4_K_M"):
        self.ollama_url = ollama_url
        self.model = model

    def _chat(self, messages: List[Dict], temperature: float = 0.1) -> str:
        """Вызов Ollama API с полной историей сообщений"""
        response = requests.post(
            f"{self.ollama_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": 4096,
                    "num_predict": 256
                }
            },
            timeout=120
        )
        return response.json()["message"]["content"]

    def _call_llm(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Упрощённый вызов без истории (для обратной совместимости)"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        return self._chat(messages, temperature)
    
    def _parse_json_response(self, response: str) -> Dict:
        """Извлечение JSON из ответа LLM"""
        # Ищем JSON в ответе
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        return {}

    def _clean_code(self, code: str) -> str:
        """Улучшенная очистка кода"""
        import re

        # 1. Удаляем "Измененный код:", "Исправленный код:" и т.д.
        prefixes = [
            "Измененный код:",
            "Исправленный код:",
            "Вот код:",
            "Результат:",
            "Код:",
            "```lua",
            "```",
            "lua{",
            "}lua"
        ]

        for prefix in prefixes:
            code = code.replace(prefix, "")

        # 2. Извлекаем содержимое между lua{ и }lua
        match = re.search(r'lua\{(.*?)\}lua', code, re.DOTALL)
        if match:
            code = match.group(1).strip()

        # 3. Удаляем незавершенные строки (обрезанные)
        lines = code.split('\n')
        cleaned_lines = []
        for line in lines:
            # Пропускаем строки с признаками обрезания
            if line.strip().endswith(("'%d", "('%d", "= '(%d", "('%d\n")):
                continue
            # Пропускаем пустые do/end блоки
            if line.strip() in ["do", "end"] and not cleaned_lines:
                continue
            cleaned_lines.append(line)

        code = '\n'.join(cleaned_lines)

        # 4. Если код все еще содержит "Измененный код:" - обрезаем
        if "Измененный код:" in code:
            code = code.split("Измененный код:")[-1]

        # 5. Удаляем markdown
        code = code.replace("```lua", "").replace("```", "")

        # 6. Оборачиваем правильно
        code = code.strip()
        if not code.startswith("lua{"):
            code = f"lua{{\n{code}\n}}lua"

        return code

class PlannerAgent(BaseAgent):
    """Агент-планировщик: анализирует задачу и строит план"""
    
    SYSTEM_PROMPT = """Ты - планировщик для генерации Lua-кода в LowCode платформе MWS Octapi.

Твоя задача: проанализировать запрос пользователя и создать план решения.

ОГРАНИЧЕНИЯ ПЛАТФОРМЫ:
- Версия Lua: 5.5
- Формат скрипта: lua{ код }lua (JSON-строка)
- НЕЛЬЗЯ использовать JsonPath ($.variables) - только прямое обращение
- Переменные хранятся в wf.vars (объявленные в схеме)
- Входные переменные: wf.initVariables (полученные при запуске)
- Массивы: _utils.array.new() - создать новый массив
- Массивы: _utils.array.markAsArray(arr) - объявить существующую переменную массивом
- Поддерживаемые типы: nil, boolean, number, string, array, table, function
- Поддерживаемые конструкции: if/then/else, while, for, repeat/until

Выдай ответ СТРОГО в JSON формате:
{
    "task_type": "array_operation|data_transform|validation|calculation|string_processing|time_conversion",
    "complexity": "simple|medium|complex",
    "steps": ["шаг 1", "шаг 2", ...],
    "required_variables": ["var1", "var2", ...],
    "input_variables": ["переменные из wf.vars"],
    "init_variables": ["переменные из wf.initVariables"],
    "needs_array_utils": true/false,
    "questions": ["уточняющий вопрос 1", "уточняющий вопрос 2", ...], // если нужны уточнения
    "plan": "детальный план на русском"
}

Если информации недостаточно - задай уточняющие вопросы в поле questions."""

    def plan(self, task: str, context: Optional[Dict] = None) -> PlannerOutput:

        user_prompt = f"Задача: {task}\n\nКонтекст:{json.dumps(context, ensure_ascii=False)}"
        response = self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        data = self._parse_json_response(response)
        
        return PlannerOutput(
            task_type=data.get("task_type", "unknown"),
            complexity=data.get("complexity", "medium"),
            steps=data.get("steps", []),
            required_variables=data.get("required_variables", []),
            input_variables=data.get("input_variables", []),
            init_variables=data.get("init_variables", []),
            questions=data.get("questions", []),
            plan=data.get("plan", response)
        )

class CoderAgent(BaseAgent):
    """Агент-кодировщик: генерирует Lua-код по плану"""
    
    SYSTEM_PROMPT = """Ты - эксперт по Lua 5.5 для MWS Octapi LowCode платформы.

КРИТИЧЕСКИ ВАЖНО - ФОРМАТ ОТВЕТА:
Ответ должен быть СТРОГО в формате lua{ код }lua
НЕ ИСПОЛЬЗУЙ markdown!
НЕ ИСПОЛЬЗУЙ ```lua!
НЕ ДОБАВЛЯЙ комментарии перед кодом!

ПРАВИЛЬНЫЙ ФОРМАТ:
lua{
local x = wf.vars.value
return x + 1
}lua

НЕПРАВИЛЬНЫЙ ФОРМАТ:
```lua
local x = wf.vars.value
return x + 1

СТРОГИЕ ПРАВИЛА (НАРУШЕНИЯ НЕДОПУСТИМЫ):
1. Формат ответа ТОЛЬКО: {"result": "lua{ код }lua"}
2. НИКАКОГО JsonPath! Не используй $.variables - только прямое обращение
3. Переменные скрипта: wf.vars (объявленные в схеме)
4. Входные переменные: wf.initVariables (при запуске)
5. Для создания массива: _utils.array.new()
6. Для пометки переменной массивом: _utils.array.markAsArray(arr)
7. Доступ к элементам массива: arr[index] (индексация с 1)
8. Длина массива: #arr

Разрешённые конструкции:
- if/then/else/elseif
- while/do/end
- for/do/end (числовой и обобщённый)
- repeat/until
- function/end

Базовые типы: nil, boolean, number, string, table

Примеры:
- Последний элемент массива: return wf.vars.emails[#wf.vars.emails]
- Увеличение счётчика: return wf.vars.try_count_n + 1
- Фильтрация массива: 
  local result = _utils.array.new()
  for _, item in ipairs(wf.vars.data) do
      if condition then table.insert(result, item) end
  end
  return result

Ответ должен быть ТОЛЬКО валидным JSON с полем "result"."""
    
    def generate(self, plan: PlannerOutput, context: Dict) -> CoderOutput:
        user_prompt = f"""План: {plan.plan}
Шаги: {json.dumps(plan.steps, ensure_ascii=False)}
Контекст: {json.dumps(context, ensure_ascii=False)}

Сгенерируй Lua-код, который решает эту задачу."""
        
        response = self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        data = self._parse_json_response(response)
        
        code = data.get("result", response)
        
        # Очистка и форматирование
        code = self._clean_code(code)
        
        return CoderOutput(
            code=code,
            explanation=data.get("explanation", ""),
            assumptions=data.get("assumptions", [])
        )


class CriticAgent(BaseAgent):
    """Агент-критик: проверяет и оценивает код"""
    
    SYSTEM_PROMPT = """Ты - критик Lua-кода для MWS Octapi платформы.

Проверь код на соответствие правилам:

1. Формат: должен быть обёрнут в lua{ ... }lua
2. Отсутствие JsonPath (запрещены конструкции вида $.vars)
3. Использование только wf.vars и wf.initVariables
4. Правильная работа с массивами (_utils.array.new / markAsArray)
5. Синтаксическая корректность Lua 5.5
6. Соответствие задаче

Выдай ответ СТРОГО в JSON:
{
    "is_valid": true/false,
    "format_errors": ["ошибка формата 1", ...],
    "syntax_errors": ["синтаксическая ошибка 1", ...],
    "jsonpath_errors": ["найден JsonPath: ...", ...],
    "array_errors": ["ошибка работы с массивами", ...],
    "logic_errors": ["логическая ошибка 1", ...],
    "suggestions": ["предложение 1", ...],
    "score": 0-100
}"""
    
    def critique(self, task: str, code: str, context: Dict) -> CriticOutput:
        user_prompt = f"""Задача: {task}
Код: {code}
Контекст: {json.dumps(context, ensure_ascii=False)}"""
        
        response = self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        data = self._parse_json_response(response)
        
        return CriticOutput(
            is_valid=data.get("is_valid", False),
            format_errors=data.get("format_errors", []),
            syntax_errors=data.get("syntax_errors", []),
            jsonpath_errors=data.get("jsonpath_errors", []),
            array_errors=data.get("array_errors", []),
            logic_errors=data.get("logic_errors", []),
            suggestions=data.get("suggestions", []),
            score=data.get("score", 0)
        )

class RefactorAgent(BaseAgent):
    """Агент-рефактор: улучшает код на основе критики"""
    
    SYSTEM_PROMPT = """Ты - рефактор Lua-кода для MWS Octapi LowCode платформы.

Исправь код на основе замечаний критика, строго соблюдая правила:
- Формат: lua{ код }lua
- Нет JsonPath ($.variables)
- Только wf.vars / wf.initVariables
- Правильная работа с массивами

Верни ТОЛЬКО исправленный код в формате:
{"result": "lua{ исправленный код }lua"}"""
    
    def refactor(self, original_code: str, criticism: CriticOutput, context: Dict) -> RefactorOutput:
        issues = (
            criticism.format_errors +
            criticism.syntax_errors +
            criticism.jsonpath_errors +
            criticism.array_errors +
            criticism.logic_errors
        )
        
        user_prompt = f"""Оригинальный код: {original_code}
Замечания: {json.dumps(issues, ensure_ascii=False)}
Предложения: {json.dumps(criticism.suggestions, ensure_ascii=False)}
Контекст: {json.dumps(context, ensure_ascii=False)}

Выдай исправленный код."""
        
        response = self._call_llm(self.SYSTEM_PROMPT, user_prompt)
        data = self._parse_json_response(response)

        return RefactorOutput(
            improved_code=self._clean_code(data.get("result", response)),
            changes_made=data.get("changes_made", ["Исправлены замечания"]),
            new_score=criticism.score + 10  # Предполагаем улучшение
        )