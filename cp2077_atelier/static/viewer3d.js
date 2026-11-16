/**
 * Hardware-accelerated WebGL 3D GLB/OBJ Cyberpunk garment renderer with:
 * - True smooth vertex normals (NORMAL) & UV coordinates (TEXCOORD_0) from WolvenKit GLBs
 * - 2D diffuse/albedo texture mapping + procedural fabric micro-weave fallback
 * - Offscreen Textured 3D Snapshot generator for scalable grid tiles
 */
class MeshViewer3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext("webgl", { preserveDrawingBuffer: true, antialias: true });
    this.rotX = 0.14;
    this.rotY = -0.38;
    this.zoom = 2.45;
    this.wireframe = false;
    this.label = "3D Preview";
    this.accentColor = "#05d9e8";

    this.positions = null;
    this.normals = null;
    this.uvs = null;
    this.vertCount = 0;

    this.program = null;
    this.posBuffer = null;
    this.normBuffer = null;
    this.uvBuffer = null;
    this.texture = null;
    this.hasTexture = false;

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
      attribute vec2 aUV;
      uniform float uRotX;
      uniform float uRotY;
      uniform float uZoom;
      uniform float uAspect;
      varying vec3 vNorm;
      varying vec3 vPos;
      varying vec2 vUV;
      void main() {
        float cy = cos(uRotY), sy = sin(uRotY);
        float cx = cos(uRotX), sx = sin(uRotX);
        vec3 p = aPos;
        vec3 n = aNorm;
        p = vec3(p.x * cy - p.z * sy, p.y, p.x * sy + p.z * cy);
        n = vec3(n.x * cy - n.z * sy, n.y, n.x * sy + n.z * cy);
        p = vec3(p.x, p.y * cx - p.z * sx, p.y * sx + p.z * cx);
        n = vec3(n.x, n.y * cx - n.z * sx, n.y * sx + n.z * cx);
        vNorm = normalize(n);
        vPos = p;
        vUV = aUV;
        float zDist = 3.6 - p.z;
        float fov = uZoom / max(0.2, zDist);
        gl_Position = vec4((p.x * fov) / uAspect, p.y * fov, (p.z + 2.0) * 0.25, 1.0);
      }
    `;
    const fsSource = `
      precision mediump float;
      varying vec3 vNorm;
      varying vec3 vPos;
      varying vec2 vUV;
      uniform vec3 uColor;
      uniform float uWire;
      uniform float uHasTex;
      uniform sampler2D uTex;
      void main() {
        if (uWire > 0.5) {
          gl_FragColor = vec4(uColor, 0.95);
          return;
        }
        vec3 n = normalize(vNorm);
        vec3 viewDir = normalize(vec3(0.0, 0.0, 1.0));
        vec3 light1 = normalize(vec3(0.45, 0.7, 0.85));
        vec3 light2 = normalize(vec3(-0.65, -0.25, 0.45));

        float diff1 = max(abs(dot(n, light1)), 0.0);
        float diff2 = max(abs(dot(n, light2)), 0.0) * 0.38;

        // Blinn-Phong specular highlight for fabric/leather sheen
        vec3 halfVec = normalize(light1 + viewDir);
        float spec = pow(max(abs(dot(n, halfVec)), 0.0), 28.0) * 0.35;
        float rim = pow(1.0 - min(1.0, abs(n.z)), 2.4) * 0.42;

        vec3 albedo;
        if (uHasTex > 0.5) {
          vec4 texCol = texture2D(uTex, fract(vUV));
          albedo = mix(vec3(0.22, 0.25, 0.32), texCol.rgb, texCol.a);
        } else {
          // Procedural micro-weave studio fabric texture along UVs
          float weave = sin(vUV.x * 160.0) * sin(vUV.y * 160.0) * 0.04;
          albedo = vec3(0.20, 0.23, 0.30) + uColor * 0.48 + vec3(weave);
        }

        vec3 lit = albedo * (0.32 + diff1 * 0.78 + diff2) + vec3(spec) + uColor * rim;
        gl_FragColor = vec4(lit, 1.0);
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
    this.uvBuffer = gl.createBuffer();
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
    this.rotX = 0.14;
    this.rotY = -0.38;
    this.zoom = 2.45;
    this.render();
  }

  toggleWireframe() {
    this.wireframe = !this.wireframe;
    this.render();
    return this.wireframe;
  }

  clearTexture() {
    this.hasTexture = false;
    this.render();
  }

  async loadTextureUrl(url) {
    if (!this.gl || !url) {
      this.hasTexture = false;
      this.render();
      return;
    }
    const gl = this.gl;
    return new Promise((resolve) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => {
        // Quick check on a tiny 8x8 canvas to reject purple normal maps (B > 0.72, R ~ 0.5, G ~ 0.5)
        try {
          const c = document.createElement("canvas");
          c.width = 8; c.height = 8;
          const ctx = c.getContext("2d");
          ctx.drawImage(img, 0, 0, 8, 8);
          const data = ctx.getImageData(0, 0, 8, 8).data;
          let rSum = 0, gSum = 0, bSum = 0;
          for (let i = 0; i < data.length; i += 4) {
            rSum += data[i]; gSum += data[i + 1]; bSum += data[i + 2];
          }
          const n = data.length / 4;
          const rAvg = rSum / n, gAvg = gSum / n, bAvg = bSum / n;
          if (bAvg > 195 && rAvg > 105 && rAvg < 155 && gAvg > 105 && gAvg < 155) {
            // Normal map detected; use studio micro-weave shader instead
            this.hasTexture = false;
            this.render();
            resolve(false);
            return;
          }
        } catch {}

        if (!this.texture) this.texture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, this.texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        this.hasTexture = true;
        this.render();
        resolve(true);
      };
      img.onerror = () => {
        this.hasTexture = false;
        this.render();
        resolve(false);
      };
      img.src = url;
    });
  }

  _uploadBuffers(posArr, normArr, uvArr, vertCount, label, accent) {
    this.positions = posArr;
    this.normals = normArr;
    this.uvs = uvArr;
    this.vertCount = vertCount;
    this.label = label;
    this.accentColor = accent;

    if (this.gl) {
      const gl = this.gl;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.normals, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, this.uvs, gl.STATIC_DRAW);
    }
    this.render();
  }

  loadObjText(objText, label = "Mesh", accent = "#05d9e8") {
    this.hasTexture = false;
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
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    for (const [x, y, z] of verts) {
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
    const uvArr = new Float32Array(faces.length * 6);
    let ptr = 0, uvPtr = 0;
    for (const f of faces) {
      const v0 = normVerts[f[0]], v1 = normVerts[f[1]], v2 = normVerts[f[2]];
      if (!v0 || !v1 || !v2) continue;
      const ux = v1[0] - v0[0], uy = v1[1] - v0[1], uz = v1[2] - v0[2];
      const vx = v2[0] - v0[0], vy = v2[1] - v0[1], vz = v2[2] - v0[2];
      let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const nl = Math.hypot(nx, ny, nz) || 1;
      nx /= nl; ny /= nl; nz /= nl;
      posArr.set(v0, ptr); posArr.set(v1, ptr + 3); posArr.set(v2, ptr + 6);
      normArr.set([nx, ny, nz, nx, ny, nz, nx, ny, nz], ptr);
      uvArr.set([v0[0], v0[1], v1[0], v1[1], v2[0], v2[1]], uvPtr);
      ptr += 9; uvPtr += 6;
    }
    this._uploadBuffers(posArr.subarray(0, ptr), normArr.subarray(0, ptr), uvArr.subarray(0, uvPtr), ptr / 3, label, accent);
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

    let totalTris = 0;
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    const validPrims = [];

    for (const mesh of jsonChunk.meshes) {
      for (const prim of mesh.primitives || []) {
        const attrs = prim.attributes || {};
        if (attrs.POSITION === undefined || prim.indices === undefined) continue;
        const posAcc = accessors[attrs.POSITION];
        if (jsonChunk.meshes.length > 1 && posAcc.count <= 8) continue;
        const idxAcc = accessors[prim.indices];
        const tris = Math.floor(idxAcc.count / 3);
        if (tris <= 0) continue;
        totalTris += tris;
        const normAcc = attrs.NORMAL !== undefined ? accessors[attrs.NORMAL] : null;
        const uvAcc = attrs.TEXCOORD_0 !== undefined ? accessors[attrs.TEXCOORD_0] : null;
        validPrims.push({ posAcc, idxAcc, normAcc, uvAcc });

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
    const sc = 1.95 / span;

    const posArr = new Float32Array(totalTris * 9);
    const normArr = new Float32Array(totalTris * 9);
    const uvArr = new Float32Array(totalTris * 6);
    let ptr = 0, uvPtr = 0;

    for (const { posAcc, idxAcc, normAcc, uvAcc } of validPrims) {
      const posBv = bufferViews[posAcc.bufferView];
      const posStride = posBv.byteStride || 12;
      const posBase = (posBv.byteOffset || 0) + (posAcc.byteOffset || 0);

      const hasSmoothNorm = Boolean(normAcc && normAcc.componentType === 5126);
      const normBv = hasSmoothNorm ? bufferViews[normAcc.bufferView] : null;
      const normStride = hasSmoothNorm ? (normBv.byteStride || 12) : 12;
      const normBase = hasSmoothNorm ? ((normBv.byteOffset || 0) + (normAcc.byteOffset || 0)) : 0;

      const hasUV = Boolean(uvAcc && uvAcc.componentType === 5126);
      const uvBv = hasUV ? bufferViews[uvAcc.bufferView] : null;
      const uvStride = hasUV ? (uvBv.byteStride || 8) : 8;
      const uvBase = hasUV ? ((uvBv.byteOffset || 0) + (uvAcc.byteOffset || 0)) : 0;

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

        posArr[ptr] = x0; posArr[ptr + 1] = y0; posArr[ptr + 2] = z0;
        posArr[ptr + 3] = x1; posArr[ptr + 4] = y1; posArr[ptr + 5] = z1;
        posArr[ptr + 6] = x2; posArr[ptr + 7] = y2; posArr[ptr + 8] = z2;

        if (hasSmoothNorm) {
          const n0 = normBase + i0 * normStride;
          const n1 = normBase + i1 * normStride;
          const n2 = normBase + i2 * normStride;
          normArr[ptr] = binChunk.getFloat32(n0, true);
          normArr[ptr + 1] = binChunk.getFloat32(n0 + 4, true);
          normArr[ptr + 2] = binChunk.getFloat32(n0 + 8, true);
          normArr[ptr + 3] = binChunk.getFloat32(n1, true);
          normArr[ptr + 4] = binChunk.getFloat32(n1 + 4, true);
          normArr[ptr + 5] = binChunk.getFloat32(n1 + 8, true);
          normArr[ptr + 6] = binChunk.getFloat32(n2, true);
          normArr[ptr + 7] = binChunk.getFloat32(n2 + 4, true);
          normArr[ptr + 8] = binChunk.getFloat32(n2 + 8, true);
        } else {
          const ux = x1 - x0, uy = y1 - y0, uz = z1 - z0;
          const vx = x2 - x0, vy = y2 - y0, vz = z2 - z0;
          let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
          const nl = Math.hypot(nx, ny, nz) || 1;
          nx /= nl; ny /= nl; nz /= nl;
          normArr[ptr] = nx; normArr[ptr + 1] = ny; normArr[ptr + 2] = nz;
          normArr[ptr + 3] = nx; normArr[ptr + 4] = ny; normArr[ptr + 5] = nz;
          normArr[ptr + 6] = nx; normArr[ptr + 7] = ny; normArr[ptr + 8] = nz;
        }

        if (hasUV) {
          const u0 = uvBase + i0 * uvStride;
          const u1 = uvBase + i1 * uvStride;
          const u2 = uvBase + i2 * uvStride;
          uvArr[uvPtr] = binChunk.getFloat32(u0, true);
          uvArr[uvPtr + 1] = binChunk.getFloat32(u0 + 4, true);
          uvArr[uvPtr + 2] = binChunk.getFloat32(u1, true);
          uvArr[uvPtr + 3] = binChunk.getFloat32(u1 + 4, true);
          uvArr[uvPtr + 4] = binChunk.getFloat32(u2, true);
          uvArr[uvPtr + 5] = binChunk.getFloat32(u2 + 4, true);
        } else {
          uvArr[uvPtr] = x0 * 0.5 + 0.5; uvArr[uvPtr + 1] = y0 * 0.5 + 0.5;
          uvArr[uvPtr + 2] = x1 * 0.5 + 0.5; uvArr[uvPtr + 3] = y1 * 0.5 + 0.5;
          uvArr[uvPtr + 4] = x2 * 0.5 + 0.5; uvArr[uvPtr + 5] = y2 * 0.5 + 0.5;
        }

        ptr += 9;
        uvPtr += 6;
      }
    }
    return {
      posArr: posArr.subarray(0, ptr),
      normArr: normArr.subarray(0, ptr),
      uvArr: uvArr.subarray(0, uvPtr),
      vertCount: ptr / 3,
    };
  }

  async loadGlbUrl(url, label = "3D Mesh", accent = "#05d9e8", textureUrl = null) {
    this.hasTexture = false;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = await res.arrayBuffer();
    this.loadGlbBuffer(buf, label, accent);
    if (textureUrl) {
      await this.loadTextureUrl(textureUrl);
    }
  }

  loadGlbBuffer(arrayBuffer, label = "3D Mesh", accent = "#05d9e8") {
    const { posArr, normArr, uvArr, vertCount } = MeshViewer3D.parseGlbBuffers(arrayBuffer);
    this._uploadBuffers(posArr, normArr, uvArr, vertCount, label, accent);
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
    gl.clearColor(0.04, 0.048, 0.078, 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);

    if (!this.vertCount) return;

    gl.useProgram(this.program);
    const aPos = gl.getAttribLocation(this.program, "aPos");
    const aNorm = gl.getAttribLocation(this.program, "aNorm");
    const aUV = gl.getAttribLocation(this.program, "aUV");

    gl.bindBuffer(gl.ARRAY_BUFFER, this.posBuffer);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.normBuffer);
    gl.enableVertexAttribArray(aNorm);
    gl.vertexAttribPointer(aNorm, 3, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.uvBuffer);
    gl.enableVertexAttribArray(aUV);
    gl.vertexAttribPointer(aUV, 2, gl.FLOAT, false, 0, 0);

    gl.uniform1f(gl.getUniformLocation(this.program, "uRotX"), this.rotX);
    gl.uniform1f(gl.getUniformLocation(this.program, "uRotY"), this.rotY);
    gl.uniform1f(gl.getUniformLocation(this.program, "uZoom"), this.zoom);
    gl.uniform1f(gl.getUniformLocation(this.program, "uAspect"), w / Math.max(1, h));

    const rgb = this._hexToRgb(this.accentColor);
    gl.uniform3f(gl.getUniformLocation(this.program, "uColor"), rgb[0], rgb[1], rgb[2]);

    if (this.hasTexture && this.texture) {
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.texture);
      gl.uniform1i(gl.getUniformLocation(this.program, "uTex"), 0);
      gl.uniform1f(gl.getUniformLocation(this.program, "uHasTex"), 1.0);
    } else {
      gl.uniform1f(gl.getUniformLocation(this.program, "uHasTex"), 0.0);
    }

    if (this.wireframe) {
      gl.uniform1f(gl.getUniformLocation(this.program, "uWire"), 1.0);
      gl.drawArrays(gl.LINES, 0, this.vertCount);
    } else {
      gl.uniform1f(gl.getUniformLocation(this.program, "uWire"), 0.0);
      gl.drawArrays(gl.TRIANGLES, 0, this.vertCount);
    }
  }
}

// Shared offscreen WebGL Textured 3D Snapshot generator for scalable grid tiles
let _thumbViewer = null;
const _glbThumbCache = new Map();

async function renderGlbThumbnailDataUrl(glbUrl, accentColor = "#05d9e8", textureUrl = null) {
  const cacheKey = `${glbUrl}|${textureUrl || ""}`;
  if (_glbThumbCache.has(cacheKey)) return _glbThumbCache.get(cacheKey);
  if (!_thumbViewer) {
    const offCanvas = document.createElement("canvas");
    offCanvas.width = 360;
    offCanvas.height = 280;
    _thumbViewer = new MeshViewer3D(offCanvas);
  }
  await _thumbViewer.loadGlbUrl(glbUrl, "", accentColor, textureUrl);
  const dataUrl = _thumbViewer.canvas.toDataURL("image/png");
  _glbThumbCache.set(cacheKey, dataUrl);
  return dataUrl;
}

window.MeshViewer3D = MeshViewer3D;
window.renderGlbThumbnailDataUrl = renderGlbThumbnailDataUrl;
