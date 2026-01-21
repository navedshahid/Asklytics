"""
Semantic Engine - Business Knowledge Graph (BKG) Core

Loads MDL files, builds in-memory graph, compiles metrics to SQL,
and provides semantic search over entities/metrics/relations/policies.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple, Sequence
from datetime import datetime
import re

# Optional FAISS for semantic search
try:
    import faiss
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

PII_NAME_HINTS: Set[str] = {
    "email",
    "phone",
    "first_name",
    "lastname",
    "last_name",
    "fullname",
    "ssn",
    "tax",
    "passport",
    "address",
    "street",
    "city",
    "zip",
    "postal",
    "dob",
    "birth",
}
TIME_DTYPES = {"timestamp", "datetime", "datetime2", "date"}


class SemanticEngine:
    """
    Semantic layer engine that loads MDL, builds knowledge graph,
    and compiles business metrics to SQL.
    """

    def __init__(self, mdl_root: str = "semantic/mdl", embed_fn=None):
        """
        Initialize semantic engine.

        Args:
            mdl_root: Path to MDL directory containing entities/metrics/relations/policies
            embed_fn: Optional embedding function for semantic search
        """
        self.mdl_root = Path(mdl_root)
        self.embed_fn = embed_fn

        # Knowledge graph storage
        self.entities: Dict[str, Dict] = {}
        self.metrics: Dict[str, Dict] = {}
        self.relations: Dict[str, Dict] = {}
        self.policies: Dict[str, Dict] = {}

        # Graph indices
        self.entity_columns: Dict[str, List[str]] = {}  # entity -> [columns]
        self.relation_graph: Dict[str, List[Dict]] = {}  # from_entity -> [{to, type, condition}]

        # Semantic search index
        self.semantic_index = None
        self.semantic_docs: List[Dict] = []

        self.last_loaded: Optional[datetime] = None
        self.load_errors: List[str] = []

    def load(self) -> Dict[str, Any]:
        """
        Load all MDL files and build knowledge graph.

        Returns:
            Status dict with counts and any errors
        """
        self.load_errors = []
        start = datetime.utcnow()

        # Load entities
        entities_dir = self.mdl_root / "entities"
        if entities_dir.exists():
            for yaml_file in entities_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        entity = yaml.safe_load(f)
                        name = entity.get("name")
                        if name:
                            self.entities[name] = entity
                            self.entity_columns[name] = [
                                col["name"] for col in entity.get("columns", [])
                            ]
                except Exception as e:
                    self.load_errors.append(f"Error loading {yaml_file.name}: {str(e)}")

        # Load metrics
        metrics_dir = self.mdl_root / "metrics"
        if metrics_dir.exists():
            for yaml_file in metrics_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        metric = yaml.safe_load(f)
                        name = metric.get("name")
                        if name:
                            self.metrics[name] = metric
                except Exception as e:
                    self.load_errors.append(f"Error loading {yaml_file.name}: {str(e)}")

        # Load relations
        relations_dir = self.mdl_root / "relations"
        if relations_dir.exists():
            for yaml_file in relations_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        relation = yaml.safe_load(f)
                        name = relation.get("name")
                        if name:
                            self.relations[name] = relation
                            # Build relation graph
                            from_model = relation.get("from", {}).get("model")
                            to_model = relation.get("to", {}).get("model")
                            if from_model:
                                if from_model not in self.relation_graph:
                                    self.relation_graph[from_model] = []
                                self.relation_graph[from_model].append({
                                    "to": to_model,
                                    "type": relation.get("type"),
                                    "condition": relation.get("condition"),
                                    "name": name
                                })
                except Exception as e:
                    self.load_errors.append(f"Error loading {yaml_file.name}: {str(e)}")

        # Load policies
        policies_dir = self.mdl_root / "policies"
        if policies_dir.exists():
            for yaml_file in policies_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        policy = yaml.safe_load(f)
                        name = policy.get("name")
                        if name:
                            self.policies[name] = policy
                except Exception as e:
                    self.load_errors.append(f"Error loading {yaml_file.name}: {str(e)}")

        self.last_loaded = datetime.utcnow()
        load_time = (self.last_loaded - start).total_seconds()

        return {
            "status": "success" if not self.load_errors else "partial",
            "entities": len(self.entities),
            "metrics": len(self.metrics),
            "relations": len(self.relations),
            "policies": len(self.policies),
            "load_time_ms": int(load_time * 1000),
            "errors": self.load_errors
        }

    def build_graph(self) -> Dict[str, Any]:
        """
        Build in-memory knowledge graph from loaded MDL.

        Returns:
            Graph statistics
        """
        # Graph is built during load() via relation_graph
        # This method can be extended for more complex graph algorithms

        node_count = len(self.entities) + len(self.metrics) + len(self.policies)
        edge_count = sum(len(rels) for rels in self.relation_graph.values())

        return {
            "nodes": node_count,
            "edges": edge_count,
            "entities": len(self.entities),
            "metrics": len(self.metrics),
            "relations": len(self.relations),
            "policies": len(self.policies)
        }

    def index_semantics(self) -> Dict[str, Any]:
        """
        Build semantic vector index from entities, metrics, and examples.

        Returns:
            Index statistics
        """
        if not self.embed_fn:
            return {"status": "skipped", "reason": "no_embedding_function"}

        if not FAISS_AVAILABLE:
            return {"status": "skipped", "reason": "faiss_not_installed"}

        self.semantic_docs = []

        # Index entities
        for name, entity in self.entities.items():
            doc_text = f"{name} {entity.get('description', '')}"
            for col in entity.get("columns", []):
                doc_text += f" {col['name']} {col.get('description', '')}"
            
            self.semantic_docs.append({
                "type": "entity",
                "name": name,
                "text": doc_text,
                "path": f"entities/{name}",
                "metadata": entity
            })

        # Index metrics
        for name, metric in self.metrics.items():
            doc_text = f"{name} {metric.get('description', '')}"
            for example in metric.get("examples", []):
                doc_text += f" {example}"
            
            self.semantic_docs.append({
                "type": "metric",
                "name": name,
                "text": doc_text,
                "path": f"metrics/{name}",
                "metadata": metric
            })

        # Index relations
        for name, relation in self.relations.items():
            doc_text = f"{name} {relation.get('description', '')}"
            self.semantic_docs.append({
                "type": "relation",
                "name": name,
                "text": doc_text,
                "path": f"relations/{name}",
                "metadata": relation
            })

        # Index policies
        for name, policy in self.policies.items():
            doc_text = f"{name} {policy.get('description', '')}"
            self.semantic_docs.append({
                "type": "policy",
                "name": name,
                "text": doc_text,
                "path": f"policies/{name}",
                "metadata": policy
            })

        # Generate embeddings
        try:
            texts = [doc["text"] for doc in self.semantic_docs]
            embeddings = self.embed_fn(texts)
            
            if isinstance(embeddings, list):
                embeddings = np.array(embeddings, dtype=np.float32)
            
            # Build FAISS index
            dimension = embeddings.shape[1]
            self.semantic_index = faiss.IndexFlatL2(dimension)
            self.semantic_index.add(embeddings)

            return {
                "status": "success",
                "documents": len(self.semantic_docs),
                "dimension": dimension
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Semantic search over knowledge graph.

        Args:
            query: Natural language search query
            k: Number of results to return

        Returns:
            List of matching documents with scores
        """
        if not self.semantic_index or not self.embed_fn:
            # Fallback: keyword search
            return self._keyword_search(query, k)

        try:
            query_embedding = self.embed_fn([query])[0]
            if isinstance(query_embedding, list):
                query_embedding = np.array(query_embedding, dtype=np.float32)
            
            query_embedding = query_embedding.reshape(1, -1)
            distances, indices = self.semantic_index.search(query_embedding, k)

            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if idx < len(self.semantic_docs):
                    doc = self.semantic_docs[idx]
                    results.append({
                        "type": doc["type"],
                        "name": doc["name"],
                        "description": doc["metadata"].get("description", ""),
                        "path": doc["path"],
                        "score": float(1.0 / (1.0 + dist)),  # Convert distance to similarity
                        "metadata": doc["metadata"]
                    })

            return results
        except Exception as e:
            print(f"Semantic search error: {e}")
            return self._keyword_search(query, k)

    def _keyword_search(self, query: str, k: int) -> List[Dict[str, Any]]:
        """Fallback keyword-based search."""
        query_lower = query.lower()
        results = []

        # Search entities
        for name, entity in self.entities.items():
            score = 0
            if query_lower in name.lower():
                score += 10
            if query_lower in entity.get("description", "").lower():
                score += 5
            
            if score > 0:
                results.append({
                    "type": "entity",
                    "name": name,
                    "description": entity.get("description", ""),
                    "path": f"entities/{name}",
                    "score": score,
                    "metadata": entity
                })

        # Search metrics
        for name, metric in self.metrics.items():
            score = 0
            if query_lower in name.lower():
                score += 10
            if query_lower in metric.get("description", "").lower():
                score += 5
            for example in metric.get("examples", []):
                if query_lower in example.lower():
                    score += 3
            
            if score > 0:
                results.append({
                    "type": "metric",
                    "name": name,
                    "description": metric.get("description", ""),
                    "path": f"metrics/{name}",
                    "score": score,
                    "metadata": metric
                })

        # Sort by score and return top k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:k]

    def compile(
        self,
        target: str,
        filters: Optional[Dict[str, Any]] = None,
        time_range: Optional[Dict[str, str]] = None,
        user_roles: Optional[List[str]] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Compile a metric or entity query to SQL with governance applied.

        Args:
            target: Metric or entity name
            filters: Optional filters to apply
            time_range: Optional time range {start_date, end_date}
            user_roles: User roles for policy enforcement
            limit: Result limit

        Returns:
            Compiled SQL with lineage and warnings
        """
        filters = filters or {}
        time_range = time_range or {}
        user_roles = user_roles or []

        # Check if target is a metric
        if target in self.metrics:
            return self._compile_metric(target, filters, time_range, user_roles, limit)
        
        # Check if target is an entity
        if target in self.entities:
            return self._compile_entity(target, filters, time_range, user_roles, limit)

        return {
            "status": "error",
            "error": f"Target '{target}' not found in metrics or entities",
            "sql": None,
            "lineage": [],
            "warnings": [f"Unknown target: {target}"]
        }

    def _compile_metric(
        self,
        name: str,
        filters: Dict[str, Any],
        time_range: Dict[str, str],
        user_roles: List[str],
        limit: int
    ) -> Dict[str, Any]:
        """Compile a metric to SQL."""
        metric = self.metrics[name]
        sql = metric.get("sql", "")
        
        warnings = []
        policies_applied = []

        # Substitute time range with sanitization to prevent SQL injection
        if time_range:
            start_date = self._sanitize_date_value(time_range.get('start_date', '1900-01-01'))
            end_date = self._sanitize_date_value(time_range.get('end_date', '2099-12-31'))
            sql = sql.replace(":start_date", f"'{start_date}'")
            sql = sql.replace(":end_date", f"'{end_date}'")
        else:
            warnings.append("No time range provided; using defaults")
            sql = sql.replace(":start_date", "'1900-01-01'")
            sql = sql.replace(":end_date", "'2099-12-31'")

        # Build filter clauses
        filter_clauses = []
        metric_filters = metric.get("filters", {})
        for filter_name, filter_value in filters.items():
            if filter_name in metric_filters:
                clause = metric_filters[filter_name]
                # Sanitize filter value to prevent SQL injection
                sanitized_value = self._sanitize_sql_value(filter_value)
                # Replace parameter placeholder
                clause = clause.replace(f":{filter_name}", sanitized_value)
                filter_clauses.append(clause)
            else:
                warnings.append(f"Filter '{filter_name}' not supported for metric '{name}'")

        # Inject filters
        if filter_clauses:
            and_filters = " AND " + " AND ".join(filter_clauses)
        else:
            and_filters = ""
        
        sql = sql.replace("{{AND_FILTERS}}", and_filters)

        # Apply policies (PII masking, row filters)
        sql, policy_info = self._apply_policies(sql, metric.get("entity"), user_roles)
        policies_applied.extend(policy_info)

        # Add limit if not present
        if "LIMIT" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + f"\nLIMIT {limit};"

        return {
            "status": "success",
            "sql": sql,
            "lineage": metric.get("lineage", []),
            "grain": metric.get("grain", []),
            "warnings": warnings,
            "policies_applied": policies_applied,
            "metric": name,
            "entity": metric.get("entity")
        }

    def _compile_entity(
        self,
        name: str,
        filters: Dict[str, Any],
        time_range: Dict[str, str],
        user_roles: List[str],
        limit: int
    ) -> Dict[str, Any]:
        """Compile an entity query to SQL."""
        entity = self.entities[name]
        table = entity.get("reference", {}).get("table", name)
        
        warnings = []
        policies_applied = []

        # Build SELECT clause
        columns = entity.get("columns", [])
        select_cols = [col["name"] for col in columns]
        
        # Apply column masking policies
        masked_cols = []
        for col in select_cols:
            masked_col, mask_info = self._mask_column(name, col, user_roles)
            masked_cols.append(masked_col)
            if mask_info:
                policies_applied.append(mask_info)

        sql = f"SELECT {', '.join(masked_cols)}\nFROM {table}"

        # Build WHERE clause
        where_clauses = []
        
        # Default filters from entity
        default_filters = entity.get("properties", {}).get("default_filters", [])
        where_clauses.extend(default_filters)

        # Time range filter
        time_col = entity.get("properties", {}).get("default_time_col")
        if time_range and time_col:
            if "start_date" in time_range:
                where_clauses.append(f"{time_col} >= '{time_range['start_date']}'")
            if "end_date" in time_range:
                where_clauses.append(f"{time_col} <= '{time_range['end_date']}'")

        # Apply row filter policies
        row_filters = self._get_row_filters(name, user_roles)
        where_clauses.extend(row_filters)
        if row_filters:
            policies_applied.append({"type": "row_filter", "count": len(row_filters)})

        if where_clauses:
            sql += "\nWHERE " + " AND ".join(where_clauses)

        sql += f"\nLIMIT {limit};"

        return {
            "status": "success",
            "sql": sql,
            "lineage": [{"table": table, "columns": select_cols}],
            "grain": [entity.get("grain")],
            "warnings": warnings,
            "policies_applied": policies_applied,
            "entity": name
        }

    def _apply_policies(
        self,
        sql: str,
        entity: Optional[str],
        user_roles: List[str]
    ) -> Tuple[str, List[Dict]]:
        """Apply governance policies to SQL."""
        policies_applied = []

        # Note: Full policy application would require SQL parsing
        # For now, we return warnings
        for policy_name, policy in self.policies.items():
            if policy.get("type") == "mask_column":
                roles_exempt = policy.get("roles_exempt", [])
                if not any(role in roles_exempt for role in user_roles):
                    policies_applied.append({
                        "policy": policy_name,
                        "type": "mask_column",
                        "description": policy.get("description", "")
                    })

        return sql, policies_applied

    def _mask_column(
        self,
        entity: str,
        column: str,
        user_roles: List[str]
    ) -> Tuple[str, Optional[Dict]]:
        """Apply column masking if needed."""
        for policy_name, policy in self.policies.items():
            if policy.get("type") == "mask_column":
                roles_exempt = policy.get("roles_exempt", [])
                if any(role in roles_exempt for role in user_roles):
                    continue  # User exempt from masking

                for target in policy.get("targets", []):
                    if target.get("entity") == entity and target.get("column") == column:
                        rule = target.get("rule", "")
                        # Extract the CASE expression result
                        masked = f"{rule} AS {column}"
                        return masked, {
                            "policy": policy_name,
                            "column": f"{entity}.{column}",
                            "type": "mask"
                        }

        return column, None

    def _get_row_filters(self, entity: str, user_roles: List[str]) -> List[str]:
        """Get row filter conditions for entity."""
        filters = []
        
        for policy_name, policy in self.policies.items():
            if policy.get("type") == "row_filter":
                roles_exempt = policy.get("roles_exempt", [])
                if any(role in roles_exempt for role in user_roles):
                    continue

                for target in policy.get("targets", []):
                    if target.get("entity") == entity:
                        condition = target.get("condition", "")
                        if condition:
                            filters.append(condition)

        return filters

    def get_catalog(self, type_filter: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        Get catalog of all entities, metrics, relations.

        Args:
            type_filter: Optional filter by type (entity, metric, relation, policy)

        Returns:
            Catalog dictionary
        """
        catalog = {}

        if not type_filter or type_filter == "entity":
            catalog["entities"] = [
                {
                    "name": name,
                    "description": entity.get("description", ""),
                    "grain": entity.get("grain"),
                    "columns": len(entity.get("columns", [])),
                    "tags": entity.get("tags", [])
                }
                for name, entity in self.entities.items()
            ]

        if not type_filter or type_filter == "metric":
            catalog["metrics"] = [
                {
                    "name": name,
                    "description": metric.get("description", ""),
                    "entity": metric.get("entity"),
                    "grain": metric.get("grain"),
                    "examples": metric.get("examples", []),
                    "tags": metric.get("tags", [])
                }
                for name, metric in self.metrics.items()
            ]

        if not type_filter or type_filter == "relation":
            catalog["relations"] = [
                {
                    "name": name,
                    "from": f"{rel.get('from', {}).get('model')}.{rel.get('from', {}).get('column')}",
                    "to": f"{rel.get('to', {}).get('model')}.{rel.get('to', {}).get('column')}",
                    "type": rel.get("type"),
                    "description": rel.get("description", "")
                }
                for name, rel in self.relations.items()
            ]

        if not type_filter or type_filter == "policy":
            catalog["policies"] = [
                {
                    "name": name,
                    "type": policy.get("type"),
                    "description": policy.get("description", ""),
                    "roles_exempt": policy.get("roles_exempt", [])
                }
                for name, policy in self.policies.items()
            ]

        return catalog

    def _sanitize_sql_value(self, value: Any) -> str:
        """
        Sanitize a value for safe SQL injection.
        
        Args:
            value: Filter value to sanitize
            
        Returns:
            Sanitized SQL-safe string
        """
        # Convert to string
        str_value = str(value)
        
        # Check for SQL injection patterns
        dangerous_patterns = [
            ';', '--', '/*', '*/', 'xp_', 'sp_', 'exec', 'execute',
            'drop', 'delete', 'insert', 'update', 'alter', 'create',
            'union', 'select', 'from', 'where', '@@', 'char(', 'waitfor'
        ]
        
        str_lower = str_value.lower()
        for pattern in dangerous_patterns:
            if pattern in str_lower:
                raise ValueError(f"Potentially dangerous SQL pattern detected: {pattern}")
        
        # Escape single quotes (SQL standard)
        str_value = str_value.replace("'", "''")
        
        # For numeric values, validate and return without quotes
        if isinstance(value, (int, float)):
            return str(value)
        
        # For string values, return with quotes
        return f"'{str_value}'"
    
    def _sanitize_date_value(self, date_str: str) -> str:
        """
        Sanitize a date string for safe SQL injection.
        
        Args:
            date_str: Date string in format YYYY-MM-DD
            
        Returns:
            Sanitized date string
        """
        # Validate date format (ISO 8601: YYYY-MM-DD)
        date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        
        if not date_pattern.match(date_str):
            raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
        
        # Additional validation: check if it's a valid date
        try:
            year, month, day = map(int, date_str.split('-'))
            if not (1900 <= year <= 2100):
                raise ValueError("Year out of range")
            if not (1 <= month <= 12):
                raise ValueError("Month out of range")
            if not (1 <= day <= 31):
                raise ValueError("Day out of range")
        except Exception as e:
            raise ValueError(f"Invalid date: {date_str} - {str(e)}")
        
        return date_str
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename to prevent path traversal attacks.
        
        Args:
            filename: Filename to sanitize
            
        Returns:
            Safe filename (alphanumeric, underscore, hyphen only)
        """
        # Only allow alphanumeric, underscore, and hyphen
        safe_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
        
        if not safe_pattern.match(filename):
            return ""  # Invalid filename
        
        # Additional checks for dangerous patterns
        if '..' in filename or '/' in filename or '\\' in filename:
            return ""
        
        return filename

    def get_health(self) -> Dict[str, Any]:
        """Get engine health status."""
        return {
            "status": "healthy" if self.last_loaded else "not_loaded",
            "last_loaded": self.last_loaded.isoformat() if self.last_loaded else None,
            "entities": len(self.entities),
            "metrics": len(self.metrics),
            "relations": len(self.relations),
            "policies": len(self.policies),
            "semantic_index": "available" if self.semantic_index else "not_indexed",
            "errors": self.load_errors
        }

    def generate_entity_from_table(
        self,
        table_meta: Dict[str, Any],
        *,
        detect_pii: bool = True,
        default_tags: Optional[Sequence[str]] = None,
        name_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Derive an entity definition from raw database metadata."""
        if not table_meta:
            raise ValueError("table metadata required")
        raw_name = name_override or table_meta.get("name")
        if not raw_name:
            raise ValueError("Table name missing")
        safe_name = self._sanitize_filename(str(raw_name))
        if not safe_name:
            raise ValueError(f"Invalid entity name: {raw_name}")

        columns_meta = table_meta.get("columns") or []
        if not columns_meta:
            raise ValueError(f"No columns provided for table {raw_name}")

        grain = None
        for col in columns_meta:
            if col.get("primary"):
                grain = col.get("name")
                break
        if not grain:
            for col in columns_meta:
                col_name = str(col.get("name") or "")
                if col_name.lower().endswith("_id"):
                    grain = col_name
                    break
        if not grain and columns_meta:
            grain = columns_meta[0].get("name")

        default_time_col = None
        for col in columns_meta:
            dtype = str(col.get("dtype") or col.get("source_type") or "").lower()
            if dtype in TIME_DTYPES:
                default_time_col = col.get("name")
                break

        tags: List[str] = []
        schema = table_meta.get("schema")
        if schema:
            tags.append(str(schema).lower())
        tags.append("auto-generated")
        if default_tags:
            tags.extend([str(tag) for tag in default_tags if tag])
        deduped_tags: List[str] = []
        for tag in tags:
            if tag and tag not in deduped_tags:
                deduped_tags.append(tag)

        columns_payload: List[Dict[str, Any]] = []
        for col in columns_meta:
            col_name = str(col.get("name"))
            dtype = str(col.get("dtype") or "string")
            column_entry: Dict[str, Any] = {
                "name": col_name,
                "dtype": dtype,
                "description": col.get("description") or col.get("source_type") or "",
            }
            if col.get("primary"):
                column_entry["primary"] = True
            pii_flag = col.get("pii")
            if pii_flag or (detect_pii and self._is_pii_column(col_name, col.get("dtype") or col.get("source_type"))):
                column_entry["pii"] = True
            columns_payload.append(column_entry)

        reference_table = (
            table_meta.get("qualified_name")
            or table_meta.get("full_name")
            or table_meta.get("name")
        )

        entity: Dict[str, Any] = {
            "name": safe_name,
            "grain": grain,
            "description": table_meta.get("description") or f"Semantic entity for {reference_table}",
            "reference": {"table": reference_table},
            "columns": columns_payload,
            "tags": deduped_tags,
        }

        properties: Dict[str, Any] = {}
        if default_time_col:
            properties["default_time_col"] = default_time_col
        default_filters = table_meta.get("default_filters")
        if default_filters:
            properties["default_filters"] = default_filters
        if properties:
            entity["properties"] = properties

        return entity

    # -----------------
    # MDL CRUD: Entities
    # -----------------
    def save_entity(self, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an entity definition in MDL."""
        try:
            name = entity_data.get("name")
            if not name:
                return {"status": "error", "error": "Entity name required"}
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {"status": "error", "error": "Invalid entity name"}
            entity_file = self.mdl_root / "entities" / f"{safe_name}.yaml"
            if not str(entity_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            entity_file.parent.mkdir(parents=True, exist_ok=True)
            with open(entity_file, "w", encoding="utf-8") as f:
                yaml.dump(entity_data, f, default_flow_style=False, sort_keys=False)
            self.load()
            return {"status": "success", "name": name, "path": str(entity_file)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _is_pii_column(self, column_name: str, dtype_hint: Optional[str]) -> bool:
        """Best-effort PII detection using column names."""
        if not column_name:
            return False
        dtype = (dtype_hint or "string").lower()
        if dtype not in {"string", "text", "varchar", "nvarchar", "nchar", "char"}:
            return False
        norm = column_name.lower()
        return any(hint in norm for hint in PII_NAME_HINTS)

    def delete_entity(self, name: str) -> Dict[str, Any]:
        """Delete an entity from MDL."""
        try:
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {"status": "error", "error": "Invalid entity name"}
            entity_file = self.mdl_root / "entities" / f"{safe_name}.yaml"
            if not str(entity_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            if entity_file.exists():
                entity_file.unlink()
                self.load()
                return {"status": "success", "name": name}
            return {"status": "error", "error": "Entity not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -----------------
    # MDL CRUD: Metrics
    # -----------------
    def save_metric(self, metric_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a metric definition in MDL."""
        try:
            name = metric_data.get("name")
            if not name:
                return {"status": "error", "error": "Metric name required"}
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {"status": "error", "error": "Invalid metric name"}
            metric_file = self.mdl_root / "metrics" / f"{safe_name}.yaml"
            if not str(metric_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            metric_file.parent.mkdir(parents=True, exist_ok=True)
            with open(metric_file, "w", encoding="utf-8") as f:
                yaml.dump(metric_data, f, default_flow_style=False, sort_keys=False)
            self.load()
            return {"status": "success", "name": name, "path": str(metric_file)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def delete_metric(self, name: str) -> Dict[str, Any]:
        """Delete a metric from MDL."""
        try:
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {"status": "error", "error": "Invalid metric name"}
            metric_file = self.mdl_root / "metrics" / f"{safe_name}.yaml"
            if not str(metric_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            if metric_file.exists():
                metric_file.unlink()
                self.load()
                return {"status": "success", "name": name}
            return {"status": "error", "error": "Metric not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -----------------
    # MDL Validation & Snapshot
    # -----------------
    def validate_mdl(self) -> Dict[str, Any]:
        """Validate references across entities, metrics, and relations."""
        errors: List[str] = []
        warnings: List[str] = []

        # Validate relations reference existing models/columns
        for rel_name, rel in self.relations.items():
            f_model = rel.get("from", {}).get("model")
            f_col = rel.get("from", {}).get("column")
            t_model = rel.get("to", {}).get("model")
            t_col = rel.get("to", {}).get("column")
            if f_model and f_model not in self.entities:
                errors.append(f"relation {rel_name}: from.model '{f_model}' not found")
            if t_model and t_model not in self.entities:
                errors.append(f"relation {rel_name}: to.model '{t_model}' not found")
            if f_model in self.entity_columns and f_col and f_col not in self.entity_columns[f_model]:
                errors.append(f"relation {rel_name}: from.column '{f_col}' not in entity '{f_model}'")
            if t_model in self.entity_columns and t_col and t_col not in self.entity_columns[t_model]:
                errors.append(f"relation {rel_name}: to.column '{t_col}' not in entity '{t_model}'")

        # Validate metrics reference existing entities
        for metric_name, metric in self.metrics.items():
            ent = metric.get("entity")
            if ent and ent not in self.entities:
                errors.append(f"metric {metric_name}: entity '{ent}' not found")
            if not metric.get("sql"):
                warnings.append(f"metric {metric_name}: missing SQL")

        return {"status": "ok" if not errors else "invalid", "errors": errors, "warnings": warnings}

    def snapshot(self) -> Dict[str, Any]:
        """Return a full MDL snapshot in memory (entities, metrics, relations, policies)."""
        return {
            "entities": self.entities,
            "metrics": self.metrics,
            "relations": self.relations,
            "policies": self.policies,
            "graph": self.build_graph(),
        }
    def save_relation(self, relation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a new or updated relation to MDL.

        Args:
            relation_data: Relation definition

        Returns:
            Status dict
        """
        try:
            name = relation_data.get("name")
            if not name:
                return {"status": "error", "error": "Relation name required"}

            # Sanitize filename to prevent path traversal attacks
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {
                    "status": "error", 
                    "error": "Invalid relation name. Only alphanumeric characters, underscores, and hyphens allowed."
                }

            # Save to YAML file
            relation_file = self.mdl_root / "relations" / f"{safe_name}.yaml"
            
            # Verify the resolved path is still within mdl_root (extra safety check)
            if not str(relation_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            
            with open(relation_file, "w", encoding="utf-8") as f:
                yaml.dump(relation_data, f, default_flow_style=False, sort_keys=False)

            # Reload to update graph
            self.load()

            return {"status": "success", "name": name, "path": str(relation_file)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def delete_relation(self, name: str) -> Dict[str, Any]:
        """
        Delete a relation from MDL.

        Args:
            name: Relation name

        Returns:
            Status dict
        """
        try:
            # Sanitize filename to prevent path traversal attacks
            safe_name = self._sanitize_filename(name)
            if not safe_name or safe_name != name:
                return {
                    "status": "error",
                    "error": "Invalid relation name. Only alphanumeric characters, underscores, and hyphens allowed."
                }
            
            relation_file = self.mdl_root / "relations" / f"{safe_name}.yaml"
            
            # Verify the resolved path is still within mdl_root (extra safety check)
            if not str(relation_file.resolve()).startswith(str(self.mdl_root.resolve())):
                return {"status": "error", "error": "Invalid file path"}
            
            if relation_file.exists():
                relation_file.unlink()
                # Reload to update graph
                self.load()
                return {"status": "success", "name": name}
            else:
                return {"status": "error", "error": "Relation not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


