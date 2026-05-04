"""
TITAN OMNISCALE X - SchemaDesigner Unit Tests

Tests for src/core/schema_designer.py:
  - Schema generation from descriptions
  - SQL DDL generation
  - Python model generation
  - Migration generation
  - Fallback entity extraction
"""

import pytest
from unittest.mock import MagicMock, patch

from src.core.schema_designer import (
    SchemaDesigner, SchemaDef, TableDef, ColumnDef,
    PYTHON_TO_SQL, SQL_TO_PYTHON, _sanitize_identifier,
)


# ============================================================
#  HELPER: Build a simple schema for reuse
# ============================================================

def _make_customer_product_schema():
    """Create a sample schema with Customer and Product tables."""
    customer_table = TableDef(
        name="customer",
        columns=[
            ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                      primary_key=True, autoincrement=True, nullable=False),
            ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=False),
            ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=True),
            ColumnDef(name="name", sql_type="TEXT", python_type="str",
                      nullable=True, index=True),
            ColumnDef(name="email", sql_type="TEXT", python_type="str",
                      nullable=True, unique=True),
        ],
        indexes=["idx_customer_name"],
        description="Table for Customer",
    )
    product_table = TableDef(
        name="product",
        columns=[
            ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                      primary_key=True, autoincrement=True, nullable=False),
            ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=False),
            ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                      default="CURRENT_TIMESTAMP", nullable=True),
            ColumnDef(name="name", sql_type="TEXT", python_type="str",
                      nullable=True, index=True),
            ColumnDef(name="sku", sql_type="TEXT", python_type="str",
                      nullable=True, unique=True),
            ColumnDef(name="price", sql_type="REAL", python_type="float",
                      nullable=True),
        ],
        indexes=["idx_product_name"],
        description="Table for Product",
    )
    return SchemaDef(tables=[customer_table, product_table], name="test_db", version=1)


# ============================================================
#  SANITIZE IDENTIFIER TESTS
# ============================================================

class TestSanitizeIdentifier:
    """Tests for the _sanitize_identifier helper."""

    def test_valid_identifier(self):
        """Valid identifiers should be double-quoted."""
        result = _sanitize_identifier("users")
        assert result == '"users"'

    def test_valid_with_underscore(self):
        """Identifiers with underscores should be accepted."""
        result = _sanitize_identifier("user_id")
        assert result == '"user_id"'

    def test_invalid_identifier_raises(self):
        """Identifiers with special chars should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _sanitize_identifier("DROP TABLE users;")

    def test_empty_identifier_raises(self):
        """Empty identifiers should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            _sanitize_identifier("")


# ============================================================
#  SCHEMA GENERATION TESTS
# ============================================================

class TestSchemaDesignerGeneration:
    """Tests for SchemaDesigner.design_schema()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_design_schema_with_entity_hints(self):
        """Should produce schema from explicit entity hints."""
        entities = [
            {"name": "Customer", "fields": ["name:str", "email:str", "age:int"]},
        ]
        schema = self.designer.design_schema("customer system", entity_hints=entities)
        assert isinstance(schema, SchemaDef)
        assert len(schema.tables) >= 1
        assert schema.tables[0].name == "customer"

    def test_design_schema_fallback_no_thinking(self):
        """Without thinking_engine, should use fallback entities."""
        schema = self.designer.design_schema("sistema de inventario y productos")
        assert isinstance(schema, SchemaDef)
        assert len(schema.tables) >= 1
        # Should detect "producto"/"inventario" keywords
        table_names = [t.name for t in schema.tables]
        assert "product" in table_names

    def test_design_schema_with_thinking_engine(self):
        """Should delegate to thinking_engine when available."""
        mock_thinking = MagicMock()
        mock_plan = MagicMock()
        mock_plan.entities = [{"name": "Invoice", "fields": ["total:float", "status:str"]}]
        mock_thinking.plan_generation.return_value = mock_plan

        designer = SchemaDesigner(thinking_engine=mock_thinking)
        schema = designer.design_schema("sistema de facturacion")

        mock_thinking.plan_generation.assert_called_once_with("sistema de facturacion")
        assert len(schema.tables) >= 1
        assert schema.tables[0].name == "invoice"

    def test_design_schema_extracts_db_name(self):
        """Schema name should be extracted from description."""
        schema = self.designer.design_schema(
            "CRM system",
            entity_hints=[{"name": "Item", "fields": ["name:str"]}],
        )
        assert schema.name != "app"
        assert len(schema.name) > 0


# ============================================================
#  ENTITY-TO-TABLE CONVERSION TESTS
# ============================================================

class TestEntityToTable:
    """Tests for SchemaDesigner._entity_to_table()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_adds_default_id_column(self):
        """Every table should have an auto-increment id column."""
        table = self.designer._entity_to_table({"name": "Test", "fields": []})
        id_col = [c for c in table.columns if c.primary_key]
        assert len(id_col) == 1
        assert id_col[0].name == "id"
        assert id_col[0].autoincrement is True

    def test_adds_timestamp_columns(self):
        """Every table should have created_at and updated_at columns."""
        table = self.designer._entity_to_table({"name": "Test", "fields": []})
        col_names = [c.name for c in table.columns]
        assert "created_at" in col_names
        assert "updated_at" in col_names

    def test_detects_foreign_keys(self):
        """Fields ending with _id should be detected as foreign keys."""
        table = self.designer._entity_to_table(
            {"name": "Invoice", "fields": ["customer_id:int", "total:float"]}
        )
        fk_cols = [c for c in table.columns if c.foreign_key]
        assert len(fk_cols) == 1
        assert fk_cols[0].foreign_key == "customer.id"

    def test_unique_fields_detected(self):
        """Fields like email, sku should be marked unique."""
        table = self.designer._entity_to_table(
            {"name": "User", "fields": ["email:str", "username:str"]}
        )
        unique_cols = [c for c in table.columns if c.unique]
        unique_names = [c.name for c in unique_cols]
        assert "email" in unique_names

    def test_sql_type_mapping(self):
        """Python types should map to SQL types correctly."""
        table = self.designer._entity_to_table(
            {"name": "Test", "fields": ["count:int", "price:float", "active:bool"]}
        )
        col_map = {c.name: c for c in table.columns}
        assert col_map["count"].sql_type == "INTEGER"
        assert col_map["price"].sql_type == "REAL"
        assert col_map["active"].sql_type == "INTEGER"


# ============================================================
#  SQL GENERATION TESTS
# ============================================================

class TestSQLGeneration:
    """Tests for SchemaDesigner.generate_sql() and generate_init_sql()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)
        self.schema = _make_customer_product_schema()

    def test_generate_sql_creates_tables(self):
        """generate_sql should produce CREATE TABLE statements."""
        sql = self.designer.generate_sql(self.schema)
        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert '"customer"' in sql
        assert '"product"' in sql

    def test_generate_sql_primary_key(self):
        """SQL should include PRIMARY KEY AUTOINCREMENT."""
        sql = self.designer.generate_sql(self.schema)
        assert "PRIMARY KEY AUTOINCREMENT" in sql

    def test_generate_sql_not_null(self):
        """SQL should include NOT NULL for non-nullable columns."""
        sql = self.designer.generate_sql(self.schema)
        assert "NOT NULL" in sql

    def test_generate_sql_unique_constraint(self):
        """SQL should include UNIQUE for unique columns."""
        sql = self.designer.generate_sql(self.schema)
        assert "UNIQUE" in sql

    def test_generate_sql_default_values(self):
        """SQL should include DEFAULT for columns with defaults."""
        sql = self.designer.generate_sql(self.schema)
        assert "CURRENT_TIMESTAMP" in sql

    def test_generate_sql_indexes(self):
        """SQL should include CREATE INDEX statements."""
        sql = self.designer.generate_sql(self.schema)
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert "idx_customer_name" in sql

    def test_generate_init_sql_includes_seed_data(self):
        """generate_init_sql should include INSERT statements for seed data."""
        sql = self.designer.generate_init_sql(self.schema)
        assert "INSERT OR IGNORE INTO" in sql

    def test_generate_init_sql_user_table_admin_seed(self):
        """User/admin tables should get an admin seed row."""
        user_table = TableDef(
            name="users",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                          primary_key=True, autoincrement=True),
                ColumnDef(name="created_at", sql_type="TEXT", python_type="str",
                          default="CURRENT_TIMESTAMP"),
                ColumnDef(name="updated_at", sql_type="TEXT", python_type="str",
                          default="CURRENT_TIMESTAMP", nullable=True),
                ColumnDef(name="username", sql_type="TEXT", python_type="str"),
                ColumnDef(name="email", sql_type="TEXT", python_type="str", unique=True),
            ],
            description="Users table",
        )
        schema = SchemaDef(tables=[user_table], name="test")
        sql = self.designer.generate_init_sql(schema)
        assert "Admin" in sql
        assert "admin@company.com" in sql


# ============================================================
#  PYTHON MODEL GENERATION TESTS
# ============================================================

class TestModelGeneration:
    """Tests for SchemaDesigner.generate_models()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)
        self.schema = _make_customer_product_schema()

    def test_generate_models_produces_classes(self):
        """generate_models should produce dataclass definitions."""
        code = self.designer.generate_models(self.schema)
        assert "@dataclass" in code
        assert "class Customer:" in code
        assert "class Product:" in code

    def test_generate_models_includes_to_dict(self):
        """Models should have a to_dict() method."""
        code = self.designer.generate_models(self.schema)
        assert "def to_dict(self)" in code

    def test_generate_models_includes_from_row(self):
        """Models should have a from_row() classmethod."""
        code = self.designer.generate_models(self.schema)
        assert "def from_row(cls" in code

    def test_generate_models_includes_imports(self):
        """Models should include necessary imports."""
        code = self.designer.generate_models(self.schema)
        assert "from dataclasses import" in code
        assert "from typing import" in code


# ============================================================
#  MIGRATION GENERATION TESTS
# ============================================================

class TestMigrationGeneration:
    """Tests for SchemaDesigner.generate_migration()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_new_table_migration(self):
        """Should generate CREATE TABLE for new tables."""
        old_schema = SchemaDef(tables=[], name="app", version=1)
        new_schema = SchemaDef(
            tables=[TableDef(
                name="orders",
                columns=[
                    ColumnDef(name="id", sql_type="INTEGER", python_type="int",
                              primary_key=True, autoincrement=True),
                    ColumnDef(name="total", sql_type="REAL", python_type="float"),
                ],
            )],
            name="app",
        )
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "New table: orders" in migration
        assert "CREATE TABLE IF NOT EXISTS" in migration

    def test_added_column_migration(self):
        """Should generate ALTER TABLE ADD COLUMN for new columns."""
        old_table = TableDef(
            name="customer",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
                ColumnDef(name="name", sql_type="TEXT", python_type="str"),
            ],
        )
        new_table = TableDef(
            name="customer",
            columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
                ColumnDef(name="name", sql_type="TEXT", python_type="str"),
                ColumnDef(name="phone", sql_type="TEXT", python_type="str", nullable=True),
            ],
        )
        old_schema = SchemaDef(tables=[old_table], name="app", version=1)
        new_schema = SchemaDef(tables=[new_table], name="app", version=2)
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "ALTER TABLE" in migration
        assert "ADD COLUMN" in migration
        assert "phone" in migration

    def test_dropped_table_migration(self):
        """Should generate DROP TABLE for removed tables."""
        old_schema = SchemaDef(
            tables=[TableDef(name="legacy", columns=[
                ColumnDef(name="id", sql_type="INTEGER", python_type="int", primary_key=True),
            ])],
            name="app",
        )
        new_schema = SchemaDef(tables=[], name="app")
        migration = self.designer.generate_migration(old_schema, new_schema, version=2)
        assert "DROP TABLE IF EXISTS" in migration
        assert "legacy" in migration

    def test_migration_includes_version_comment(self):
        """Migration should start with a version comment."""
        old_schema = SchemaDef(tables=[], name="app")
        new_schema = SchemaDef(tables=[], name="app")
        migration = self.designer.generate_migration(old_schema, new_schema, version=3)
        assert "Migration v2 -> v3" in migration


# ============================================================
#  FALLBACK ENTITY EXTRACTION TESTS
# ============================================================

class TestFallbackEntities:
    """Tests for SchemaDesigner._fallback_entities()."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_detects_customer_keyword(self):
        """Should detect 'customer' keyword and create Customer entity."""
        entities = self.designer._fallback_entities("necesito un CRM para clientes")
        names = [e["name"] for e in entities]
        assert "Customer" in names

    def test_detects_product_keyword(self):
        """Should detect 'product' keyword and create Product entity."""
        entities = self.designer._fallback_entities("sistema de inventario y productos")
        names = [e["name"] for e in entities]
        assert "Product" in names

    def test_detects_invoice_keyword(self):
        """Should detect 'invoice' keyword and create Invoice entity."""
        entities = self.designer._fallback_entities("sistema de facturacion")
        names = [e["name"] for e in entities]
        assert "Invoice" in names

    def test_detects_user_keyword(self):
        """Should detect 'user' keyword and create User entity."""
        entities = self.designer._fallback_entities("auth and user management")
        names = [e["name"] for e in entities]
        assert "User" in names

    def test_default_item_entity(self):
        """Should return a generic Item entity for unrecognized descriptions."""
        entities = self.designer._fallback_entities("something completely unknown")
        names = [e["name"] for e in entities]
        assert "Item" in names


# ============================================================
#  RELATIONSHIP & INDEX TESTS
# ============================================================

class TestRelationshipsAndIndexes:
    """Tests for relationship detection and index generation."""

    def setup_method(self):
        self.designer = SchemaDesigner(thinking_engine=None)

    def test_missing_fk_table_created(self):
        """Referenced tables not in schema should be auto-created."""
        entities = [
            {"name": "Invoice", "fields": ["customer_id:int", "total:float"]},
        ]
        schema = self.designer.design_schema("invoice system", entity_hints=entities)
        table_names = {t.name for t in schema.tables}
        # customer table should be auto-created because customer_id FK references it
        assert "customer" in table_names

    def test_indexes_added_for_indexed_columns(self):
        """Columns with index=True should generate index entries."""
        entities = [
            {"name": "Order", "fields": ["status:str", "category:str"]},
        ]
        schema = self.designer.design_schema("orders", entity_hints=entities)
        order_table = next(t for t in schema.tables if t.name == "order")
        assert len(order_table.indexes) > 0

    def test_extract_db_name(self):
        """_extract_db_name should extract words from description."""
        name = self.designer._extract_db_name("Invoice Management System")
        assert name == "invoice_management"
