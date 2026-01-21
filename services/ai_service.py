import logging
import os
from threading import Lock
from typing import Optional, Tuple
import numpy as np
from llama_cpp import Llama
from FlagEmbedding import BGEM3FlagModel
from services.config_service import get_settings
from services.discovery_agent import ScoutAgent
import faiss

logger = logging.getLogger("AskLytics-AI")

_embedder = None
_llm: Optional[Llama] = None
_faiss_index = None
_knowledge_strings = None
AI_LOCK = Lock()

def get_embedder():
    global _embedder
    if _embedder is None:
        with AI_LOCK:
            if _embedder is None:
                logger.info("Initializing BGE-M3 Embedder...")
                _embedder = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    return _embedder

def get_llm():
    global _llm
    if _llm is None:
        with AI_LOCK:
            if _llm is None:
                settings = get_settings()
                llm_cfg = settings.llm
                if not llm_cfg.model_path or not os.path.exists(llm_cfg.model_path):
                    logger.warning(f"LLM model path not found: {llm_cfg.model_path}")
                    return None
                
                logger.info(f"Initializing Llama LLM from {llm_cfg.model_path}...")
                _llm = Llama(
                    model_path=llm_cfg.model_path,
                    n_gpu_layers=llm_cfg.n_gpu_layers,
                    n_ctx=llm_cfg.n_ctx,
                    n_threads=llm_cfg.n_threads,
                    verbose=False
                )
    return _llm

def get_faiss_index() -> Tuple[Optional[faiss.Index], Optional[np.ndarray]]:
    global _faiss_index, _knowledge_strings
    if _faiss_index is None:
        with AI_LOCK:
            if _faiss_index is None:
                settings = get_settings()
                if os.path.exists(str(settings.faiss.index_path)) and os.path.exists(str(settings.faiss.strings_path)):
                    logger.info("Loading FAISS index...")
                    _faiss_index = faiss.read_index(str(settings.faiss.index_path))
                    _knowledge_strings = np.load(str(settings.faiss.strings_path), allow_pickle=True)
                else:
                    logger.warning("FAISS files not found. Triggering ScoutAgent to generate MDL for cold-start.")
                    try:
                        ScoutAgent().discover_and_generate()
                    except Exception as e:
                        logger.warning(f"Scout cold-start failed: {e}")
    return _faiss_index, _knowledge_strings

def search_knowledge(question: str, k: int = 5) -> str:
    embedder = get_embedder()
    index, strings = get_faiss_index()
    if index is None or strings is None:
        return ""
    
    # BGE-M3 encode returns a dict with 'dense_vecs'
    emb = np.asarray(embedder.encode([question])["dense_vecs"], dtype="float32")
    _, I = index.search(emb, k)
    
    context = "\n---\n".join(strings[i] for i in I[0] if i < len(strings))
    return context
