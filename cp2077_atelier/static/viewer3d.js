/**
 * Hardware-accelerated WebGL (with 2D Canvas fallback) 3D GLB/OBJ Cyberpunk garment renderer.
 * Also supports offscreen 3D thumbnail snapshot generation for batch grid cards.
 */
class MeshViewer3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl", { preserveDrawingBuffer: true, antialias: true });
    this.ctx2d = this.gl ? null : canvas.getContext("2d");
    this.rotX = 0.18;
    this.rotY = -0.45;
    this.zoom = 2.3;
    this.wireframe = false;
    this.label = "3D Preview";
    this.accentColor = "#05d9e8";

    // CPU geometry for fallback / bounds
    this.positions = null; // Float32Array (unindexed triangles: 9 floats per tri)
    this.normals = null;   // Float32Array (9 floats per tri)
    this.vertCount = 0;

    // WebGL resources
    this.program = null;
    this.posBuffer = null;
    this.normBuffer = null;

    if (this.gl) {
      this._initWebGL();
    }
    this._bindEvents();
  }

  _initWebGL() {
    const gl = this.gl;
    const vsSource = `
      attribute vec3 aPos;
      attribute vec3 aNorm;
      uniform float uRotX;
      uniform float uRotY;
      uniform float uZoom;
      uniform float uAspect;
      varying vec3 vNorm;
      varying vec3 vPos;
      void main() {
        float cy = cos(uRotY), sy = sin(uRotY);
        float cx = cos(uRotX), sx = sin(uRotX);
        vec3 p = aPos;
        vec3 n = aNorm;
        // Rotate Y
        p = vec3(p.x * cy - p.z * sy, p.y, p.x * sy + p.z * cy);
        n = vec3(n.x * cy - n.z * sy, n.y, n.x * sy + n.z * cy);
        // Rotate X
        p = vec3(p.x, p.y * cx - p.z * sx, p.y * sx + p.z * cx);
        n = vec3(n.x, n.y * cx - n.z * sx, n.y * sx + n.z * cx);
        vNorm = normalize(n);
        vPos = p;
        float zDist = 3.6 - p.z;
        float fov = uZoom / max(0.2, zDist);
        gl_Position = vec4((p.x * fov) / uAspect, p.y * fov, (p.z + 2.0) * 0.25, 1.0);
      }
    `;
    const fsSource = `
      precision mediump float;
      varying vec3 vNorm;
      varying vec3 vPos;
      uniform vec3 uColor;
      uniform float uWire;
      void main() {
        if (uWire > 0.5) {
          gl_FragColor = vec4(uColor, 0.95);
          return;
        }
        vec3 n = normalize(vNorm);
        vec3 light1 = normalize(vec3(0.45, 0.65, 0.85));
        vec3 light2 = normalize(vec3(-0.6, -0.2, 0.4));
        float diff1 = max(abs(dot(n, light1)), 0.0);
        float diff2 = max(abs(dot(n, light2)), 0.0) * 0.35;
        float rim = pow(1.0 - abs(n.z), 2.0) * 0.45;
        vec3 base = vec3(0.14, 0.17, 0.24) + uColor * 0.55;
        vec3 col = base * (0.28 + diff1 * 0.72 + diff2) + uColor * rim;
        gl_FragColor = vec4(col, 1.0);
      }
    `;
    const compile = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    };
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, vsSource));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, fsSource));
    gl.linkProgram(prog);
    this.program = prog;
    this.posBuffer = gl.createBuffer();
    this.normBuffer = gl.createBuffer();
  }

  _bindEvents() {
    let dragging = false, lastX = 0, lastY = 0;
    this.canvas.addEventListener("mousedown", (e) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener("mouseup", () => { dragging = false; });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      this.rotY += dx * 0.012;
      this.rotX = Math.max(-1.45, Math.min(1.45, this.rotX + dy * 0.012));
      this.render();
    });
    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.zoom = Math.max(0.8, Math.min(6.0, this.zoom - e.deltaY * 0.0025));
      this.render();
    });
  }

  resetCamera() {
    this.rotX = 0.18;
    this.rotY = -0.45;
    this.zoom = 2.3;
    this.render();
  }

  toggleWireframe() {
    this.wireframe = !this.wireframe;
    this.render();
    return this.wireframe;
  }

  _uploadTriangles(verts, faces, label, accent) {
    // Normalize vertices into [-1, 1] bounding box
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (let i = 0; i < verts.length; i++) {
      const [x, y, z] = verts[i];
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
      if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
    }
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
    const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ) || 1;
    const sc = 1.9 / span;
    const normVerts = verts.map(([x, y, z]) => [(x - cx) * sc, (y - cy) * sc, (z - cz) * sc]);

    const posArr = new Float32Array(faces.length * 9);
    const normArr = new Float32Array(faces.length * 9);
    let ptr = 0;

    for (let i = 0; i < faces.length; i++) {
      const f = faces[i];
      const v0 = normVerts[f[0]], v1 = normVerts[f[1]], v2 = normVerts[f[2]];
      if (!v0 || !v1 || !v2) continue;
      const ux = v1[0] - v0[0], uy = v1[1] - v0[1], uz = v1[2] - v0[2];
      const vx = v2[0] - v0[0], vy = v2[1] - v0[1], vz = v2[2] - v0[2];
      let nx = uy * vz - uz * vy;
      let ny = uz * vx - ux * vz;
      let nz = ux * vy - uy * vx;
      const nl = Math.hypot(nx, ny, nz) || 1;
      nx /= nl; ny /= nl; nz /= nl;

      posArr[ptr] = v0[0]; posArr[ptr + 1] = v0[1]; posArr[ptr + 2] = v0[2];
      posArr[ptr + 3] = v1[0]; posArr[ptr + 4] = v1[1]; posArr[ptr + 5] = v1[2];
      posArr[ptr + 6] = v2[0]; posArr[ptr + 7] = v2[1]; posArr[ptr + 8] = v2[2];

      normArr[ptr] = nx; normArr[ptr + 1] = ny; normArr[ptr + 2] = nz;
      normArr[ptr + 3] = nx; normArr[ptr + 4] = ny; normArr[ptr + 5] = nz;
      normArr[ptr + 6] = nx; normArr[ptr + 7] = ny; normArr[ptr + 8] = nz;
      ptr += 9;
    }

    this.positions = posArr.subarray(0, ptr);
    this.normals = normArr.subarray(0, ptr);
    this.vertCount = ptr / 3;
    this.label = label;
    this.accentColor = accent;

    if (this.gl) {
      const gl = this.gl;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.normals, gl.STATIC_DRAW);
    }
    this.render();
  }

  loadObjText(objText, label = "Mesh", accent = "#05d9e8") {
    const verts = [];
    const faces = [];
    for (const raw of objText.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const parts = line.split(/\s+/);
      if (parts[0] === "v" && parts.length >= 4) {
        verts.push([parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])]);
      } else if (parts[0] === "f" && parts.length >= 4) {
        const idx = parts.slice(1).map((tok) => parseInt(tok.split("/")[0], 10) - 1);
        for (let i = 1; i + 1 < idx.length; i++) {
          faces.push([idx[0], idx[i], idx[i + 1]]);
        }
      }
    }
    this._uploadTriangles(verts, faces, label, accent);
  }

  loadProceduralFallback(category, label = "Procedural Silhouette") {
    const fallbackObj = [
      "v -0.6 0.8 0.3", "v 0.6 0.8 0.3", "v 0.45 -0.5 0.3", "v -0.45 -0.5 0.3",
      "v -0.6 0.8 -0.3", "v 0.6 0.8 -0.3", "v 0.45 -0.5 -0.3", "v -0.45 -0.5 -0.3",
      "f 1 2 3 4", "f 5 6 7 8", "f 1 2 6 5", "f 2 3 7 6", "f 3 4 8 7", "f 4 1 5 8"
    ].join("\n");
    this.loadObjText(fallbackObj, `${label} (${category})`, "#fcee09");
  }

  static parseGlbBuffers(arrayBuffer) {
    const dv = new DataView(arrayBuffer);
    if (dv.getUint32(0, true) !== 0x46546c67) {
      throw new Error("Invalid GLB magic");
    }
    let offset = 12;
    let jsonChunk = null;
    let binChunk = null;
    while (offset < arrayBuffer.byteLength) {
      const chunkLen = dv.getUint32(offset, true);
      const chunkType = dv.getUint32(offset + 4, true);
      const chunkStart = offset + 8;
      if (chunkType === 0x4e4f534a) {
        const dec = new TextDecoder("utf-8");
        jsonChunk = JSON.parse(dec.decode(new Uint8Array(arrayBuffer, chunkStart, chunkLen)));
      } else if (chunkType === 0x004e4942) {
        binChunk = new DataView(arrayBuffer, chunkStart, chunkLen);
      }
      offset = chunkStart + chunkLen;
    }
    if (!jsonChunk || !binChunk || !jsonChunk.meshes || !jsonChunk.meshes.length) {
      throw new Error("No meshes in GLB");
    }

    const accessors = jsonChunk.accessors || [];
    const bufferViews = jsonChunk.bufferViews || [];

    // First pass: count total triangles and bounding box
    let totalTris = 0;
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    const validPrims = [];

    for (const mesh of jsonChunk.meshes) {
      for (const prim of mesh.primitives || []) {
        const posAccIdx = prim.attributes && prim.attributes.POSITION;
        if (posAccIdx === undefined || prim.indices === undefined) continue;
        const posAcc = accessors[posAccIdx];
        if (jsonChunk.meshes.length > 1 && posAcc.count <= 8) continue;
        const idxAcc = accessors[prim.indices];
        const tris = Math.floor(idxAcc.count / 3);
        if (tris <= 0) continue;
        totalTris += tris;
        validPrims.push({ posAcc, idxAcc });

        if (posAcc.min && posAcc.max) {
          if (posAcc.min[0] < minX) minX = posAcc.min[0];
          if (posAcc.min[1] < minY) minY = posAcc.min[1];
          if (posAcc.min[2] < minZ) minZ = posAcc.min[2];
          if (posAcc.max[0] > maxX) maxX = posAcc.max[0];
          if (posAcc.max[1] > maxY) maxY = posAcc.max[1];
          if (posAcc.max[2] > maxZ) maxZ = posAcc.max[2];
        } else {
          const posBv = bufferViews[posAcc.bufferView];
          const posStride = posBv.byteStride || 12;
          const posBase = (posBv.byteOffset || 0) + (posAcc.byteOffset || 0);
          for (let i = 0; i < posAcc.count; i++) {
            const p = posBase + i * posStride;
            const x = binChunk.getFloat32(p, true);
            const y = binChunk.getFloat32(p + 4, true);
            const z = binChunk.getFloat32(p + 8, true);
            if (x < minX) minX = x; if (x > maxX) maxX = x;
            if (y < minY) minY = y; if (y > maxY) maxY = y;
            if (z < minZ) minZ = z; if (z > maxZ) maxZ = z;
          }
        }
      }
    }

    if (!totalTris) throw new Error("Empty GLB geometry");

    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2, cz = (minZ + maxZ) / 2;
    const span = Math.max(maxX - minX, maxY - minY, maxZ - minZ) || 1;
    const sc = 1.9 / span;

    const posArr = new Float32Array(totalTris * 9);
    const normArr = new Float32Array(totalTris * 9);
    let ptr = 0;

    for (const { posAcc, idxAcc } of validPrims) {
      const posBv = bufferViews[posAcc.bufferView];
      const posStride = posBv.byteStride || 12;
      const posBase = (posBv.byteOffset || 0) + (posAcc.byteOffset || 0);

      const idxBv = bufferViews[idxAcc.bufferView];
      const idxBase = (idxBv.byteOffset || 0) + (idxAcc.byteOffset || 0);
      const isU32 = idxAcc.componentType === 5125;
      const step = isU32 ? 4 : 2;
      const triCount = Math.floor(idxAcc.count / 3);

      for (let t = 0; t < triCount; t++) {
        const b = idxBase + t * 3 * step;
        const i0 = isU32 ? binChunk.getUint32(b, true) : binChunk.getUint16(b, true);
        const i1 = isU32 ? binChunk.getUint32(b + step, true) : binChunk.getUint16(b + step, true);
        const i2 = isU32 ? binChunk.getUint32(b + step * 2, true) : binChunk.getUint16(b + step * 2, true);

        const p0 = posBase + i0 * posStride;
        const p1 = posBase + i1 * posStride;
        const p2 = posBase + i2 * posStride;

        const x0 = (binChunk.getFloat32(p0, true) - cx) * sc;
        const y0 = (binChunk.getFloat32(p0 + 4, true) - cy) * sc;
        const z0 = (binChunk.getFloat32(p0 + 8, true) - cz) * sc;

        const x1 = (binChunk.getFloat32(p1, true) - cx) * sc;
        const y1 = (binChunk.getFloat32(p1 + 4, true) - cy) * sc;
        const z1 = (binChunk.getFloat32(p1 + 8, true) - cz) * sc;

        const x2 = (binChunk.getFloat32(p2, true) - cx) * sc;
        const y2 = (binChunk.getFloat32(p2 + 4, true) - cy) * sc;
        const z2 = (binChunk.getFloat32(p2 + 8, true) - cz) * sc;

        const ux = x1 - x0, uy = y1 - y0, uz = z1 - z0;
        const vx = x2 - x0, vy = y2 - y0, vz = z2 - z0;
        let nx = uy * vz - uz * vy;
        let ny = uz * vx - ux * vz;
        let nz = ux * vy - uy * vx;
        const nl = Math.hypot(nx, ny, nz) || 1;
        nx /= nl; ny /= nl; nz /= nl;

        posArr[ptr] = x0; posArr[ptr + 1] = y0; posArr[ptr + 2] = z0;
        posArr[ptr + 3] = x1; posArr[ptr + 4] = y1; posArr[ptr + 5] = z1;
        posArr[ptr + 6] = x2; posArr[ptr + 7] = y2; posArr[ptr + 8] = z2;

        normArr[ptr] = nx; normArr[ptr + 1] = ny; normArr[ptr + 2] = nz;
        normArr[ptr + 3] = nx; normArr[ptr + 4] = ny; normArr[ptr + 5] = nz;
        normArr[ptr + 6] = nx; normArr[ptr + 7] = ny; normArr[ptr + 8] = nz;
        ptr += 9;
      }
    }
    return { posArr: posArr.subarray(0, ptr), normArr: normArr.subarray(0, ptr), vertCount: ptr / 3 };
  }

  async loadGlbUrl(url, label = "3D Mesh", accent = "#05d9e8") {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = await res.arrayBuffer();
    this.loadGlbBuffer(buf, label, accent);
  }

  loadGlbBuffer(arrayBuffer, label = "3D Mesh", accent = "#05d9e8") {
    const { posArr, normArr, vertCount } = MeshViewer3D.parseGlbBuffers(arrayBuffer);
    this.positions = posArr;
    this.normals = normArr;
    this.vertCount = vertCount;
    this.label = label;
    this.accentColor = accent;
    if (this.gl) {
      const gl = this.gl;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.normals, gl.STATIC_DRAW);
    }
    this.render();
  }

  _hexToRgb(hex) {
    const h = (hex || "#05d9e8").replace("#", "");
    const num = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16) || 0x05d9e8;
    return [((num >> 16) & 255) / 255, ((num >> 8) & 255) / 255, (num & 255) / 255];
  }

  render() {
    if (!this.gl) return;
    const gl = this.gl;
    const w = this.canvas.width;
    const h = this.canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(0.035, 0.043, 0.07, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);

    if (!this.vertCount) return;

    gl.useProgram(this.program);
    const aPos = gl.getAttribLocation(this.program, "aPos");
    const aNorm = gl.getAttribLocation(this.program, "aNorm");

    gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuffer);
    gl.enableVertexAttribArray(aNorm);
    gl.vertexAttribPointer(aNorm, 3, gl.FLOAT, false, 0, 0);

    gl.uniform1f(gl.getUniformLocation(this.program, "uRotX"), this.rotX);
    gl.uniform1f(gl.getUniformLocation(this.program, "uRotY"), this.rotY);
    gl.uniform1f(gl.getUniformLocation(this.program, "uZoom"), this.zoom);
    gl.uniform1f(gl.getUniformLocation(this.program, "uAspect"), w / Math.max(1, h));

    const rgb = this._hexToRgb(this.accentColor);
    gl.uniform3f(gl.getUniformLocation(this.program, "uColor"), rgb[0], rgb[1], rgb[2]);

    if (this.wireframe) {
      gl.uniform1f(gl.getUniformLocation(this.program, "uWire"), 1.0);
      gl.drawArrays(gl.LINES, 0, this.vertCount);
    } else {
      gl.uniform1f(gl.getUniformLocation(this.program, "uWire"), 0.0);
      gl.drawArrays(gl.TRIANGLES, 0, this.vertCount);
    }
  }
}

// Shared offscreen WebGL thumbnail generator for cards whose .archive only has .mesh (no 2D .xbm icon)
let _thumbViewer = null;
const _glbThumbCache = new Map();

async function renderGlbThumbnailDataUrl(glbUrl, accentColor = "#05d9e8") {
  if (_glbThumbCache.has(glbUrl)) return _glbThumbCache.get(glbUrl);
  if (!_thumbViewer) {
    const offCanvas = document.createElement("canvas");
    offCanvas.width = 320;
    offCanvas.height = 200;
    _thumbViewer = new MeshViewer3D(offCanvas);
  }
  await _thumbViewer.loadGlbUrl(glbUrl, "", accentColor);
  const dataUrl = _thumbViewer.canvas.toDataURL("image/png");
  _glbThumbCache.set(glbUrl, dataUrl);
  return dataUrl;
}

window.MeshViewer3D = MeshViewer3D;
window.renderGlbThumbnailDataUrl = renderGlbThumbnailDataUrl;
