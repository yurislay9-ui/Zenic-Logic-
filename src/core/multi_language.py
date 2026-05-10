"""
MultiLanguage — Generate code in TypeScript, Go, and Kotlin from YAML entities.

Problem: All generated code is Python-only. Many users need APIs in
TypeScript (Express/NestJS), Go (Gin), or Kotlin (Spring/Ktor).

Solution: MultiLanguage takes entity definitions from niche YAML files
and generates complete API projects in multiple languages:
  - TypeScript: Express + TypeORM + Swagger
  - Go: Gin + GORM + Swagger
  - Kotlin: Spring Boot + JPA + Swagger

M10 Implementation: Uses entity field types from YAML, maps them to
target language types, and generates complete CRUD services.
No external APIs needed — pure code generation.
"""

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Type mapping: YAML → target language ──
TYPE_MAP = {
    "typescript": {
        "str": "string", "string": "string", "text": "string",
        "int": "number", "integer": "number", "number": "number",
        "float": "number", "decimal": "number", "double": "number",
        "bool": "boolean", "boolean": "boolean",
        "date": "Date", "datetime": "Date",
        "uuid": "string",
        "list": "any[]", "array": "any[]", "json": "any",
        "email": "string", "url": "string", "phone": "string",
    },
    "go": {
        "str": "string", "string": "string", "text": "string",
        "int": "int", "integer": "int", "number": "int",
        "float": "float64", "decimal": "float64", "double": "float64",
        "bool": "bool", "boolean": "bool",
        "date": "time.Time", "datetime": "time.Time",
        "uuid": "string",
        "list": "[]interface{}", "array": "[]interface{}", "json": "map[string]interface{}",
        "email": "string", "url": "string", "phone": "string",
    },
    "kotlin": {
        "str": "String", "string": "String", "text": "String",
        "int": "Int", "integer": "Int", "number": "Int",
        "float": "Double", "decimal": "Double", "double": "Double",
        "bool": "Boolean", "boolean": "Boolean",
        "date": "LocalDate", "datetime": "LocalDateTime",
        "uuid": "UUID",
        "list": "List<Any>", "array": "List<Any>", "json": "Map<String, Any>",
        "email": "String", "url": "String", "phone": "String",
    },
}


class MultiLanguage:
    """Generate API projects in TypeScript, Go, and Kotlin."""

    def generate_project(self, entities: List[Dict], project_name: str,
                          language: str, description: str = "") -> Dict[str, str]:
        """Generate a complete API project in the target language.

        Args:
            entities: List of entity dicts with name + fields
            project_name: Name for the project
            language: "typescript", "go", or "kotlin"
            description: Project description

        Returns:
            Dict mapping filename → file content
        """
        if language == "typescript":
            return self._generate_typescript(entities, project_name, description)
        elif language == "go":
            return self._generate_go(entities, project_name, description)
        elif language == "kotlin":
            return self._generate_kotlin(entities, project_name, description)
        else:
            logger.warning(f"MultiLanguage: Unsupported language '{language}', falling back to TypeScript")
            return self._generate_typescript(entities, project_name, description)

    def _parse_fields(self, fields: list, language: str) -> List[Dict]:
        """Parse entity fields from YAML format.

        YAML fields are strings like "name:str", "price:decimal", "id:uuid"
        """
        parsed = []
        type_map = TYPE_MAP.get(language, TYPE_MAP["typescript"])

        for field_def in fields:
            if isinstance(field_def, str) and ":" in field_def:
                parts = field_def.split(":", 1)
                name = parts[0].strip()
                yaml_type = parts[1].strip().lower()
                target_type = type_map.get(yaml_type, "string" if language != "go" else "string")
                parsed.append({"name": name, "yaml_type": yaml_type, "type": target_type})
            elif isinstance(field_def, dict):
                name = field_def.get("name", "field")
                yaml_type = field_def.get("type", "str").lower()
                target_type = type_map.get(yaml_type, "string" if language != "go" else "string")
                parsed.append({"name": name, "yaml_type": yaml_type, "type": target_type})

        return parsed

    # ================================================================
    #  TYPESCRIPT (Express + TypeORM + Swagger)
    # ================================================================

    def _generate_typescript(self, entities: List[Dict], project_name: str,
                              description: str) -> Dict[str, str]:
        """Generate TypeScript Express project."""
        files = {}

        # package.json
        files["package.json"] = self._ts_package(project_name, description)

        # tsconfig.json
        files["tsconfig.json"] = self._ts_tsconfig()

        # Entity models
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "typescript")
            files[f"src/models/{name.lower()}.model.ts"] = self._ts_model(name, fields)
            files[f"src/services/{name.lower()}.service.ts"] = self._ts_service(name, fields)
            files[f"src/routes/{name.lower()}.routes.ts"] = self._ts_routes(name)

        # Main app
        files["src/app.ts"] = self._ts_app(project_name, entities)

        # Database config
        files["src/config/database.ts"] = self._ts_database_config()

        # Docker
        files["Dockerfile"] = self._ts_dockerfile(project_name)

        return files

    def _ts_package(self, name: str, desc: str) -> str:
        return f'''{{
  "name": "{name}",
  "version": "1.0.0",
  "description": "{desc or name}",
  "main": "dist/app.js",
  "scripts": {{
    "build": "tsc",
    "start": "node dist/app.js",
    "dev": "ts-node-dev src/app.ts"
  }},
  "dependencies": {{
    "express": "^4.18.0",
    "typeorm": "^0.3.0",
    "better-sqlite3": "^9.0.0",
    "cors": "^2.8.5",
    "helmet": "^7.0.0",
    "swagger-ui-express": "^5.0.0",
    "class-validator": "^0.14.0",
    "class-transformer": "^0.5.0"
  }},
  "devDependencies": {{
    "typescript": "^5.3.0",
    "@types/express": "^4.17.0",
    "@types/cors": "^2.8.0",
    "ts-node-dev": "^2.0.0"
  }}
}}
'''

    def _ts_tsconfig(self) -> str:
        return '''{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
'''

    def _ts_model(self, name: str, fields: List[Dict]) -> str:
        props = "\n".join(
            f"  {f['name']}: {f['type']};" for f in fields
        )
        return f'''import {{ Entity, PrimaryGeneratedColumn, Column }} from "typeorm";

@Entity("{name.lower()}s")
export class {name} {{
{props}
}}
'''

    def _ts_service(self, name: str, fields: List[Dict]) -> str:
        return f'''import {{ AppDataSource }} from "../config/database";
import {{ {name} }} from "../models/{name.lower()}.model";

export class {name}Service {{
  private repo = AppDataSource.getRepository({name});

  async create(data: Partial<{name}>): Promise<{name}> {{
    const item = this.repo.create(data);
    return await this.repo.save(item);
  }}

  async findById(id: number): Promise<{name} | null> {{
    return await this.repo.findOneBy({{ id }} as any);
  }}

  async findAll(limit: number = 50, offset: number = 0): Promise<{name}[]> {{
    return await this.repo.find({{ take: limit, skip: offset }});
  }}

  async update(id: number, data: Partial<{name}>): Promise<{name} | null> {{
    await this.repo.update(id, data as any);
    return await this.findById(id);
  }}

  async delete(id: number): Promise<boolean> {{
    const result = await this.repo.delete(id);
    return (result.affected ?? 0) > 0;
  }}
}}
'''

    def _ts_routes(self, name: str) -> str:
        return f'''import {{ Router, Request, Response }} from "express";
import {{ {name}Service }} from "../services/{name.lower()}.service";

const router = Router();
const service = new {name}Service();

router.post("/", async (req: Request, res: Response) => {{
  try {{
    const item = await service.create(req.body);
    res.status(201).json(item);
  }} catch (error) {{
    res.status(400).json({{ error: (error as Error).message }});
  }}
}});

router.get("/", async (req: Request, res: Response) => {{
  try {{
    const limit = parseInt(req.query.limit as string) || 50;
    const offset = parseInt(req.query.offset as string) || 0;
    const items = await service.findAll(limit, offset);
    res.json(items);
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

router.get("/:id", async (req: Request, res: Response) => {{
  try {{
    const item = await service.findById(parseInt(req.params.id));
    if (!item) return res.status(404).json({{ error: "{name} not found" }});
    res.json(item);
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

router.put("/:id", async (req: Request, res: Response) => {{
  try {{
    const item = await service.update(parseInt(req.params.id), req.body);
    if (!item) return res.status(404).json({{ error: "{name} not found" }});
    res.json(item);
  }} catch (error) {{
    res.status(400).json({{ error: (error as Error).message }});
  }}
}});

router.delete("/:id", async (req: Request, res: Response) => {{
  try {{
    const success = await service.delete(parseInt(req.params.id));
    if (!success) return res.status(404).json({{ error: "{name} not found" }});
    res.json({{ success: true }});
  }} catch (error) {{
    res.status(500).json({{ error: (error as Error).message }});
  }}
}});

export default router;
'''

    def _ts_app(self, project_name: str, entities: List[Dict]) -> str:
        imports = [f'import {e["name"].lower()}Routes from "./routes/{e["name"].lower()}.routes";'
                   for e in entities]
        uses = [f'app.use("/v1/{e["name"].lower()}s", {e["name"].lower()}Routes);'
                for e in entities]
        return f'''import express from "express";
import cors from "cors";
import helmet from "helmet";
import {{ AppDataSource }} from "./config/database";
{chr(10).join(imports)}

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json());

{chr(10).join(uses)}

app.get("/health", (req, res) => {{
  res.json({{ status: "ok", service: "{project_name}" }});
}});

AppDataSource.initialize()
  .then(() => {{
    app.listen(PORT, () => {{
      console.log(`{project_name} running on port ${{PORT}}`);
    }});
  }})
  .catch((error) => {{
    console.error("Database connection failed:", error);
    process.exit(1);
  }});

export default app;
'''

    def _ts_database_config(self) -> str:
        return '''import { DataSource } from "typeorm";

export const AppDataSource = new DataSource({
  type: "better-sqlite3",
  database: process.env.DB_PATH || "data.sqlite",
  synchronize: true,
  logging: false,
  entities: ["src/models/**/*.model.ts"],
});
'''

    def _ts_dockerfile(self, name: str) -> str:
        return f'''FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY dist ./dist
EXPOSE 3000
CMD ["node", "dist/app.js"]
'''

    # ================================================================
    #  GO (Gin + GORM + Swagger)
    # ================================================================

    def _generate_go(self, entities: List[Dict], project_name: str,
                      description: str) -> Dict[str, str]:
        """Generate Go Gin project."""
        files = {}
        mod_name = project_name.lower().replace("-", "_")

        # go.mod
        files["go.mod"] = f'''module {mod_name}

go 1.21

require (
\tgithub.com/gin-gonic/gin v1.9.1
\tgorm.io/gorm v1.25.0
\tgorm.io/driver/sqlite v1.5.0
)
'''

        # Models
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "go")
            files[f"models/{name.lower()}.go"] = self._go_model(name, fields, mod_name)
            files[f"handlers/{name.lower()}.go"] = self._go_handler(name, mod_name)

        # main.go
        files["main.go"] = self._go_main(project_name, entities, mod_name)

        # Dockerfile
        files["Dockerfile"] = self._go_dockerfile(mod_name)

        return files

    def _go_model(self, name: str, fields: List[Dict], mod_name: str) -> str:
        field_defs = "\n".join(
            f"\t{f['name'].capitalize()} {f['type']} `json:\"{f['name']}\" gorm:\"column:{f['name']}\"`"
            for f in fields
        )
        return f'''package models

import "time"

// {name} model
type {name} struct {{
{field_defs}
}}

// TableName overrides the table name
func ({name}) TableName() string {{
\treturn "{name.lower()}s"
}}
'''

    def _go_handler(self, name: str, mod_name: str) -> str:
        return f'''package handlers

import (
\t"net/http"
\t"strconv"
\t"{mod_name}/models"
\t"github.com/gin-gonic/gin"
\t"gorm.io/gorm"
)

type {name}Handler struct {{
\tDB *gorm.DB
}}

func New{name}Handler(db *gorm.DB) *{name}Handler {{
\treturn &{name}Handler{{DB: db}}
}}

func (h *{name}Handler) Create(c *gin.Context) {{
\tvar item models.{name}
\tif err := c.ShouldBindJSON(&item); err != nil {{
\t\tc.JSON(http.StatusBadRequest, gin.H{{"error": err.Error()}})
\t\treturn
\t}}
\th.DB.Create(&item)
\tc.JSON(http.StatusCreated, item)
}}

func (h *{name}Handler) GetByID(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\tvar item models.{name}
\tif err := h.DB.First(&item, id).Error; err != nil {{
\t\tc.JSON(http.StatusNotFound, gin.H{{"error": "{name} not found"}})
\t\treturn
\t}}
\tc.JSON(http.StatusOK, item)
}}

func (h *{name}Handler) List(c *gin.Context) {{
\tlimit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
\toffset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
\tvar items []models.{name}
\th.DB.Limit(limit).Offset(offset).Find(&items)
\tc.JSON(http.StatusOK, items)
}}

func (h *{name}Handler) Update(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\tvar item models.{name}
\tif err := h.DB.First(&item, id).Error; err != nil {{
\t\tc.JSON(http.StatusNotFound, gin.H{{"error": "{name} not found"}})
\t\treturn
\t}}
\tc.ShouldBindJSON(&item)
\th.DB.Save(&item)
\tc.JSON(http.StatusOK, item)
}}

func (h *{name}Handler) Delete(c *gin.Context) {{
\tid, _ := strconv.Atoi(c.Param("id"))
\th.DB.Delete(&models.{name}{{}}, id)
\tc.JSON(http.StatusOK, gin.H{{"success": true}})
}}
'''

    def _go_main(self, project_name: str, entities: List[Dict], mod_name: str) -> str:
        imports = [f'\t"{mod_name}/handlers"' for _ in entities]
        routes = []
        for e in entities:
            name = e.get("name", "Item")
            routes.append(f'\t{name.lower()}Handler := handlers.New{name}Handler(db)')
            routes.append(f'\tv1.GET("/{name.lower()}s", {name.lower()}Handler.List)')
            routes.append(f'\tv1.GET("/{name.lower()}s/:id", {name.lower()}Handler.GetByID)')
            routes.append(f'\tv1.POST("/{name.lower()}s", {name.lower()}Handler.Create)')
            routes.append(f'\tv1.PUT("/{name.lower()}s/:id", {name.lower()}Handler.Update)')
            routes.append(f'\tv1.DELETE("/{name.lower()}s/:id", {name.lower()}Handler.Delete)')

        return f'''package main

import (
\t"{mod_name}/models"
\t"github.com/gin-gonic/gin"
\t"gorm.io/driver/sqlite"
\t"gorm.io/gorm"
{chr(10).join(set(imports))}
)

func main() {{
\tdb, err := gorm.Open(sqlite.Open("data.sqlite"), &gorm.Config{{}})
\tif err != nil {{
\t\tpanic("failed to connect database")
\t}}
{chr(10).join([f"\tdb.AutoMigrate(&models.{e['name']}{{}})" for e in entities])}

\tr := gin.Default()
\tv1 := r.Group("/v1")
\t{{
{chr(10).join(routes)}
\t}}

\tr.GET("/health", func(c *gin.Context) {{
\t\tc.JSON(200, gin.H{{"status": "ok", "service": "{project_name}"}})
\t}})

\tr.Run(":3000")
}}
'''

    def _go_dockerfile(self, mod_name: str) -> str:
        return f'''FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=1 go build -o /app/server .

FROM alpine:3.18
RUN apk add --no-cache gcc musl-dev
COPY --from=builder /app/server /app/server
EXPOSE 3000
CMD ["/app/server"]
'''

    # ================================================================
    #  KOTLIN (Spring Boot + JPA)
    # ================================================================

    def _generate_kotlin(self, entities: List[Dict], project_name: str,
                          description: str) -> Dict[str, str]:
        """Generate Kotlin Spring Boot project."""
        files = {}
        pkg = project_name.lower().replace("-", ".")

        # build.gradle.kts
        files["build.gradle.kts"] = self._kt_build(project_name)

        # Application main
        files["src/main/kotlin/Application.kt"] = self._kt_main(project_name, pkg)

        # Entity + Repository + Service + Controller for each entity
        for entity in entities:
            name = entity.get("name", "Item")
            fields = self._parse_fields(entity.get("fields", []), "kotlin")
            base = f"src/main/kotlin/{pkg.replace('.', '/')}"
            files[f"{base}/models/{name}.kt"] = self._kt_model(name, fields, pkg)
            files[f"{base}/repositories/{name}Repository.kt"] = self._kt_repository(name, pkg)
            files[f"{base}/services/{name}Service.kt"] = self._kt_service(name, pkg)
            files[f"{base}/controllers/{name}Controller.kt"] = self._kt_controller(name, pkg)

        return files

    def _kt_build(self, name: str) -> str:
        return f'''plugins {{
\tkotlin("jvm") version "1.9.20"
\tkotlin("plugin.spring") version "1.9.20"
\tkotlin("plugin.jpa") version "1.9.20"
\tid("org.springframework.boot") version "3.2.0"
\tid("io.spring.dependency-management") version "1.1.4"
}}

group = "{name.lower()}"
version = "1.0.0"

dependencies {{
\timplementation("org.springframework.boot:spring-boot-starter-web")
\timplementation("org.springframework.boot:spring-boot-starter-data-jpa")
\timplementation("org.springframework.boot:spring-boot-starter-validation")
\timplementation("com.fasterxml.jackson.module:jackson-module-kotlin")
\timplementation("org.jetbrains.kotlin:kotlin-reflect")
\truntimeOnly("com.h2database:h2")
\ttestImplementation("org.springframework.boot:spring-boot-starter-test")
}}
'''

    def _kt_main(self, name: str, pkg: str) -> str:
        return f'''package {pkg}

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class Application

fun main(args: Array<String>) {{
\trunApplication<Application>(*args)
}}
'''

    def _kt_model(self, name: str, fields: List[Dict], pkg: str) -> str:
        props = "\n".join(
            f'\tval {f["name"]}: {f["type"]}' + ('? = null' if f["name"] != "id" else ' = null')
            for f in fields
        )
        return f'''package {pkg}.models

import jakarta.persistence.*

@Entity
@Table(name = "{name.lower()}s")
data class {name}(
{props}
)
'''

    def _kt_repository(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.repositories

import {pkg}.models.{name}
import org.springframework.data.jpa.repository.JpaRepository
import org.springframework.stereotype.Repository

@Repository
interface {name}Repository : JpaRepository<{name}, Long>
'''

    def _kt_service(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.services

import {pkg}.models.{name}
import {pkg}.repositories.{name}Repository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service

@Service
class {name}Service(private val repository: {name}Repository) {{

\tfun findAll(limit: Int = 50, offset: Int = 0): List<{name}> =
\t\trepository.findAll(PageRequest.of(offset / limit, limit)).content

\tfun findById(id: Long): {name}? = repository.findById(id).orElse(null)

\tfun create(item: {name}): {name} = repository.save(item)

\tfun update(id: Long, item: {name}): {name}? {{
\t\treturn if (repository.existsById(id)) repository.save(item) else null
\t}}

\tfun delete(id: Long): Boolean {{
\t\treturn if (repository.existsById(id)) {{ repository.deleteById(id); true }} else false
\t}}
}}
'''

    def _kt_controller(self, name: str, pkg: str) -> str:
        return f'''package {pkg}.controllers

import {pkg}.models.{name}
import {pkg}.services.{name}Service
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*

@RestController
@RequestMapping("/v1/{name.lower()}s")
class {name}Controller(private val service: {name}Service) {{

\t@GetMapping
\tfun list(@RequestParam(defaultValue = "50") limit: Int,
\t          @RequestParam(defaultValue = "0") offset: Int): List<{name}> =
\t\tservice.findAll(limit, offset)

\t@GetMapping("/{{id}}")
\tfun getById(@PathVariable id: Long): ResponseEntity<{name}> =
\t\tservice.findById(id)?.let {{ ResponseEntity.ok(it) }}
\t\t\t?: ResponseEntity.notFound().build()

\t@PostMapping
\tfun create(@RequestBody item: {name}): ResponseEntity<{name}> =
\t\tResponseEntity.status(HttpStatus.CREATED).body(service.create(item))

\t@PutMapping("/{{id}}")
\tfun update(@PathVariable id: Long, @RequestBody item: {name}): ResponseEntity<{name}> =
\t\tservice.update(id, item)?.let {{ ResponseEntity.ok(it) }}
\t\t\t?: ResponseEntity.notFound().build()

\t@DeleteMapping("/{{id}}")
\tfun delete(@PathVariable id: Long): ResponseEntity<Map<String, Boolean>> =
\t\tif (service.delete(id)) ResponseEntity.ok(mapOf("success" to true))
\t\telse ResponseEntity.notFound().build()
}}
'''
