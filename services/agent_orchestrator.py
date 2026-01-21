import logging
import time
import re
import json
from typing import Dict, Any, List, Optional, Generator, Tuple
import requests
import sqlglot
from sqlglot import expressions as exp
from services.ai_service import get_llm
from services.sql_service import transpile_to_tsql, inject_safety_top, validate_tsql
from services.db_service import get_db_connection, safe_execute_sql
from services.tribal_knowledge_engine import TribalKnowledgeEngine
from services.config_service import get_settings
from services.planner_agent_v2 import PlannerAgentV2, load_semantic_model, load_tribal_rules
from services.sql_compiler import SQLCompiler
from services.semantic_validator import SemanticValidator

logger = logging.getLogger("AskLytics-Agent")

class ReflectionOrchestrator:
    """Agentic orchestrator with self-healing reflection loop."""
    
    def __init__(self, max_attempts: int = 3):
        self.max_attempts = max_attempts
        self.tribal = TribalKnowledgeEngine()
        self.semantic_model = load_semantic_model()
        self.tribal_rules = load_tribal_rules()
        self.planner = PlannerAgentV2(self.semantic_model, self.tribal_rules)
        self.compiler = SQLCompiler(self.semantic_model)
        self.validator = SemanticValidator(self.semantic_model, self.tribal_rules)
        self.fk_cache: Dict[str, List[Tuple[str, str]]] = {}

    @staticmethod
    def _unwrap_sql(text: str) -> str:
        """Extract SQL from markdown/code fences and strip leading markers like `sql`."""
        if not text:
            return text
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m:
            text = m.group(1)
        # Remove leading markdown-ish markers
        text = re.sub(r"^\[?\s*sql\]?\s*", "", text.strip(), flags=re.IGNORECASE)
        # Drop any leading '[' leftovers before the first SELECT
        m2 = re.search(r"(?is)(select\b.*)", text)
        if m2:
            return m2.group(1).strip()
        return text.strip()

    def generate_sql_with_reflection(self, question: str, context: str) -> Generator[Dict[str, Any], None, None]:
        """Generate SQL, execute, and reflect on errors to self-heal."""
        
        settings = get_settings()
        inference_mode = (settings.app.inference or "gemini").lower()
        temperature = float(settings.app.temperature or 0.1)
        attempt = 1
        last_error = None
        full_sql = None
        
        while attempt <= self.max_attempts:
            yield {"event": "attempt", "data": {"number": attempt, "max": self.max_attempts}}
            
            # Step 1: Planner builds structured plan/prompt
            plan_prompt, fk_hints = self._build_plan(question, context, last_error, full_sql)
            
            # Step 2: Call chosen model (Gemini or local)
            raw_text = ""
            try:
                yield {"event": "thinking", "data": {"message": "Analyzing schema and generating SQL..."}}
                if inference_mode == "gemini":
                    raw_text = self._generate_with_gemini(plan_prompt, temperature)
                else:
                    llm = get_llm()
                    if not llm:
                        yield {"event": "error", "data": {"message": "Local LLM not initialized"}}
                        return
                    response = llm(plan_prompt, max_tokens=1024, temperature=temperature)
                    raw_text = response["choices"][0]["text"]
            except Exception as gen_err:
                logger.warning(f"Generation failed on attempt {attempt}: {gen_err}")
                last_error = str(gen_err)
                attempt += 1
                yield {"event": "reflection", "data": {"error": last_error, "retry": attempt <= self.max_attempts}}
                continue
            
            # Extract SQL (heuristic) with fence unwrapping or compile plan if empty
            clean_raw = self._unwrap_sql(raw_text)
            candidate = re.search(r"(?is)SELECT\b.*", clean_raw)
            generated_sql = (candidate.group(0) if candidate else clean_raw).strip().rstrip(";")
            if not generated_sql:
                # Try planner + compiler path
                logical_plan = self.planner.plan(question)
                generated_sql = self.compiler.compile(logical_plan)
            
            try:
                # Step 3: Critic validates; Corrector repairs; enforce safety
                full_sql = self._critic_and_correct(generated_sql, plan_prompt, fk_hints, inference_mode, last_error)
            except Exception as prep_err:
                logger.warning(f"SQL preparation failed on attempt {attempt}: {prep_err}")
                last_error = str(prep_err)
                attempt += 1
                yield {"event": "reflection", "data": {"error": last_error, "retry": attempt <= self.max_attempts}}
                continue
            
            yield {"event": "sql_complete", "data": {"query": full_sql}}
            
            # Step 4: Validate and Execute
            try:
                yield {"event": "executing", "data": {"message": "Validating and executing..."}}
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    columns, rows, exec_ms = safe_execute_sql(cursor, full_sql)
                
                # Success!
                yield {"event": "result", "data": {"columns": columns, "data": rows, "exec_ms": exec_ms}}
                
                # Yield summary for frontend
                summary_text = f"Successfully retrieved {len(rows)} rows from the database using a generated SQL query."
                yield {"event": "summary", "data": {"text": summary_text}}
                
                yield {"event": "done", "data": {"message": "Success after {} attempts".format(attempt)}}
                return
                
            except Exception as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                last_error = str(e)
                attempt += 1
                yield {"event": "reflection", "data": {"error": last_error, "retry": attempt <= self.max_attempts}}
                
        yield {"event": "error", "data": {"message": f"Failed to generate valid SQL after {self.max_attempts} attempts. Last error: {last_error}"}}

    def _build_plan(self, question: str, context: str, error: Optional[str], last_sql: Optional[str]) -> Tuple[str, str]:
        tribal_context = self.tribal.get_rules_context()
        fk_hints = self._extract_fk_hints(context)
        join_hints = ""
        if fk_hints:
            join_hints = "\n### RELATIONSHIPS (FK->PK)\n" + "\n".join(f"- {fk}" for fk in fk_hints)

        base = (
            "You are a Planner + SQL Specialist for Microsoft SQL Server.\n"
            "Generate a single, valid T-SQL SELECT statement only.\n"
            "- Identifiers must be [schema].[table] and [column]; no backticks/double quotes.\n"
            "- Prefer INNER JOIN using FK->PK edges when spanning tables.\n"
            "- Use SELECT TOP (N) not LIMIT; avoid non-T-SQL syntax.\n\n"
            f"{tribal_context}"
            f"{join_hints}\n"
            f"Context:\n{context}\n\n"
            f"Question:\n{question}\n\n"
        )

        if error:
            base += (
                f"### REFLECTION\n"
                f"The previous SQL failed with this error: {error}\n"
                f"Previous SQL: {last_sql}\n\n"
                "Analyze the error and provide a corrected T-SQL statement.\n"
            )

        base += "SQL Server Query:"
        return base, join_hints

    def _generate_with_gemini(self, prompt: str, temperature: float) -> str:
        settings = get_settings()
        api_key = settings.gemini.api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        base_url = (settings.gemini.base_url or "https://generativelanguage.googleapis.com/v1beta/models").rstrip("/")
        model = settings.gemini.model or "gemini-2.0-flash"
        url = f"{base_url}/{model}:generateContent?key={api_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}
        }

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            raise RuntimeError(f"Gemini response parsing failed: {e}")

    def _repair_with_gemini(self, prompt: str, broken_sql: str, error: Optional[str]) -> str:
        """Ask Gemini to repair non-T-SQL or invalid SQL into valid T-SQL."""
        settings = get_settings()
        api_key = settings.gemini.api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        base_url = (settings.gemini.base_url or "https://generativelanguage.googleapis.com/v1beta/models").rstrip("/")
        model = settings.gemini.model or "gemini-2.0-flash"
        url = f"{base_url}/{model}:generateContent?key={api_key}"

        repair_prompt = (
            "You are a SQL Server T-SQL fixer. Convert the provided SQL into valid T-SQL, "
            "using [schema].[table] and [column] identifiers (no backticks or double-quotes). "
            "Keep the intent identical.\n\n"
            f"Original question:\n{prompt}\n\n"
            f"Broken SQL:\n{broken_sql}\n\n"
            f"Previous error: {error or 'Invalid dialect/parse'}\n"
            "Return only the corrected T-SQL statement."
        )

        payload = {
            "contents": [{"parts": [{"text": repair_prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }

        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            raise RuntimeError(f"Gemini repair response parsing failed: {e}")

    def _extract_fk_hints(self, context: str) -> List[str]:
        hints = []
        try:
            for line in context.splitlines():
                if "->" in line and "FK" in line.upper():
                    hints.append(line.strip())
        except Exception:
            pass
        return hints

    def _critic_and_correct(self, generated_sql: str, plan_prompt: str, fk_hints: str, inference_mode: str, last_error: Optional[str]) -> str:
        """Validate/repair SQL then inject safety."""
        full_sql = transpile_to_tsql(generated_sql)
        # Critic: basic sqlglot parse plus semantic validator
        valid = validate_tsql(full_sql) and self.validator.validate(full_sql)
        if (not valid or "`" in full_sql) and inference_mode == "gemini":
            try:
                repaired_sql = self._repair_with_gemini(plan_prompt, generated_sql, last_error)
                full_sql = transpile_to_tsql(repaired_sql, read_dialect="mysql")
            except Exception as repair_err:
                logger.warning(f"Gemini repair failed: {repair_err}")

        full_sql = inject_safety_top(full_sql)
        return full_sql
