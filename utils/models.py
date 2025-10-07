# utils/models.py  (drop-in)
import os, re

class ModelProfiles:
    FAST="fast"; BALANCED="balanced"; ACCURATE="accurate"

class ModelRunner:
    def __init__(self, profile: str = ModelProfiles.BALANCED):
        self.profile = profile
        self._llm = None
        self._init_llm()

    def set_profile(self, profile: str): self.profile = profile

    def _init_llm(self):
        path = os.environ.get("QP_MODEL_PATH")
        if not path or not os.path.exists(path):
            print("[ModelRunner] QP_MODEL_PATH not set or file missing:", path)
            self._llm = None; return
        try:
            from llama_cpp import Llama
            n_ctx = int(os.environ.get("QP_MODEL_CTX","4096"))
            n_gpu = int(os.environ.get("QP_MODEL_NGPU","-1"))
            n_batch = int(os.environ.get("QP_MODEL_NBATCH","512"))
            self._llm = Llama(model_path=path, n_ctx=n_ctx, n_gpu_layers=n_gpu,
                              n_threads=max(2, os.cpu_count() or 4),
                              n_batch=n_batch, logits_all=False, verbose=False)
            print(f"[ModelRunner] Loaded {os.path.basename(path)} (ctx={n_ctx}, gpu_layers={n_gpu})")
        except Exception as ex:
            print("[ModelRunner] llama-cpp init failed:", ex); self._llm=None

    def _clean_sql_text(self, text: str) -> str:
        t = (text or "").strip()
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t).replace("```","").strip()
        t = re.sub(r"^(sql\s*:|t-sql\s*:)\s*", "", t, flags=re.I)
        if (t.startswith("'") and t.endswith("'")) or (t.startswith('"') and t.endswith('"')):
            t = t[1:-1].strip()
        m = re.match(r"^\s*select\s+N?'(.*)'\s*;?\s*$", t, flags=re.I|re.S)
        if m:
            inner = m.group(1).replace("''","'").strip()
            if re.search(r"\bselect\b.+\bfrom\b", inner, flags=re.I|re.S):
                t = inner
        t = re.sub(r"^(sql\s*:|t-sql\s*:)\s*", "", t, flags=re.I).strip().rstrip(";")
        return t + ";"

    def _stub(self, prompt: str) -> str:
        m_table = re.search(r"- ([A-Za-z0-9_]+\.[A-Za-z0-9_]+)", prompt)
        m_col = re.search(r"\.([A-Za-z0-9_]+) \(", prompt)
        table = m_table.group(1) if m_table else "sys.objects"
        col = m_col.group(1) if m_col else "name"
        return f"SELECT TOP 50 {col} FROM {table};"

    def generate_sql(self, prompt: str) -> str:
        if self._llm is None: return self._stub(prompt)
        system = ("You are SQLCoder for Microsoft SQL Server. "
                  "Use only listed tables/columns. Return ONE SELECT statement. "
                  "No quotes, no fences, no explanations.")
        full = f"<|system|>\n{system}\n<|user|>\n{prompt}\n<|assistant|>"
        out = self._llm(prompt=full, max_tokens=512, temperature=0.05,
                        top_p=0.9, repeat_penalty=1.1,
                        stop=["<|user|>","<|system|>","```"])
        raw = out["choices"][0]["text"]
        return self._clean_sql_text(raw)
