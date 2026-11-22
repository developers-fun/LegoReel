"""moderngl renderer: shadowed Lambert/hemisphere lighting, sky, fog, glass pass, post FX.

GL 3.3 core only. Conventions: Y-up right-handed, column-vector 4x4 matrices.
Texture convention: images are uploaded so that the image's TOP row is at v=1 (OpenGL style,
uv (0,0) = bottom-left of the picture). Textures repeat (tile) outside 0..1.
"""
from __future__ import annotations
import math
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import moderngl

from .mesh import Mesh
from .util import color as _color, look_at, perspective, normalize
from .post import PostFx, PostProcessor

__all__ = ["DrawItem", "CameraState", "Lighting", "PostFx", "Renderer", "QUALITY"]

QUALITY = {
    "preview": dict(samples=2, shadow_cap=1024),
    "final": dict(samples=4, shadow_cap=None),
}


@dataclass
class DrawItem:
    mesh: Mesh
    model: np.ndarray = None
    color: tuple = (1.0, 1.0, 1.0)
    texture: object = None            # PIL.Image | np.ndarray | str path | None
    material: str = "plastic"         # plastic|smooth|grass|brick|wood|concrete|glass|neon|metal
    transparency: float = 0.0
    cast_shadow: bool = True
    receive_shadow: bool = True
    uv_scale: tuple = (1.0, 1.0)
    emissive: float = 0.0
    key: Optional[str] = None         # stable id => texture cache key

    def __post_init__(self):
        if self.model is None:
            self.model = np.eye(4)


@dataclass
class CameraState:
    eye: tuple = (0.0, 5.0, 10.0)
    target: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    fov_y: float = 70.0
    roll: float = 0.0
    near: float = 0.1
    far: float = 2000.0


@dataclass
class Lighting:
    sun_dir: tuple = (-0.4, -1.0, -0.3)      # direction the light TRAVELS
    sun_color: tuple = (1.0, 0.96, 0.88)
    sun_intensity: float = 1.0
    ambient: tuple = (0.55, 0.6, 0.7)
    sky_top: object = "#4f9bff"
    sky_bottom: object = "#d3ecff"
    fog_color: object = None
    fog_density: float = 0.0
    shadow_extent: float = 60.0              # ortho half-size around camera target
    shadow_res: int = 2048
    shadow_softness: float = 1.3             # PCF kernel spacing in texels


# material -> (spec, shininess, fresnel, metal, base_alpha)
_MATERIALS = {
    "plastic": (0, 0.10, 24.0, 0.04, 0.0, 1.0),
    "smooth": (1, 0.40, 64.0, 0.12, 0.0, 1.0),
    "grass": (2, 0.0, 8.0, 0.0, 0.0, 1.0),
    "brick": (3, 0.02, 8.0, 0.0, 0.0, 1.0),
    "wood": (4, 0.06, 16.0, 0.0, 0.0, 1.0),
    "concrete": (5, 0.0, 8.0, 0.0, 0.0, 1.0),
    "glass": (6, 0.9, 160.0, 0.45, 0.0, 0.45),
    "neon": (7, 0.0, 8.0, 0.0, 0.0, 1.0),
    "metal": (8, 0.6, 40.0, 0.2, 1.0, 1.0),
}

_SHADOW_VS = """
#version 330
uniform mat4 u_lvp; uniform mat4 u_model;
in vec3 in_pos;
void main(){ gl_Position = u_lvp * u_model * vec4(in_pos, 1.0); }
"""
_SHADOW_FS = """
#version 330
void main(){}
"""

_MAIN_VS = """
#version 330
uniform mat4 u_vp; uniform mat4 u_model; uniform mat3 u_nm;
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv;
out vec3 v_wpos; out vec3 v_n; out vec2 v_uv;
void main(){
    vec4 w = u_model * vec4(in_pos, 1.0);
    v_wpos = w.xyz;
    v_n = u_nm * in_nrm;
    v_uv = in_uv;
    gl_Position = u_vp * w;
}
"""

_MAIN_FS = """
#version 330
in vec3 v_wpos; in vec3 v_n; in vec2 v_uv;
out vec4 f_color;
uniform vec3 u_eye; uniform vec3 u_toSun; uniform vec3 u_sunCol;
uniform vec3 u_ambUp; uniform vec3 u_ambDn; uniform vec3 u_skyTop; uniform vec3 u_skyBot;
uniform vec3 u_fogCol; uniform float u_fogD;
uniform sampler2D u_tex; uniform sampler2DShadow u_shadow;
uniform mat4 u_lvp; uniform float u_texel; uniform float u_zrange; uniform float u_shadowRes;
uniform float u_shadowOn; uniform float u_soft;
uniform vec4 u_item[4];  // 0: color+alpha, 1: emissive,spec,shin,fres, 2: mat,hastex,recv,metal, 3: uvscale

float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
float vnoise(vec2 p){
    vec2 i = floor(p), fr = fract(p); fr = fr*fr*(3.0-2.0*fr);
    return mix(mix(hash21(i), hash21(i+vec2(1,0)), fr.x), mix(hash21(i+vec2(0,1)), hash21(i+vec2(1,1)), fr.x), fr.y);
}

float shadowFactor(vec3 wp, vec3 n, float ndl){
    if (u_shadowOn < 0.5) return 1.0;
    float slope = clamp(1.0 - ndl, 0.0, 1.0);
    vec3 p = wp + n * u_texel * (1.2 + 2.2 * slope);          // normal-offset bias
    vec4 lp = u_lvp * vec4(p, 1.0);
    vec3 c = lp.xyz * 0.5 + 0.5;
    float bias = (u_texel * (0.6 + 1.5 * slope)) / u_zrange;   // slope-scaled depth bias
    float inv = 1.0 / u_shadowRes;
    float s = 0.0;
    for (int j = -1; j <= 1; j++)
        for (int i = -1; i <= 1; i++)
            s += texture(u_shadow, vec3(c.xy + vec2(float(i), float(j)) * inv * u_soft, c.z - bias));
    s /= 9.0;
    float edge = min(min(c.x, 1.0 - c.x), min(c.y, 1.0 - c.y));
    float fade = smoothstep(0.0, 0.08, edge);
    if (c.z > 1.0) fade = 0.0;
    return mix(1.0, s, fade);
}

vec3 procedural(int mat, vec3 wp, vec3 n){
    vec3 an = abs(n);
    vec2 q = an.y > 0.6 ? wp.xz : (an.x > an.z ? wp.zy : wp.xy);
    if (mat == 2) {          // grass
        float a = vnoise(q * 1.0), b = vnoise(q * 4.0);
        return vec3(0.93 + 0.10 * a + 0.04 * b, 0.93 + 0.12 * a + 0.04 * b, 0.93 + 0.08 * a);
    }
    if (mat == 3) {          // brick: 2x1 stud bricks, running bond
        vec2 p = vec2(q.x / 2.0, q.y);
        float row = floor(p.y);
        p.x += 0.5 * mod(row, 2.0);
        vec2 f = fract(p);
        float mortar = step(f.x, 0.04) + step(f.y, 0.07);
        float v = hash21(vec2(floor(p.x), row));
        float k = 0.93 + 0.1 * v;
        return vec3(mix(k, 0.78, clamp(mortar, 0.0, 1.0)));
    }
    if (mat == 4) {          // wood planks
        float row = floor(q.y * 1.0);
        float g = vnoise(vec2(q.x * 0.6 + row * 7.1, q.y * 14.0));
        float seam = step(fract(q.y), 0.05);
        return vec3((0.92 + 0.12 * g) * (1.0 - 0.18 * seam));
    }
    if (mat == 5) {          // concrete
        float a = vnoise(q * 3.0), b = vnoise(q * 11.0);
        vec2 sf = fract(q / 8.0);
        float seam = step(sf.x, 0.006) + step(sf.y, 0.006);
        return vec3((0.95 + 0.05 * a + 0.04 * b) * (1.0 - 0.12 * clamp(seam, 0.0, 1.0)));
    }
    return vec3(1.0);
}

void main(){
    vec4 it0 = u_item[0], it1 = u_item[1], it2 = u_item[2], it3 = u_item[3];
    int mat = int(it2.x + 0.5);
    vec3 N = normalize(v_n);
    vec3 V = normalize(u_eye - v_wpos);
    vec3 albedo = it0.rgb;
    if (it2.y > 0.5) {
        vec4 t = texture(u_tex, v_uv * it3.xy);
        albedo *= mix(vec3(1.0), t.rgb, t.a);
    } else if (mat >= 2 && mat <= 5) {
        albedo *= procedural(mat, v_wpos, N);
    }
    vec3 col;
    if (mat == 7) {                       // neon: unlit
        col = albedo * (1.25 + it1.x);
    } else {
        float ndl = dot(N, u_toSun);
        float wrap = 0.18;
        float diff = clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0);
        float sh = it2.z > 0.5 ? shadowFactor(v_wpos, N, max(ndl, 0.0)) : 1.0;
        vec3 amb = mix(u_ambDn, u_ambUp, N.y * 0.5 + 0.5);
        vec3 direct = u_sunCol * diff * sh;
        col = albedo * (amb + direct);
        float spec = it1.y;
        if (spec > 0.0) {
            vec3 H = normalize(u_toSun + V);
            float s = pow(max(dot(N, H), 0.0), it1.z) * step(0.0, ndl) * sh;
            col += mix(vec3(1.0), albedo, it2.w) * u_sunCol * s * spec;
        }
        float fres = it1.w;
        if (fres > 0.0 || it2.w > 0.0) {
            float fr = pow(1.0 - max(dot(N, V), 0.0), 4.0);
            vec3 R = reflect(-V, N);
            float up = clamp(R.y, 0.0, 1.0);
            vec3 env = R.y > 0.0 ? mix(u_skyBot, u_skyTop, pow(up, 0.6)) : u_ambDn * 0.8;
            float amt = clamp(fres * (0.35 + 1.4 * fr) + it2.w * 0.35, 0.0, 0.85);
            col = mix(col, env * mix(vec3(1.0), albedo, it2.w), amt);
        }
        col += albedo * it1.x * 1.5;      // generic emissive
    }
    if (u_fogD > 0.0) {
        float d = length(u_eye - v_wpos);
        float ff = 1.0 - exp(-d * u_fogD);
        col = mix(col, u_fogCol, clamp(ff, 0.0, 1.0));
    }
    f_color = vec4(col, it0.a);
}
"""

_SKY_VS = """
#version 330
out vec2 v_ndc;
void main(){
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    v_ndc = p * 2.0 - 1.0;
    gl_Position = vec4(v_ndc, 0.9999, 1.0);
}
"""
_SKY_FS = """
#version 330
in vec2 v_ndc; out vec4 f_color;
uniform vec3 u_fwd; uniform vec3 u_right; uniform vec3 u_up; uniform float u_tanH; uniform float u_aspect;
uniform vec3 u_top; uniform vec3 u_bot; uniform vec3 u_toSun; uniform vec3 u_sunCol; uniform float u_sunI;
void main(){
    vec3 d = normalize(u_fwd + u_right * (v_ndc.x * u_tanH * u_aspect) + u_up * (v_ndc.y * u_tanH));
    float t = clamp(d.y * 1.5, 0.0, 1.0);
    t = pow(t, 0.7);
    vec3 c = mix(u_bot, u_top, t);
    float sd = max(dot(d, u_toSun), 0.0);
    c += u_sunCol * u_sunI * (pow(sd, 400.0) * 3.0 + pow(sd, 48.0) * 0.18 + pow(sd, 6.0) * 0.04);
    f_color = vec4(c, 1.0);
}
"""


def _mat_bytes(m) -> bytes:
    return np.ascontiguousarray(np.asarray(m, np.float64).T, np.float32).tobytes()


class _MeshGL:
    __slots__ = ("mesh", "vbo", "ibo", "vao_main", "vao_shadow", "center", "n")


class Renderer:
    def __init__(self, width=1080, height=1920, samples=4, headless=True, quality="final",
                 ctx: Optional[moderngl.Context] = None):
        q = QUALITY.get(quality, QUALITY["final"])
        self.quality = quality
        self.width, self.height = int(width), int(height)
        self.shadow_cap = q["shadow_cap"]
        self._own_ctx = ctx is None
        if ctx is None:
            ctx = self._make_context(headless)
        self.ctx = ctx
        max_s = int(ctx.info.get("GL_MAX_SAMPLES", 4) or 4)
        samples = int(samples)
        if quality == "preview":
            samples = min(samples, q["samples"])
        self.samples = 0 if samples <= 1 else min(samples, max_s)
        self.cull_backfaces = True
        self._build()
        self._mesh_cache: "OrderedDict[int, _MeshGL]" = OrderedDict()
        self._tex_cache: "OrderedDict[object, moderngl.Texture]" = OrderedDict()
        self._shadow_res = 0
        self._closed = False

    @classmethod
    def preview(cls, width=360, height=640, **kw):
        return cls(width, height, samples=2, quality="preview", **kw)

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _make_context(headless):
        if headless:
            try:
                return moderngl.create_standalone_context(backend="egl", require=330)
            except Exception:
                pass
        return moderngl.create_standalone_context(require=330)

    def _build(self):
        ctx, w, h = self.ctx, self.width, self.height
        self.prog_shadow = ctx.program(vertex_shader=_SHADOW_VS, fragment_shader=_SHADOW_FS)
        self.prog_main = ctx.program(vertex_shader=_MAIN_VS, fragment_shader=_MAIN_FS)
        self.prog_sky = ctx.program(vertex_shader=_SKY_VS, fragment_shader=_SKY_FS)
        self.vao_sky = ctx.vertex_array(self.prog_sky, [])
        self.post = PostProcessor(ctx, w, h)
        # main (optionally multisampled) HDR target
        if self.samples:
            self._rb_color = ctx.renderbuffer((w, h), 4, samples=self.samples, dtype="f2")
            self._rb_depth = ctx.depth_renderbuffer((w, h), samples=self.samples)
            self.fbo_main = ctx.framebuffer([self._rb_color], self._rb_depth)
        else:
            self._rb_depth = ctx.depth_renderbuffer((w, h))
            self.fbo_main = ctx.framebuffer([self.post.scene_tex], self._rb_depth)
        self.white = ctx.texture((1, 1), 4, np.array([255, 255, 255, 255], np.uint8).tobytes())
        self._shadow_tex = None
        self._u = {n: self.prog_main[n] for n in ("u_vp", "u_model", "u_nm", "u_item") if n in self.prog_main}

    def _ensure_shadow(self, res):
        res = int(res)
        if self.shadow_cap:
            res = min(res, self.shadow_cap)
        res = max(64, res)
        if res == self._shadow_res and self._shadow_tex is not None:
            return res
        if self._shadow_tex is not None:
            self._shadow_fbo.release()
            self._shadow_tex.release()
        t = self.ctx.depth_texture((res, res))
        t.compare_func = "<="
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        t.repeat_x = t.repeat_y = False
        self._shadow_tex = t
        self._shadow_fbo = self.ctx.framebuffer(depth_attachment=t)
        self._shadow_res = res
        return res

    # --------------------------------------------------------------- caches
    def _get_mesh(self, mesh: Mesh) -> _MeshGL:
        k = id(mesh)
        e = self._mesh_cache.get(k)
        if e is not None and e.mesh is mesh and e.n == len(mesh.positions):
            self._mesh_cache.move_to_end(k)
            return e
        data = np.concatenate([mesh.positions, mesh.normals, mesh.uvs], axis=1).astype("f4")
        e = _MeshGL()
        e.mesh, e.n = mesh, len(mesh.positions)
        e.vbo = self.ctx.buffer(data.tobytes())
        e.ibo = self.ctx.buffer(np.ascontiguousarray(mesh.indices, "u4").tobytes())
        e.vao_main = self.ctx.vertex_array(self.prog_main, [(e.vbo, "3f 3f 2f", "in_pos", "in_nrm", "in_uv")], e.ibo)
        e.vao_shadow = self.ctx.vertex_array(self.prog_shadow, [(e.vbo, "3f 20x", "in_pos")], e.ibo)
        lo, hi = mesh.positions.min(0), mesh.positions.max(0)
        e.center = np.append((lo + hi) * 0.5, 1.0).astype(np.float64)
        old = self._mesh_cache.pop(k, None)
        if old is not None:
            self._free_mesh(old)
        self._mesh_cache[k] = e
        while len(self._mesh_cache) > 4096:
            _, old = self._mesh_cache.popitem(last=False)
            self._free_mesh(old)
        return e

    @staticmethod
    def _free_mesh(e):
        for o in (e.vao_main, e.vao_shadow, e.vbo, e.ibo):
            try:
                o.release()
            except Exception:
                pass

    def _get_texture(self, item: DrawItem):
        tx = item.texture
        if tx is None:
            return self.white
        if isinstance(tx, (str, os.PathLike)):
            k = ("path", os.fspath(tx))
        elif item.key is not None:
            k = ("key", item.key)
        else:
            k = ("id", id(tx))
        t = self._tex_cache.get(k)
        if t is not None:
            self._tex_cache.move_to_end(k)
            return t
        arr = self._to_rgba(tx)
        t = self.ctx.texture((arr.shape[1], arr.shape[0]), 4, np.ascontiguousarray(arr[::-1]).tobytes())
        t.repeat_x = t.repeat_y = True
        t.build_mipmaps()
        t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        try:
            t.anisotropy = 8.0
        except Exception:
            pass
        self._tex_cache[k] = t
        if k[0] == "id":                  # keep the source alive so id() can't be recycled
            t._src_ref = tx
        while len(self._tex_cache) > 256:
            _, old = self._tex_cache.popitem(last=False)
            old.release()
        return t

    @staticmethod
    def _to_rgba(tx) -> np.ndarray:
        from PIL import Image
        if isinstance(tx, (str, os.PathLike)):
            tx = Image.open(tx)
        if isinstance(tx, Image.Image):
            return np.asarray(tx.convert("RGBA"), np.uint8)
        a = np.asarray(tx)
        if a.dtype != np.uint8:
            a = np.clip(a * (255.0 if a.max() <= 1.0 else 1.0), 0, 255).astype(np.uint8)
        if a.ndim == 2:
            a = np.stack([a] * 3, -1)
        if a.shape[2] == 3:
            a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, np.uint8)], 2)
        return a

    # --------------------------------------------------------------- render
    def render(self, items, camera: CameraState, lighting: Lighting, post: Optional[PostFx] = None) -> np.ndarray:
        raw = self._render_raw(items, camera, lighting, post)
        img = np.frombuffer(raw, np.uint8).reshape(self.height, self.width, 3)
        return np.ascontiguousarray(img[::-1])

    def _render_raw(self, items, camera, lighting, post):
        ctx = self.ctx
        items = list(items)
        n = len(items)
        post = post if post is not None else PostFx()
        W, H = self.width, self.height
        aspect = W / H

        eye = np.asarray(camera.eye, np.float64)
        view = look_at(eye, camera.target, camera.up, camera.roll)
        proj = perspective(camera.fov_y, aspect, camera.near, camera.far)
        vp = proj @ view

        # per-item data -----------------------------------------------------
        models = np.empty((n, 4, 4), np.float64)
        for i, it in enumerate(items):
            models[i] = it.model
        if n:
            nm = np.transpose(np.linalg.inv(models[:, :3, :3]), (0, 2, 1))
            dets = np.linalg.det(models[:, :3, :3])
        meshes = [self._get_mesh(it.mesh) for it in items]
        opaque, blended = [], []
        for i, it in enumerate(items):
            mname = it.material if it.material in _MATERIALS else "plastic"
            alpha = 1.0 - float(it.transparency)
            if mname == "glass" and it.transparency <= 0.0:
                alpha = _MATERIALS["glass"][5]
            (blended if alpha < 0.999 else opaque).append(i)
            # stash alpha
        # sun / light matrices ----------------------------------------------
        L = normalize(lighting.sun_dir)
        to_sun = -L
        shadow_on = lighting.sun_intensity > 0 and any(
            it.cast_shadow and it.transparency < 0.5 and it.material != "glass" for it in items)
        res = self._ensure_shadow(lighting.shadow_res)
        if shadow_on:
            lvp, texel, zrange = self._shadow_matrix(L, camera, lighting.shadow_extent, res)
            self._shadow_pass(items, meshes, models, lvp)
        else:
            lvp, texel, zrange = np.eye(4), 1.0, 1.0

        # main pass ------------------------------------------------------------
        self.fbo_main.use()
        ctx.viewport = (0, 0, W, H)
        ctx.clear(0, 0, 0, 1, depth=1.0)
        top = np.array(_color(lighting.sky_top)), np.array(_color(lighting.sky_bottom))
        sky_top, sky_bot = top
        sun_col = np.array(_color(lighting.sun_color)) * lighting.sun_intensity
        self._draw_sky(view, camera, aspect, sky_top, sky_bot, to_sun, np.array(_color(lighting.sun_color)),
                       lighting.sun_intensity)

        amb = np.array(lighting.ambient, np.float64)
        amb_up = amb * (0.85 + 0.35 * sky_top) * 0.5 + amb * 0.5
        amb_dn = amb * np.array([0.62, 0.55, 0.48]) * 0.9
        fog_c = _color(lighting.fog_color) if lighting.fog_color is not None else tuple(sky_bot)
        P = self.prog_main
        P["u_vp"].write(_mat_bytes(vp))
        P["u_eye"].value = tuple(eye)
        P["u_toSun"].value = tuple(to_sun)
        P["u_sunCol"].value = tuple(sun_col)
        P["u_ambUp"].value = tuple(amb_up)
        P["u_ambDn"].value = tuple(amb_dn)
        P["u_skyTop"].value = tuple(sky_top)
        P["u_skyBot"].value = tuple(sky_bot)
        P["u_fogCol"].value = tuple(fog_c)
        P["u_fogD"].value = float(lighting.fog_density)
        P["u_lvp"].write(_mat_bytes(lvp))
        P["u_texel"].value = float(texel)
        P["u_zrange"].value = float(zrange)
        P["u_shadowRes"].value = float(res)
        P["u_shadowOn"].value = 1.0 if shadow_on else 0.0
        P["u_soft"].value = float(lighting.shadow_softness)
        P["u_tex"].value = 0
        P["u_shadow"].value = 1
        if self._shadow_tex is not None:
            self._shadow_tex.use(1)

        ctx.enable(moderngl.DEPTH_TEST)
        ctx.depth_func = "<="
        ctx.disable(moderngl.BLEND)
        if self.cull_backfaces:
            ctx.enable(moderngl.CULL_FACE)
        else:
            ctx.disable(moderngl.CULL_FACE)

        def draw(i):
            it, me = items[i], meshes[i]
            mname = it.material if it.material in _MATERIALS else "plastic"
            mid, spec, shin, fres, metal, base_a = _MATERIALS[mname]
            alpha = 1.0 - float(it.transparency)
            if mname == "glass" and it.transparency <= 0.0:
                alpha = base_a
            col = _color(it.color)
            tex = self._get_texture(it)
            hastex = 1.0 if it.texture is not None else 0.0
            tex.use(0)
            uvs = it.uv_scale if it.uv_scale is not None else (1.0, 1.0)
            emis = float(it.emissive) + (0.0 if mname != "neon" else 0.0)
            params = np.array([col[0], col[1], col[2], alpha,
                               emis, spec, shin, fres,
                               mid, hastex, 1.0 if it.receive_shadow else 0.0, metal,
                               uvs[0], uvs[1], 0.0, 0.0], np.float32)
            P["u_item"].write(params.tobytes())
            P["u_model"].write(_mat_bytes(models[i]))
            P["u_nm"].write(np.ascontiguousarray(nm[i].T, np.float32).tobytes())
            ctx.front_face = "cw" if dets[i] < 0 else "ccw"
            me.vao_main.render(moderngl.TRIANGLES)

        for i in opaque:
            draw(i)
        if blended:
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            ctx.depth_mask = False
            order = sorted(blended, key=lambda i: -float(np.linalg.norm((models[i] @ meshes[i].center)[:3] - eye)))
            for i in order:
                draw(i)
            ctx.depth_mask = True
            ctx.disable(moderngl.BLEND)
        ctx.front_face = "ccw"

        # resolve + post ---------------------------------------------------------
        if self.samples:
            ctx.copy_framebuffer(self.post.scene_fbo, self.fbo_main)
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        return self.post.process(post, tex_unit_base=2)

    def _draw_sky(self, view, camera, aspect, top, bot, to_sun, sun_col, sun_i):
        ctx = self.ctx
        r, u, f = view[0, :3], view[1, :3], -view[2, :3]
        S = self.prog_sky
        S["u_fwd"].value = tuple(f)
        S["u_right"].value = tuple(r)
        S["u_up"].value = tuple(u)
        S["u_tanH"].value = math.tan(math.radians(camera.fov_y) * 0.5)
        S["u_aspect"].value = aspect
        S["u_top"].value = tuple(top)
        S["u_bot"].value = tuple(bot)
        S["u_toSun"].value = tuple(to_sun)
        S["u_sunCol"].value = tuple(sun_col)
        S["u_sunI"].value = float(sun_i)
        ctx.disable(moderngl.DEPTH_TEST | moderngl.CULL_FACE | moderngl.BLEND)
        self.vao_sky.render(moderngl.TRIANGLES, vertices=3)

    def _shadow_matrix(self, L, camera, extent, res):
        """Ortho light matrix, fixed orientation, snapped to shadow texels (no shimmer)."""
        fwd = L
        up = np.array([0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.99 else np.array([0.0, 0.0, 1.0])
        right = normalize(np.cross(fwd, up))
        lup = np.cross(right, fwd)
        extent = max(float(extent), 1.0)
        texel = 2.0 * extent / res
        c = np.asarray(camera.target, np.float64)
        cx, cy, cz = float(c @ right), float(c @ lup), float(c @ fwd)
        cx = math.floor(cx / texel) * texel
        cy = math.floor(cy / texel) * texel
        zr = extent * 4.0                       # half depth range: casters up to 4*extent toward the sun
        view = np.eye(4)
        view[0, :3], view[1, :3], view[2, :3] = right, lup, -fwd
        # place origin at snapped centre: translate so (cx,cy,cz) -> 0
        view[0, 3], view[1, 3], view[2, 3] = -cx, -cy, cz
        proj = np.eye(4)
        proj[0, 0], proj[1, 1], proj[2, 2] = 1.0 / extent, 1.0 / extent, -1.0 / zr
        return proj @ view, texel, 2.0 * zr

    def _shadow_pass(self, items, meshes, models, lvp):
        ctx = self.ctx
        self._shadow_fbo.use()
        ctx.viewport = (0, 0, self._shadow_res, self._shadow_res)
        ctx.clear(depth=1.0)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.depth_func = "<"
        ctx.disable(moderngl.CULL_FACE | moderngl.BLEND)
        S = self.prog_shadow
        S["u_lvp"].write(_mat_bytes(lvp))
        for i, it in enumerate(items):
            if not it.cast_shadow or it.transparency >= 0.5 or it.material in ("glass",):
                continue
            S["u_model"].write(_mat_bytes(models[i]))
            meshes[i].vao_shadow.render(moderngl.TRIANGLES)
        ctx.depth_func = "<="

    # ---------------------------------------------------------- motion blur
    def render_motion_blur(self, frame_fn: Callable, t: float, shutter: float = 0.5, subsamples: int = 4,
                           fps: float = 30.0) -> np.ndarray:
        """Average `subsamples` renders spread over the shutter interval centred on t.

        shutter is a fraction of one frame at `fps` (0.5 = 180 degree shutter).
        frame_fn(t) -> (items, camera, lighting, post).
        """
        n = max(1, int(subsamples))
        if n == 1 or shutter <= 0:
            return self.render(*frame_fn(t))
        dur = shutter / fps
        acc = None
        for i in range(n):
            ti = t + ((i + 0.5) / n - 0.5) * dur
            items, cam, light, post = frame_fn(ti)
            img = self._render_raw(items, cam, light, post)
            a = np.frombuffer(img, np.uint8).astype(np.float32)
            acc = a if acc is None else acc + a
        out = np.clip(acc / n + 0.5, 0, 255).astype(np.uint8).reshape(self.height, self.width, 3)
        return np.ascontiguousarray(out[::-1])

    # ---------------------------------------------------------------- close
    def close(self):
        if self._closed:
            return
        self._closed = True
        for e in self._mesh_cache.values():
            self._free_mesh(e)
        self._mesh_cache.clear()
        for t in self._tex_cache.values():
            t.release()
        self._tex_cache.clear()
        try:
            self.post.release()
        except Exception:
            pass
        if self._own_ctx:
            try:
                self.ctx.release()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
