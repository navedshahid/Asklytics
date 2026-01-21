"""
Semantic Layer REST API Routes

Provides endpoints for semantic search, metric compilation,
and knowledge graph management.
"""

from flask import Blueprint, request, jsonify
from typing import Optional, Dict, Any, List, Set
from semantic.engine import SemanticEngine
from governance.rbac import resolve_roles
from semantic.layout_store import LayoutStore

# Initialize semantic engine
semantic_engine: Optional[SemanticEngine] = None
_routes_registered = False  # Guard flag to prevent duplicate registration


def _normalize_table_identifier(identifier: str) -> str:
    """Normalize identifiers like [dbo].[Table] or dbo.Table to schema.table."""
    if not identifier:
        return ""
    cleaned = identifier.replace("[", "").replace("]", "").strip()
    if "." in cleaned:
        schema, table = cleaned.split(".", 1)
    else:
        schema, table = "", cleaned
    return f"{schema.strip().lower()}.{table.strip().lower()}"


def _collect_db_tables(filter_keys: Optional[Dict[str, Set[str]]] = None) -> List[Dict[str, Any]]:
    """Return database tables/columns with optional filtering."""
    from app import get_db_connection, config  # local import to avoid circular deps

    if not config.is_db_configured():
        raise RuntimeError("Database not configured")

    tables: List[Dict[str, Any]] = []
    with get_db_connection() as conn:
        cur = conn.cursor()
        table_query = """
            SELECT TABLE_SCHEMA, TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE='BASE TABLE' 
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        table_rows = cur.execute(table_query).fetchall()
        for schema, table_name in table_rows:
            schema = str(schema)
            table_name = str(table_name)
            qualified_key = f"{schema.lower()}.{table_name.lower()}"
            table_only_key = table_name.lower()
            if filter_keys:
                qualified = filter_keys.get("qualified", set())
                table_only = filter_keys.get("table_only", set())
                if qualified_key not in qualified and table_only_key not in table_only:
                    continue

            col_query = """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, ORDINAL_POSITION,
                       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """
            col_rows = cur.execute(col_query, (schema, table_name)).fetchall()

            pk_query = """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                AND OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME), 'IsPrimaryKey') = 1
                ORDER BY ORDINAL_POSITION
            """
            try:
                pk_rows = cur.execute(pk_query, (schema, table_name)).fetchall()
                pk_columns = {str(row[0]) for row in pk_rows}
            except Exception:
                pk_columns = set()

            dtype_map = {
                "int": "integer",
                "bigint": "integer",
                "smallint": "integer",
                "tinyint": "integer",
                "decimal": "decimal",
                "numeric": "decimal",
                "float": "decimal",
                "real": "decimal",
                "money": "decimal",
                "varchar": "string",
                "nvarchar": "string",
                "char": "string",
                "nchar": "string",
                "text": "string",
                "ntext": "string",
                "date": "date",
                "datetime": "timestamp",
                "datetime2": "timestamp",
                "time": "time",
                "bit": "boolean",
                "uniqueidentifier": "string",
            }

            columns: List[Dict[str, Any]] = []
            for col_row in col_rows:
                (
                    col_name,
                    data_type,
                    is_nullable,
                    ordinal_pos,
                    char_max_len,
                    num_precision,
                    num_scale,
                ) = col_row
                semantic_type = dtype_map.get(str(data_type).lower(), "string")
                description = f"{data_type}"
                if char_max_len:
                    description += f"({char_max_len})"
                elif num_precision:
                    desc = f"{num_precision}"
                    if num_scale:
                        desc += f",{num_scale}"
                    description += f"({desc})"
                columns.append(
                    {
                        "name": str(col_name),
                        "dtype": semantic_type,
                        "source_type": str(data_type),
                        "primary": str(col_name) in pk_columns,
                        "nullable": str(is_nullable).upper() == "YES",
                        "description": description,
                        "ordinal": int(ordinal_pos),
                        "pii": False,
                    }
                )

            tables.append(
                {
                    "name": table_name,
                    "schema": schema,
                    "full_name": f"[{schema}].[{table_name}]",
                    "qualified_name": f"{schema}.{table_name}",
                    "key": qualified_key,
                    "columns": columns,
                    "type": "database_table",
                }
            )
    return tables


def init_semantic_routes(app, embedder_fn=None):
    """
    Initialize semantic routes and engine.
    
    Args:
        app: Flask app instance
        embedder_fn: Optional embedding function for semantic search
    """
    global semantic_engine, _routes_registered
    
    # Prevent duplicate initialization
    if _routes_registered:
        app.logger.info("Semantic routes already registered, skipping re-initialization")
        return
    
    # Initialize engine
    semantic_engine = SemanticEngine(mdl_root="semantic/mdl", embed_fn=embedder_fn)
    
    # Load MDL on startup
    try:
        load_result = semantic_engine.load()
        app.logger.info(f"Semantic engine loaded: {load_result}")
        
        # Build semantic index if embedder available
        if embedder_fn:
            index_result = semantic_engine.index_semantics()
            app.logger.info(f"Semantic index built: {index_result}")
    except Exception as e:
        app.logger.error(f"Failed to initialize semantic engine: {e}")
    
    # Register routes
    register_routes(app)
    _routes_registered = True


def register_routes(app):
    """Register semantic API routes with Flask app."""
    layout_store = LayoutStore()
    
    @app.get("/semantic/health")
    def semantic_health():
        """Get semantic engine health status."""
        if not semantic_engine:
            return jsonify({
                "status": "not_initialized",
                "error": "Semantic engine not available"
            }), 503
        
        health = semantic_engine.get_health()
        return jsonify(health)
    
    @app.get("/semantic/catalog")
    def semantic_catalog():
        """
        Get catalog of entities, metrics, relations, policies.
        
        Query params:
            type: Optional filter (entity, metric, relation, policy)
            page: Page number (default 1)
            per_page: Items per page (default 50)
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        type_filter = request.args.get("type")
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "50"))
        
        catalog = semantic_engine.get_catalog(type_filter)
        
        # Build result dictionary to avoid modifying during iteration
        result = {}
        
        # Simple pagination - iterate over keys to avoid modification during iteration
        for key in list(catalog.keys()):
            items = catalog[key]
            start = (page - 1) * per_page
            end = start + per_page
            result[key] = items[start:end]
            
            # Calculate total count
            if key == "entities":
                total_count = len(semantic_engine.entities)
            elif key == "metrics":
                total_count = len(semantic_engine.metrics)
            elif key == "relations":
                total_count = len(semantic_engine.relations)
            elif key == "policies":
                total_count = len(semantic_engine.policies)
            else:
                total_count = len(items)
            
            result[f"{key}_total"] = total_count
        
        return jsonify(result)
    
    @app.post("/semantic/search")
    def semantic_search():
        """
        Semantic search over knowledge graph.
        
        Request body:
            {
                "q": "search query",
                "k": 5  // optional, default 5
            }
        
        Returns:
            {
                "results": [
                    {
                        "type": "metric|entity|relation|policy",
                        "name": "...",
                        "description": "...",
                        "score": 0.95,
                        "metadata": {...}
                    }
                ]
            }
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        data = request.get_json() or {}
        query = data.get("q", "")
        k = data.get("k", 5)
        
        if not query:
            return jsonify({"error": "Query 'q' required"}), 400
        
        results = semantic_engine.search(query, k)
        
        return jsonify({"results": results, "query": query, "k": k})

    @app.get("/semantic/mdl/validate")
    def validate_mdl():
        """Validate MDL integrity (entities, metrics, relations)."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        return jsonify(semantic_engine.validate_mdl())

    @app.get("/semantic/mdl/snapshot")
    def mdl_snapshot():
        """Return full MDL snapshot (read-only)."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        return jsonify(semantic_engine.snapshot())
    
    @app.get("/semantic/entity/<name>")
    def get_entity_details(name: str):
        """Get full entity details including columns."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        if name not in semantic_engine.entities:
            return jsonify({"error": "Entity not found"}), 404
        entity = semantic_engine.entities[name]
        return jsonify({
            "name": name,
            "description": entity.get("description", ""),
            "grain": entity.get("grain"),
            "columns": entity.get("columns", []),
            "tags": entity.get("tags", []),
            "properties": entity.get("properties", {}),
            "reference": entity.get("reference", {})
        })
    
    def _truthy(value: Optional[str]) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    @app.get("/semantic/db/tables")
    def get_database_tables():
        """Get database tables from connected database with column details."""
        try:
            selected_param = request.args.get("selected_only")
            from app import config  # local import to avoid circular deps

            configured_selection = config.get_selected_tables() or []
            use_selected = False
            if selected_param is None:
                use_selected = bool(configured_selection)
            else:
                use_selected = _truthy(selected_param)

            filter_keys = None
            if use_selected and configured_selection:
                filter_keys = _build_table_filter(configured_selection)

            tables = _collect_db_tables(filter_keys=filter_keys)
            return jsonify({
                "tables": tables,
                "selected_only": bool(filter_keys),
                "total": len(tables),
                "selection_count": len(configured_selection),
            })
        except RuntimeError as err:
            return jsonify({"error": str(err)}), 400
        except Exception as e:
            import traceback
            app.logger.error(f"Failed to get database tables: {e}\n{traceback.format_exc()}")
            return jsonify({"error": str(e)}), 500

    def _build_table_filter(raw_tables: List[Any]) -> Dict[str, Set[str]]:
        qualified: Set[str] = set()
        table_only: Set[str] = set()
        for item in raw_tables or []:
            if isinstance(item, str):
                cleaned = item.strip()
                if not cleaned:
                    continue
                norm = _normalize_table_identifier(cleaned)
                if "." in norm:
                    qualified.add(norm)
                else:
                    table_only.add(cleaned.replace("[", "").replace("]", "").strip().lower())
            elif isinstance(item, dict):
                schema = str(
                    item.get("schema")
                    or item.get("Schema")
                    or item.get("SCHEMA")
                    or ""
                )
                table = str(
                    item.get("name")
                    or item.get("table")
                    or item.get("Table")
                    or item.get("TABLE")
                    or ""
                )
                if schema and table:
                    qualified.add(_normalize_table_identifier(f"{schema}.{table}"))
                elif table:
                    table_only.add(table.replace("[", "").replace("]", "").strip().lower())
        return {"qualified": qualified, "table_only": table_only}

    @app.post("/semantic/entities")
    def upsert_entity():
        """Create/update an entity (admin only)."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        data = request.get_json() or {}
        result = semantic_engine.save_entity(data)
        status = 200 if result.get("status") == "success" else 400
        return jsonify(result), status

    @app.delete("/semantic/entities/<name>")
    def remove_entity(name: str):
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        result = semantic_engine.delete_entity(name)
        status = 200 if result.get("status") == "success" else 404
        return jsonify(result), status

    @app.post("/semantic/metrics")
    def upsert_metric():
        """Create/update a metric (admin only)."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        data = request.get_json() or {}
        result = semantic_engine.save_metric(data)
        status = 200 if result.get("status") == "success" else 400
        return jsonify(result), status

    @app.delete("/semantic/metrics/<name>")
    def remove_metric(name: str):
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        result = semantic_engine.delete_metric(name)
        status = 200 if result.get("status") == "success" else 404
        return jsonify(result), status

    @app.post("/semantic/entities/import")
    def import_entities_from_db():
        """Generate MDL entities from live database tables."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403

        body = request.get_json(force=True) or {}
        requested_tables = body.get("tables") or []
        if not requested_tables:
            return jsonify({"error": "tables array required"}), 400

        table_filter = _build_table_filter(requested_tables)
        if not table_filter["qualified"] and not table_filter["table_only"]:
            return jsonify({"error": "No valid table identifiers provided"}), 400

        try:
            table_metadata = _collect_db_tables(filter_keys=table_filter)
        except RuntimeError as err:
            return jsonify({"error": str(err)}), 400
        except Exception as e:
            import traceback
            app.logger.error(f"Failed to introspect tables: {e}\n{traceback.format_exc()}")
            return jsonify({"error": "Failed to introspect tables"}), 500

        if not table_metadata:
            return jsonify({"error": "No matching tables found"}), 404

        detect_pii = bool(body.get("detect_pii", True))
        dry_run = bool(body.get("dry_run", False))
        name_prefix = str(body.get("name_prefix") or "").strip()
        base_tags = body.get("tags") or []
        overrides = body.get("name_overrides")
        override_map: Dict[str, str] = {}
        if isinstance(overrides, dict):
            for raw_key, override_value in overrides.items():
                if not isinstance(raw_key, str) or not isinstance(override_value, str):
                    continue
                cleaned_key = raw_key.replace("[", "").replace("]", "").strip().lower()
                override_map[cleaned_key] = override_value.strip()

        previews: List[Dict[str, Any]] = []
        saved: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for meta in table_metadata:
            try:
                qualified = meta.get("qualified_name", "")
                override_name = override_map.get(qualified.lower()) or override_map.get(meta["name"].lower())
                entity_payload = semantic_engine.generate_entity_from_table(
                    meta,
                    detect_pii=detect_pii,
                    default_tags=base_tags,
                    name_override=override_name,
                )
                if name_prefix:
                    entity_payload["name"] = f"{name_prefix}{entity_payload['name']}"

                if dry_run:
                    previews.append(
                        {
                            "table": qualified,
                            "entity": entity_payload,
                        }
                    )
                else:
                    save_result = semantic_engine.save_entity(entity_payload)
                    if save_result.get("status") == "success":
                        saved.append(
                            {
                                "table": qualified,
                                "name": entity_payload["name"],
                                "path": save_result.get("path"),
                            }
                        )
                    else:
                        errors.append(
                            {"table": qualified, "error": save_result.get("error", "Unknown error")}
                        )
            except Exception as exc:
                errors.append({"table": meta.get("qualified_name"), "error": str(exc)})

        status = "success" if not errors else "partial"
        payload = {
            "status": status,
            "dry_run": dry_run,
            "count": len(previews if dry_run else saved),
            "entities": previews if dry_run else saved,
            "errors": errors,
        }
        return jsonify(payload), (200 if status == "success" else 207)
    
    @app.get("/semantic/layouts")
    def list_layouts():
        """List available MDL graph layouts (names only)."""
        try:
            return jsonify(layout_store.list())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.get("/semantic/layout/<name>")
    def get_layout(name: str):
        """Get a specific MDL layout document."""
        try:
            doc = layout_store.get(name)
            if doc is None:
                return jsonify({"error": "not_found"}), 404
            return jsonify({"name": name, "layout": doc})
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.post("/semantic/layout/<name>")
    def upsert_layout(name: str):
        """Create or update an MDL layout document. Requires admin role."""
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        try:
            body = request.get_json() or {}
            layout = body.get("layout")
            if layout is None:
                return jsonify({"error": "layout required"}), 400
            result = layout_store.put(name, layout)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.delete("/semantic/layout/<name>")
    def delete_layout(name: str):
        """Delete an MDL layout document. Requires admin role."""
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        try:
            result = layout_store.delete(name)
            status = 200 if result.get("status") == "success" else 404
            return jsonify(result), status
        except Exception as e:
            return jsonify({"error": str(e)}), 400
    
    @app.post("/semantic/compile")
    def semantic_compile():
        """
        Compile a metric or entity to SQL with governance.
        
        Request body:
            {
                "target": "metric_name or entity_name",
                "filters": {"store": 1, "product": 42},  // optional
                "time_range": {"start_date": "2024-01-01", "end_date": "2024-12-31"},  // optional
                "limit": 1000  // optional
            }
        
        Returns:
            {
                "status": "success",
                "sql": "SELECT ...",
                "lineage": [...],
                "grain": [...],
                "warnings": [...],
                "policies_applied": [...]
            }
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        data = request.get_json() or {}
        target = data.get("target")
        filters = data.get("filters", {})
        time_range = data.get("time_range", {})
        limit = data.get("limit", 1000)
        
        if not target:
            return jsonify({"error": "Target metric or entity required"}), 400
        
        # Resolve user roles for policy enforcement
        user_roles = list(resolve_roles(request))
        
        result = semantic_engine.compile(
            target=target,
            filters=filters,
            time_range=time_range,
            user_roles=user_roles,
            limit=limit
        )
        
        if result.get("status") == "error":
            return jsonify(result), 400
        
        return jsonify(result)
    
    @app.post("/semantic/reindex")
    def semantic_reindex():
        """
        Reload MDL and rebuild semantic index.
        
        Requires admin or auditor role.
        
        Returns:
            {
                "load": {...},
                "index": {...},
                "graph": {...}
            }
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        # Check authorization
        roles = resolve_roles(request)
        if "admin" not in roles and "auditor" not in roles:
            return jsonify({"error": "Admin or auditor role required"}), 403
        
        try:
            # Reload MDL
            load_result = semantic_engine.load()
            
            # Rebuild graph
            graph_result = semantic_engine.build_graph()
            
            # Rebuild semantic index
            index_result = semantic_engine.index_semantics()
            
            return jsonify({
                "status": "success",
                "load": load_result,
                "graph": graph_result,
                "index": index_result
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "error": str(e)
            }), 500
    
    @app.post("/semantic/relations")
    def create_relation():
        """
        Create or update a relation.
        
        Requires admin role.
        
        Request body:
            {
                "name": "relation_name",
                "from": {"model": "orders", "column": "customer_id"},
                "to": {"model": "customers", "column": "customer_id"},
                "type": "MANY_TO_ONE",
                "description": "...",
                "condition": "orders.customer_id = customers.customer_id"
            }
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        # Check authorization
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        
        data = request.get_json() or {}
        
        # Validate required fields
        if not data.get("name"):
            return jsonify({"error": "Relation name required"}), 400
        if not data.get("from") or not data.get("to"):
            return jsonify({"error": "From and To models required"}), 400
        if not data.get("type"):
            return jsonify({"error": "Relation type required"}), 400
        
        result = semantic_engine.save_relation(data)
        
        if result.get("status") == "error":
            return jsonify(result), 400
        
        return jsonify(result)
    
    @app.delete("/semantic/relations/<name>")
    def delete_relation(name: str):
        """
        Delete a relation.
        
        Requires admin role.
        """
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        # Check authorization
        roles = resolve_roles(request)
        if "admin" not in roles:
            return jsonify({"error": "Admin role required"}), 403
        
        result = semantic_engine.delete_relation(name)
        
        if result.get("status") == "error":
            return jsonify(result), 404
        
        return jsonify(result)
    
    @app.get("/semantic/relations")
    def list_relations():
        """Get all relations."""
        if not semantic_engine:
            return jsonify({"error": "Semantic engine not available"}), 503
        
        catalog = semantic_engine.get_catalog(type_filter="relation")
        return jsonify({"relations": catalog.get("relations", [])})
