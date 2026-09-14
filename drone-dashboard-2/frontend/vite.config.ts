import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "fs";
import path from "path";
import os from "os";
import { exec } from "child_process";

// Parses multipart/form-data from a Node.js IncomingMessage.
// Returns a Promise that resolves to an array of { filename, data }.
function parseMultipart(
  req: any
): Promise<{ filename: string; data: Buffer }[]> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("error", reject);
    req.on("end", () => {
      try {
        const body = Buffer.concat(chunks);
        const contentType: string = req.headers["content-type"] || "";
        const boundaryMatch = contentType.match(/boundary=(.+)/);
        if (!boundaryMatch) return resolve([]);
        const boundary = Buffer.from("--" + boundaryMatch[1]);
        const results: { filename: string; data: Buffer }[] = [];

        let pos = 0;
        while (pos < body.length) {
          const boundaryIdx = body.indexOf(boundary, pos);
          if (boundaryIdx === -1) break;
          pos = boundaryIdx + boundary.length;
          if (body[pos] === 0x2d && body[pos + 1] === 0x2d) break; // --boundary--
          pos += 2; // skip \r\n

          // find end of headers
          const headerEnd = body.indexOf(Buffer.from("\r\n\r\n"), pos);
          if (headerEnd === -1) break;
          const headers = body.slice(pos, headerEnd).toString();
          pos = headerEnd + 4;

          // extract filename from Content-Disposition
          const filenameMatch = headers.match(/filename="([^"]+)"/);
          if (!filenameMatch) continue;
          const filename = path.basename(filenameMatch[1]);

          // find next boundary
          const nextBoundary = body.indexOf(boundary, pos);
          if (nextBoundary === -1) break;
          const data = body.slice(pos, nextBoundary - 2); // strip trailing \r\n
          results.push({ filename, data });
          pos = nextBoundary;
        }
        resolve(results);
      } catch (e) {
        reject(e);
      }
    });
  });
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "serve-seed-features-plugin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && req.url.startsWith("/seed_features/")) {
            const cleanUrl = req.url.split('?')[0];
            const filename = path.basename(cleanUrl);
            const filePath = path.join(os.homedir(), "isro", "seed_features", filename);
            if (fs.existsSync(filePath)) {
              res.setHeader("Content-Type", "image/jpeg");
              res.statusCode = 200;
              res.end(fs.readFileSync(filePath));
            } else {
              res.statusCode = 404;
              res.end("Not Found");
            }
          } else {
            next();
          }
        });
      }
    },
    {
      name: "serve-isro-plugin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && req.url.startsWith("/isro/")) {
            // Decode URL-encoded chars (spaces become %20 in browser requests)
            const cleanUrl = decodeURIComponent(req.url.split('?')[0]);
            const filename = path.basename(cleanUrl);
            const filePath = path.join(os.homedir(), "isro", filename);
            if (fs.existsSync(filePath)) {
              const ext = path.extname(filename).toLowerCase();
              const mime = ext === ".png" ? "image/png" : "image/jpeg";
              res.setHeader("Content-Type", mime);
              res.statusCode = 200;
              res.end(fs.readFileSync(filePath));
            } else {
              res.statusCode = 404;
              res.end("Not Found: " + filePath);
            }
          } else {
            next();
          }
        });
      }
    },
    {
      name: "save-zip-plugin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === "/api/save-zip" && req.method === "POST") {
            const tempZipPath = path.join(os.tmpdir(), `drone_frames_${Date.now()}.zip`);
            const writeStream = fs.createWriteStream(tempZipPath);
            req.pipe(writeStream);
            req.on("end", () => {
              const targetDir = "/Users/bikash/image_search/images";
              fs.mkdirSync(targetDir, { recursive: true });
              exec(`unzip -o "${tempZipPath}" -d "${targetDir}"`, (err, _stdout, stderr) => {
                try { fs.unlinkSync(tempZipPath); } catch (e) {}
                res.setHeader("Content-Type", "application/json");
                if (err) {
                  console.error("Unzip error:", err, stderr);
                  res.statusCode = 500;
                  res.end(JSON.stringify({ error: "Failed to unzip files", details: err.message }));
                } else {
                  let fileCount = 0;
                  try { fileCount = fs.readdirSync(targetDir).filter(f => f.endsWith(".jpg")).length; } catch (e) {}
                  res.statusCode = 200;
                  res.end(JSON.stringify({ success: true, path: targetDir, fileCount }));
                }
              });
            });
            req.on("error", (err) => {
              console.error("Upload error:", err);
              res.statusCode = 500;
              res.setHeader("Content-Type", "application/json");
              res.end(JSON.stringify({ error: "Upload failed" }));
            });
          } else {
            next();
          }
        });
      }
    },
    {
      name: "save-images-plugin",
      configureServer(server) {
        server.middlewares.use(async (req, res, next) => {
          if (req.url === "/api/save-images" && req.method === "POST") {
            res.setHeader("Content-Type", "application/json");
            try {
              const files = await parseMultipart(req);
              if (files.length === 0) {
                res.statusCode = 400;
                res.end(JSON.stringify({ error: "No files received" }));
                return;
              }
              const targetDir = "/Users/bikash/image_search/reference";
              fs.mkdirSync(targetDir, { recursive: true });
              for (const { filename, data } of files) {
                fs.writeFileSync(path.join(targetDir, filename), data);
              }
              res.statusCode = 200;
              res.end(JSON.stringify({ success: true, path: targetDir, count: files.length }));
            } catch (e: any) {
              console.error("save-images error:", e);
              res.statusCode = 500;
              res.end(JSON.stringify({ error: e.message }));
            }
          } else {
            next();
          }
        });
      }
    },
    {
      name: "serve-image-search-plugin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url && req.url.startsWith("/image_search/")) {
            const cleanUrl = decodeURIComponent(req.url.split('?')[0]);
            const relativePath = cleanUrl.replace(/^\/image_search\/?/, "");
            const filePath = path.join("/Users/bikash/image_search", relativePath);
            if (fs.existsSync(filePath)) {
              const ext = path.extname(filePath).toLowerCase();
              const mime = ext === ".png" ? "image/png" : "image/jpeg";
              res.setHeader("Content-Type", mime);
              res.statusCode = 200;
              res.end(fs.readFileSync(filePath));
            } else {
              res.statusCode = 404;
              res.end("Not Found: " + filePath);
            }
          } else {
            next();
          }
        });
      }
    },
    {
      name: "run-search-plugin",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          if (req.url === "/api/run-search" && req.method === "POST") {
            res.setHeader("Content-Type", "application/json");
            const scriptPath = "/Users/bikash/image_search/search.py";
            const venvPython = "/Users/bikash/image_search/venv/bin/python";
            const workingDir = "/Users/bikash/image_search";
            
            exec(`"${venvPython}" "${scriptPath}"`, { cwd: workingDir }, (err, stdout, stderr) => {
              if (err) {
                console.error("Search execution error:", err, stderr);
                res.statusCode = 500;
                res.end(JSON.stringify({ error: "Failed to run search", details: err.message, stderr }));
                return;
              }
              
              // Parse stdout
              const lines = stdout.split("\n");
              const results: any[] = [];
              let currentRef: string | null = null;
              let inMatches = false;

              for (const line of lines) {
                const refMatch = line.match(/^REFERENCE\s*:\s*(.+)$/);
                if (refMatch) {
                  currentRef = refMatch[1].trim();
                  inMatches = false;
                  continue;
                }
                if (line.includes("Top Matches:")) {
                  inMatches = true;
                  continue;
                }
                if (inMatches && line.trim()) {
                  const parts = line.trim().split(/\s+/);
                  if (parts.length >= 2) {
                    const filename = parts[0];
                    const score = parseFloat(parts[1]);
                    if (filename.endsWith(".jpg") || filename.endsWith(".jpeg") || filename.endsWith(".png")) {
                      // parse coordinates
                      const coordMatch = filename.match(/x_(-?\d+\.?\d*)-y_(-?\d+\.?\d*)/);
                      const x = coordMatch ? parseFloat(coordMatch[1]) : 0;
                      const y = coordMatch ? parseFloat(coordMatch[2]) : 0;
                      
                      let refObj = results.find(r => r.reference === currentRef);
                      if (!refObj) {
                        refObj = { reference: currentRef, matches: [] };
                        results.push(refObj);
                      }
                      refObj.matches.push({ filename, score, x, y });
                    }
                  }
                }
              }
              
              res.statusCode = 200;
              res.end(JSON.stringify({ success: true, results }));
            });
          } else {
            next();
          }
        });
      }
    }
  ],
  server: {
    port: 5173,
  },
});
