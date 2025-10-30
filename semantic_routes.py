"""
Semantic Layer REST API Routes

Provides endpoints for semantic search, metric compilation,
and knowledge graph management.
"""

from flask import Blueprint, request, jsonify
from typing import Optional
from semantic.engine import SemanticEngine
from governance.rbac import resolve_roles

# Initialize semantic engine
semantic_engine: Optional[SemanticEngine] = None
_routes_registered = False  # Guard flag to prevent duplicate registration


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
        
        # Simple pagination
        for key, items in catalog.items():
            start = (page - 1) * per_page
            end = start + per_page
            catalog[key] = items[start:end]
            catalog[f"{key}_total"] = len(semantic_engine.entities if key == "entities" 
                                         else semantic_engine.metrics if key == "metrics"
                                         else semantic_engine.relations if key == "relations"
                                         else semantic_engine.policies)
        
        return jsonify(catalog)
    
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


