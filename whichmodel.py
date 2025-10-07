# 1) See which models.py Python is actually importing
# python - <<'PY'
import utils.models as m, inspect
print("loaded from:", m.__file__)
print("has generate_sql:", hasattr(m.ModelRunner, "generate_sql"))
print("class methods:", [n for n in dir(m.ModelRunner) if not n.startswith("_")])