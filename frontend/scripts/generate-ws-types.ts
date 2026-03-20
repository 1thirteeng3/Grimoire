import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const WS_SCHEMA_PATH = path.resolve("../backend/ws_events_schema.json");
const WS_TYPES_OUT_PATH = path.resolve("./src/types/ws_events.d.ts");

function generateWsTypes(): void {
  if (!fs.existsSync(WS_SCHEMA_PATH)) {
    throw new Error(`Schema WS não encontrado em ${WS_SCHEMA_PATH}. Execute: make export-ws-schema`);
  }
  execSync(`npx openapi-typescript ${WS_SCHEMA_PATH} -o ${WS_TYPES_OUT_PATH}`, {
    stdio: "inherit"
  });
  console.log("Tipos WS gerados em:", WS_TYPES_OUT_PATH);
}

try {
  generateWsTypes();
} catch (err) {
  console.error(err);
  process.exit(1);
}
