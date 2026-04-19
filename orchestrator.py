# orchestrator.py
from agents import PlannerAgent, CoderAgent, CriticAgent, RefactorAgent
from validator import LuaValidator
from contracts import *
import uuid
from datetime import datetime


class AgentOrchestrator:
    """Оркестратор агентской системы"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.planner = PlannerAgent(ollama_url)
        self.coder = CoderAgent(ollama_url)
        self.critic = CriticAgent(ollama_url)
        self.refactor = RefactorAgent(ollama_url)
        self.validator = LuaValidator()
        
        self.max_iterations = 3
        self.score_threshold = 90
        self.sessions: Dict[str, Dict] = {}
        self.session_id = self._new_session()

    def _log(self, emoji: str, title: str, content: str = "", indent: int = 0):
        """Форматированный вывод логов"""
        indent_str = "  " * indent
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{indent_str}[{timestamp}] {emoji} {title}")
        if content:
            for line in content.split('\n'):
                if line.strip():
                    print(f"{indent_str}    {line}")

    def _log_separator(self, char: str = "=", length: int = 60):
        """Разделитель для визуального отделения этапов"""
        print(f"\n{char * length}\n")

    def _new_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "history": [],  # [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]
            "context": TaskContext(user_request="", variables={}, constraints=[], examples=[]),
            "state": "awaiting_plan"  # awaiting_plan, awaiting_clarification, generating
        }
        return session_id

    def _clean_response(self, code: str) -> str:
        """Полная очистка ответа от мусора"""
        import re

        # 1. Извлекаем содержимое lua{...}lua
        match = re.search(r'lua\{(.*?)\}lua', code, re.DOTALL)
        if match:
            inner = match.group(1)
        else:
            inner = code

        # 2. Удаляем фразы-префиксы
        prefixes = [
            "Исправленный код:",
            "Вот исправленный код:",
            "Результат:",
            "Код:",
            "```lua",
            "```"
        ]
        for prefix in prefixes:
            inner = inner.replace(prefix, "")

        # 3. Удаляем комментарии с "Извините", "В этом исправлении"
        lines = inner.split('\n')
        cleaned_lines = []
        for line in lines:
            if any(word in line.lower() for word in ["извините", "исправлении", "добави"]):
                continue
            cleaned_lines.append(line)
        inner = '\n'.join(cleaned_lines)

        # 4. Удаляем require внешних библиотек
        inner = re.sub(r'local \w+ = require\([^\)]+\)\s*\n', '', inner)

        # 5. Удаляем незавершенные строки
        if inner.endswith('добави'):
            inner = inner[:-6].strip()

        # 6. Убираем пустые строки в начале
        inner = inner.strip()

        # 7. Оборачиваем правильно
        return f"lua{{\n{inner}\n}}lua"

    def process(self, request: GenerateRequest) -> GenerateResponse:
        """Основной цикл обработки запроса"""

        self._log_separator("=")
        self._log("🚀", "ЗАПУСК АГЕНТСКОЙ СИСТЕМЫ")
        self._log_separator("=")
        self._log("📝", "Получен запрос от пользователя", f'"{request.prompt}"')

        self.sessions[self.session_id]["context"].user_request = request.prompt
        session = self.sessions[self.session_id]
        history = session["history"]
        ctx = session["context"]
        original_prompt = request.prompt

        history.append({"role": "user", "content": original_prompt})

        # ========== ЭТАП 1: ПЛАНИРОВАНИЕ ==========
        self._log_separator("-")
        self._log("📋", "ЭТАП 1: ПЛАНИРОВАНИЕ ЗАДАЧИ")
        self._log_separator("-")

        full_context = {
            "history": history,
            "wf": {"vars": ctx.variables, "initVariables": {}}
        }

        self._log("🤖", "Вызов агента-планировщика...")
        plan = self.planner.plan(request.prompt, full_context)

        self._log("✅", "План сформирован",
                  f"Тип задачи: {plan.task_type}\n"
                  f"Сложность: {plan.complexity}\n"
                  f"Шаги: {', '.join(plan.steps[:3])}{'...' if len(plan.steps) > 3 else ''}")

        # Если есть уточняющие вопросы - возвращаем пользователю
        if plan.questions:
            self._log("❓", "Требуются уточнения", f"Вопросов: {len(plan.questions)}")
            for i, q in enumerate(plan.questions, 1):
                self._log("", f"{i}. {q}", indent=1)

            session["state"] = "awaiting_clarification"
            # Сохраняем план для следующего шага
            session["pending_plan"] = plan
            questions_text = "❓ Уточните:\n" + "\n".join(f"- {q}" for q in plan.questions)
            # Возвращаем вопросы как "код" (по спецификации)
            return GenerateResponse(code=questions_text)

        # ========== ЭТАП 2: ГЕНЕРАЦИЯ КОДА ==========
        self._log_separator("-")
        self._log("💻", "ЭТАП 2: ГЕНЕРАЦИЯ КОДА")
        self._log_separator("-")

        self._log("🤖", "Вызов агента-кодировщика...")
        code_output = self.coder.generate(plan, full_context)
        current_code = code_output.code
        current_code = self._clean_response(current_code)

        self._log("📄", "Код сгенерирован",
                  f"Размер: {len(current_code)} символов\n"
                  f"Первые 100 символов:\n{current_code[:100]}...")

        # ========== ЭТАП 3: ИТЕРАТИВНОЕ УЛУЧШЕНИЕ ==========
        self._log_separator("-")
        self._log("🔄", "ЭТАП 3: ИТЕРАТИВНОЕ УЛУЧШЕНИЕ")
        self._log_separator("-")

        best_score = 0
        best_code = current_code
        for iteration in range(self.max_iterations):
            self._log("", f"Итерация {iteration + 1}/{self.max_iterations}", indent=0)
            self._log_separator("·", 40)

            # Валидация
            self._log("🔍", "Запуск валидаторов...", indent=1)

            syntax_ok, syntax_errors = self.validator.validate_syntax_luac(current_code)
            format_errors = self.validator.validate_format(current_code)
            jsonpath_errors = self.validator.validate_jsonpath(current_code)
            array_errors = self.validator.validate_array_usage(current_code)
            var_errors = self.validator.validate_variables(current_code)
            platform_violations = self.validator.check_platform_rules(current_code)

            # Критика от агента
            self._log("🤖", "Вызов агента-критика...", indent=1)
            criticism = self.critic.critique(
                request.prompt,
                current_code,
                full_context
            )
            
            # Добавляем результаты валидации
            if format_errors:
                criticism.format_errors.extend(format_errors)
                criticism.is_valid = False

            if not syntax_ok:
                criticism.syntax_errors.extend(syntax_errors)
                criticism.is_valid = False

            if jsonpath_errors:
                criticism.jsonpath_errors.extend(jsonpath_errors)
                criticism.is_valid = False

            if array_errors:
                criticism.array_errors.extend(array_errors)
                criticism.is_valid = False

            if var_errors:
                criticism.logic_errors.extend(var_errors)
                criticism.is_valid = False

            if platform_violations:
                criticism.logic_errors.extend(platform_violations)
                criticism.is_valid = False

            total_errors = (
                    len(criticism.format_errors) +
                    len(criticism.syntax_errors) +
                    len(criticism.jsonpath_errors) +
                    len(criticism.array_errors) +
                    len(criticism.logic_errors)
            )

            # Пересчет score
            if total_errors == 0 and criticism.is_valid:
                criticism.score = min(100, criticism.score)
            else:
                criticism.score = max(0, 100 - total_errors * 5)

            self._log("📊", "Оценка качества кода",
                      f"Score: {criticism.score}/100\n"
                      f"Валиден: {'✅ Да' if criticism.is_valid else '❌ Нет'}\n"
                      f"Ошибок всего: {total_errors}", indent=1)

            if criticism.suggestions:
                self._log("💡", "Предложения по улучшению", indent=1)
                for sug in criticism.suggestions[:3]:
                    self._log("", f"• {sug}", indent=2)

            if criticism.score > best_score:
                best_score = criticism.score
                best_code = current_code
                self._log("⭐", f"Новый лучший результат: {best_score}/100", indent=1)

            # Проверяем, достаточно ли хорош код
            if criticism.score >= self.score_threshold:
                self._log("🎉", f"Код прошёл проверку! Score: {criticism.score} >= {self.score_threshold}", indent=1)
                break
            
            # Если нужны улучшения - рефакторим
            if iteration < self.max_iterations - 1:
                self._log("🔧", "Запуск рефакторинга...", indent=1)
                refactored = self.refactor.refactor(
                    current_code,
                    criticism,
                    full_context
                )
                current_code = refactored.improved_code
                current_code = self._clean_response(current_code)
                self._log("✨", f"Код улучшен (итерация {iteration + 1})", indent=1)
            else:
                self._log("⚠️", "Достигнут лимит итераций", indent=1)

        current_code = best_code

        # ========== ФИНАЛЬНЫЙ РЕЗУЛЬТАТ ==========
        self._log_separator("=")
        self._log("🏁", "ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        self._log_separator("=")

        self._log("📦", "Итоговый код", f"\n{current_code[:300]}{'...' if len(current_code) > 300 else ''}")
        self._log("📊", "Статистика",
                  f"Лучший score: {best_score}/100\n"
                  f"Размер кода: {len(current_code)} символов")
        self._log_separator("=")

        history.append({"role": "assistant", "content": current_code})
        session["history"] = history

        return GenerateResponse(code=current_code)