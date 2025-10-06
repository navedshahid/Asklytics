
from jinja2 import Environment, FileSystemLoader, select_autoescape

class PromptGenerator:
    def __init__(self, template_dir="./prompting/templates"):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(enabled_extensions=('html','xml'))
        )

    def render_tsql(self, question: str, retrieval: dict, policies: str) -> str:
        tpl = self.env.get_template("tsql.md")
        # Attach convenient dot-access for Jinja
        class Struct(dict):
            __getattr__ = dict.get
        retr = Struct({
            "tables": retrieval.get("tables", []),
            "columns": [Struct({"table":c["table"], "name":c["name"], "dtype":c.get("dtype",""), "stats": c.get("stats",{})}) for c in retrieval.get("columns",[])],
            "relationships": [Struct({"from":r["from"], "to":r["to"], "via":[Struct(v) for v in r["via"]]}) for r in retrieval.get("relationships",[])]
        })
        return tpl.render(question=question, retrieval=retr, policies=policies)
    def render_generic(self, template: str, question: str, retrieval: dict, policies: str) -> str:
        tpl = self.env.get_template(template)
        class S(dict): __getattr__ = dict.get
        retr = S({
        "tables": retrieval.get("tables", []),
        "columns":[S({"table":c["table"],"name":c["name"],"dtype":c.get("dtype",""),"stats":c.get("stats",{})}) for c in retrieval.get("columns",[])],
        "relationships":[S({"from":r["from"],"to":r["to"],"via":[S(v) for v in r["via"]]}) for r in retrieval.get("relationships",[])]
        })
        return tpl.render(question=question, retrieval=retr, policies=policies)

