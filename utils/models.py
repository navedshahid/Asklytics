# utils/models.py
import os, re

class ModelProfiles:
    FAST = "fast"
    BALANCED = "balanced"
    ACCURATE = "accurate"

class ModelRunner:
    """
    Llama.cpp-backed runner for SQLCoder GGUF.
    Config via env:
      QP_MODEL_PATH : ./models/sqlcoder-7b-2.q8_0.gguf
      QP_MODEL_CTX  : 4096
      QP_MODEL_NGPU : -1 (GPU) or 0 (CPU)
    """
    def __init__(self, profile: str = ModelProfiles.BALANCED):
        self.profile = profile
        self._llm = None
        self._init_llm()

    def set_profile(self, profile: str):
        self.profile = profile

    def _init_llm(self):
        path = os.environ.get("QP_MODEL_PATH")
        if not path or not os.path.exists(path):
            print("[ModelRunner] QP_MODEL_PATH not set or file missing:", path)
            self._llm = None
            return
        try:
            from llama_cpp import Llama
            n_ctx = int(os.environ.get("QP_MODEL_CTX", "4096"))
            n_gpu = int(os.environ.get("QP_MODEL_NGPU", "-1"))
            self._llm = Llama(
                model_path=path,
                n_ctx=n_ctx,
                n_threads=max(2, os.cpu_count() or 4),
                n_gpu_layers=n_gpu,    # -1 => all GPU layers if CUDA build
                logits_all=False,
                verbose=False,
            )
            print(f"[ModelRunner] Loaded {os.path.basename(path)} (ctx={n_ctx}, gpu_layers={n_gpu})")
        except Exception as ex:
            print("[ModelRunner] llama-cpp init failed:", ex)
            self._llm = None

def _clean_sql_text(self, text: str) -> str:
    t = text.strip()

    # strip code fences / labels
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = t.replace("```", "").strip()
    t = re.sub(r"^(sql\s*:|t-sql\s*:)\s*", "", t, flags=re.I)

    # remove surrounding quotes if the whole thing is quoted
    if (t.startswith("'") and t.endswith("'")) or (t.startswith('"') and t.endswith('"')):
        t = t[1:-1].strip()

    # unwrap: SELECT '...';
    m = re.match(r"^\s*select\s+N?'(.*)'\s*;?\s*$", t, flags=re.I | re.S)
    if m:
        inner = m.group(1).replace("''", "'").strip()
        # if it looks like actual SQL, use the inner
        if re.search(r"\bselect\b.+\bfrom\b", inner, flags=re.I | re.S):
            t = inner

    # collapse accidental “SQL:” prefixes inside the text
    t = re.sub(r"^(sql\s*:|t-sql\s*:)\s*", "", t, flags=re.I)

    # single statement; ensure trailing semicolon
    t = t.strip().rstrip(";")
    return t + ";"
    # Conservative fallback if model missing
    def _stub(self, prompt: str) -> str:
        m_table = re.search(r"- ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", prompt)
        m_col = re.search(r"\.([A-Za-z0-9_]+) \(", prompt)
        table = m_table.group(1) if m_table else "sys.objects"
        col = m_col.group(1) if m_col else "name"
        return f"SELECT TOP 50 {col} FROM {table};"

    def generate_sql(self, prompt: str) -> str:
        if self._llm is None:
            return self._stub(prompt)
        system = ("You are SQLCoder tuned for Microsoft SQL Server T-SQL. "
                  "Use only listed tables/columns. Output ONE T-SQL SELECT statement. "
                  "Do NOT wrap it in quotes or code fences. No explanations.")
        text = f"<|system|>\n{system}\n<|user|>\n{prompt}\n<|assistant|>"
        out = self._llm(
            prompt=text,
            max_tokens=512,
            temperature=0.05,   # sqlcoder likes low temp
            top_p=0.9,
            repeat_penalty=1.1,
            stop=["<|user|>", "<|system|>", "```"],
        )
        sql = out["choices"][0]["text"].strip()
        # Strip accidental fences or labels
        sql = re.sub(r"^```(\w+)?", "", sql).replace("```", "").strip()
        # Ensure one statement without trailing chatter
        sql = sql.split("\nGO")[0].strip()
        return sql