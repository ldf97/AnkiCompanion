// Railway Infrastructure as Code (new service format, not deprecated railway.json).
// One replica only: the app uses a local SQLite WAL and immutable skin packages.
// Never lower volume sizes, rename, detach or recreate the existing volumes.
import { defineRailway, github, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const data = volume("ankicompanion-data", {
    region: "us-east4-eqdc4a",
    sizeMB: 1024,
  });
  const backups = volume("ankicompanion-backups", {
    region: "us-east4-eqdc4a",
    sizeMB: 1024,
  });
  const api = service("AnkiCompanion Server", {
    source: github("ldf97/AnkiCompanion", { branch: "main" }),
    start: "python -m server.launch --host 0.0.0.0 --data /data",
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: 1,
    volumeMounts: {
      "/data": data,
      "/backups": backups,
    },
    env: {
      PORT: "8765",
      ANKI_COMPANION_DATA: "/data",
      ANKI_COMPANION_BACKUPS: "/backups",
      RAILWAY_DOCKERFILE_PATH: "server/Dockerfile",
    },
  });
  return project("AnkiCompanion", { resources: [api, data, backups] });
});
