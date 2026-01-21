from services import sql_service


def test_transpile_strips_backticks():
    sql = "SELECT `id`, `name` FROM `dbo`.`users`"
    out = sql_service.transpile_to_tsql(sql, read_dialect="mysql")
    assert "[" in out and "`" not in out


def test_inject_safety_top():
    sql = "select id from [dbo].[users]"
    out = sql_service.inject_safety_top(sql, limit=50)
    assert "TOP" in out.upper()
