import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const SCHEMA_PATH = path.resolve("../backend/openapi.json");
const TYPES_OUT_PATH = path.resolve("./src/types/api.d.ts");
const BACKEND_URL = "http://localhost:8000/openapi.json";

async function generateTypes(): Promise<void> {
  if (fs.existsSync(SCHEMA_PATH)) {
    console.log("Usando schema estático:", SCHEMA_PATH);
  } else {
    try {
      console.log("Schema estático não encontrado. Gerando a partir do backend...");
      execSync(
        "python3 -m uv run python3 -c \"import json; from app.main import app; print(json.dumps(app.openapi()))\" > openapi.json",
        {
          stdio: "inherit",
          cwd: path.resolve("../backend")
        }
      );
    } catch {
      console.log("Falha ao gerar localmente. Tentando buscar do servidor...");
      const res = await fetch(BACKEND_URL);
      if (!res.ok) {
        throw new Error(`Servidor não disponível em ${BACKEND_URL}`);
      }
      const schema = await res.text();
      fs.writeFileSync(SCHEMA_PATH, schema, { encoding: "utf-8" });
      console.log("Schema baixado e salvo em:", SCHEMA_PATH);
    }
  }

  execSync(`npx openapi-typescript ${SCHEMA_PATH} -o ${TYPES_OUT_PATH}`, {
    stdio: "inherit"
  });
  console.log("Tipos gerados em:", TYPES_OUT_PATH);
}

generateTypes().catch((err) => {
  console.error(err);
  process.exit(1);
});
