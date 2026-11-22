"""Post-processing: PostFx parameters + GPU PostProcessor (bloom, grade, blur, chroma, grain...)."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import moderngl

FS_VS = """
#version 330
out vec2 v_uv;
void main(){
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    v_uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""


@dataclass
class PostFx:
    """All effects are no-ops at value 0 except exposure/saturation/contrast (1 = neutral)."""
    bloom: float = 0.15            # bloom strength added to the image
    bloom_threshold: float = 0.9   # HDR luminance where bloom starts
    vignette: float = 0.15
    saturation: float = 1.1
    contrast: float = 1.05
    exposure: float = 1.0
    grain: float = 0.0             # film grain amplitude (0.03 = subtle)
    chroma: float = 0.0            # radial chromatic aberration (0.004 = visible)
    blur_dir: tuple = (0.0, 0.0)   # direction of motion blur in screen fraction (dx, dy); length ~ blur size
    blur_amount: float = 0.0       # multiplier on blur_dir (0 = off)
    flash: float = 0.0             # add white 0..1
    fade: float = 0.0              # fade to black 0..1
    seed: int = 0                  # grain seed (deterministic)

    @classmethod
    def off(cls) -> "PostFx":
        """Neutral grade, no effects at all."""
        return cls(bloom=0.0, vignette=0.0, saturation=1.0, contrast=1.0, exposure=1.0)


_BRIGHT = """
#version 330
uniform sampler2D u_src; uniform float u_th; uniform vec2 u_px;
in vec2 v_uv; out vec4 f;
void main(){
    vec3 c = vec3(0.0);
    c += texture(u_src, v_uv + u_px*vec2(-1.0,-1.0)).rgb;
    c += texture(u_src, v_uv + u_px*vec2( 1.0,-1.0)).rgb;
    c += texture(u_src, v_uv + u_px*vec2(-1.0, 1.0)).rgb;
    c += texture(u_src, v_uv + u_px*vec2( 1.0, 1.0)).rgb;
    c *= 0.25;
    float l = max(c.r, max(c.g, c.b));
    float k = clamp((l - u_th) / max(u_th * 0.6, 1e-3), 0.0, 1.0);
    k = k * k * (3.0 - 2.0 * k);
    f = vec4(c * k, 1.0);
}
"""
_DOWN = """
#version 330
uniform sampler2D u_src; uniform vec2 u_px;
in vec2 v_uv; out vec4 f;
void main(){
    vec3 c = texture(u_src, v_uv + u_px*vec2(-1.0,-1.0)).rgb + texture(u_src, v_uv + u_px*vec2(1.0,-1.0)).rgb
           + texture(u_src, v_uv + u_px*vec2(-1.0,1.0)).rgb + texture(u_src, v_uv + u_px*vec2(1.0,1.0)).rgb;
    f = vec4(c*0.25, 1.0);
}
"""
_BLUR = """
#version 330
uniform sampler2D u_src; uniform vec2 u_dir;
in vec2 v_uv; out vec4 f;
void main(){
    // 9-tap gaussian folded into 5 bilinear taps
    vec3 c = texture(u_src, v_uv).rgb * 0.2270270270;
    c += texture(u_src, v_uv + u_dir*1.3846153846).rgb * 0.3162162162;
    c += texture(u_src, v_uv - u_dir*1.3846153846).rgb * 0.3162162162;
    c += texture(u_src, v_uv + u_dir*3.2307692308).rgb * 0.0702702703;
    c += texture(u_src, v_uv - u_dir*3.2307692308).rgb * 0.0702702703;
    f = vec4(c, 1.0);
}
"""
_COMPOSITE = """
#version 330
uniform sampler2D u_scene; uniform sampler2D u_b0; uniform sampler2D u_b1; uniform sampler2D u_b2; uniform sampler2D u_b3;
uniform vec2 u_res;
uniform float u_bloom, u_vig, u_sat, u_con, u_exp, u_grain, u_chroma, u_flash, u_fade, u_seed;
uniform vec2 u_blur;
in vec2 v_uv; out vec4 f;

float hash(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }

vec3 fetch(vec2 uv){
    vec3 c;
    if (u_chroma > 0.0) {
        vec2 d = (uv - 0.5) * u_chroma;
        c = vec3(texture(u_scene, uv + d).r, texture(u_scene, uv).g, texture(u_scene, uv - d).b);
    } else {
        c = texture(u_scene, uv).rgb;
    }
    return c;
}

void main(){
    vec2 uv = v_uv;
    vec3 c;
    if (length(u_blur) > 1e-6) {
        c = vec3(0.0);
        const int N = 17;
        for (int i = 0; i < N; i++) {
            float t = float(i) / float(N - 1) - 0.5;
            c += fetch(uv + u_blur * t);
        }
        c /= float(N);
    } else {
        c = fetch(uv);
    }
    if (u_bloom > 0.0) {
        vec3 b = texture(u_b0, uv).rgb * 0.5 + texture(u_b1, uv).rgb * 0.7
               + texture(u_b2, uv).rgb * 0.9 + texture(u_b3, uv).rgb * 1.1;
        c += b * u_bloom;
    }
    c *= u_exp;
    // soft shoulder: linear to 0.8, then smooth roll-off (keeps saturation, avoids hard clip)
    vec3 over = max(c - 0.8, 0.0);
    c = min(c, 0.8) + 0.2 * (1.0 - exp(-over / 0.2)) ;
    c = max(c, 0.0);
    float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
    c = mix(vec3(l), c, u_sat);
    c = (c - 0.5) * u_con + 0.5;
    vec2 q = (uv - 0.5) * vec2(1.0, 1.0) * 1.4142;
    float vd = smoothstep(0.35, 1.15, length(q));
    c *= 1.0 - u_vig * vd * vd * 1.6;
    if (u_grain > 0.0) {
        float n = hash(gl_FragCoord.xy + u_seed * 17.31) + hash(gl_FragCoord.xy * 1.7 + u_seed * 3.7) - 1.0;
        c += n * u_grain;
    }
    c += u_flash;
    c *= 1.0 - u_fade;
    // triangular dither against banding (deterministic)
    float d = hash(gl_FragCoord.xy) + hash(gl_FragCoord.xy + 71.7) - 1.0;
    c += d / 255.0;
    f = vec4(clamp(c, 0.0, 1.0), 1.0);
}
"""


class PostProcessor:
    LEVELS = 4

    def __init__(self, ctx: moderngl.Context, width: int, height: int):
        self.ctx, self.w, self.h = ctx, width, height
        self.vao_cache = {}
        self.progs = {n: ctx.program(vertex_shader=FS_VS, fragment_shader=s)
                      for n, s in (("bright", _BRIGHT), ("down", _DOWN), ("blur", _BLUR), ("comp", _COMPOSITE))}
        self.vaos = {n: ctx.vertex_array(p, []) for n, p in self.progs.items()}
        # scene (resolved HDR) target
        self.scene_tex = self._tex(width, height, 4, "f2")
        self.scene_fbo = ctx.framebuffer(color_attachments=[self.scene_tex])
        # bloom pyramid: level i at size/2^(i+1); A/B ping-pong
        self.levels = []
        for i in range(self.LEVELS):
            lw, lh = max(1, width >> (i + 1)), max(1, height >> (i + 1))
            a, b = self._tex(lw, lh, 4, "f2"), self._tex(lw, lh, 4, "f2")
            self.levels.append((lw, lh, a, ctx.framebuffer([a]), b, ctx.framebuffer([b])))
        self.out_tex = ctx.texture((width, height), 3, dtype="f1")
        self.out_fbo = ctx.framebuffer(color_attachments=[self.out_tex])

    def _tex(self, w, h, comps, dtype):
        t = self.ctx.texture((w, h), comps, dtype=dtype)
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        t.repeat_x = t.repeat_y = False
        return t

    def _draw(self, name, fbo, vp, **uniforms):
        prog = self.progs[name]
        for k, v in uniforms.items():
            if k in prog:
                prog[k].value = v
        fbo.use()
        self.ctx.viewport = vp
        self.vaos[name].render(moderngl.TRIANGLES, vertices=3)

    def process(self, fx: PostFx, tex_unit_base: int = 0) -> bytes:
        """Run post on self.scene_tex; returns raw RGB bytes (bottom-up rows)."""
        ctx = self.ctx
        ctx.disable(moderngl.DEPTH_TEST | moderngl.BLEND | moderngl.CULL_FACE)
        u = tex_unit_base
        bloom_on = fx.bloom > 0.0
        if bloom_on:
            # bright pass into level 0 (A), then successive downsample, then blur each level
            lw, lh, a0, f0, b0, fb0 = self.levels[0]
            self.scene_tex.use(u)
            self._draw("bright", f0, (0, 0, lw, lh), u_src=u, u_th=float(fx.bloom_threshold),
                       u_px=(1.0 / self.w, 1.0 / self.h))
            prev = a0
            for i in range(1, self.LEVELS):
                lw, lh, a, fa, b, fb = self.levels[i]
                pw, ph = self.levels[i - 1][0], self.levels[i - 1][1]
                prev.use(u)
                self._draw("down", fa, (0, 0, lw, lh), u_src=u, u_px=(1.0 / pw, 1.0 / ph))
                prev = a
            for i in range(self.LEVELS):
                lw, lh, a, fa, b, fb = self.levels[i]
                a.use(u)
                self._draw("blur", fb, (0, 0, lw, lh), u_src=u, u_dir=(1.0 / lw, 0.0))
                b.use(u)
                self._draw("blur", fa, (0, 0, lw, lh), u_src=u, u_dir=(0.0, 1.0 / lh))
        self.scene_tex.use(u)
        for i in range(self.LEVELS):
            self.levels[i][2].use(u + 1 + i)
        bd = np.asarray(fx.blur_dir, np.float64) * float(fx.blur_amount)
        self._draw("comp", self.out_fbo, (0, 0, self.w, self.h),
                   u_scene=u, u_b0=u + 1, u_b1=u + 2, u_b2=u + 3, u_b3=u + 4,
                   u_res=(self.w, self.h), u_bloom=float(fx.bloom) if bloom_on else 0.0,
                   u_vig=float(fx.vignette), u_sat=float(fx.saturation), u_con=float(fx.contrast),
                   u_exp=float(fx.exposure), u_grain=float(fx.grain), u_chroma=float(fx.chroma),
                   u_flash=float(fx.flash), u_fade=float(fx.fade), u_seed=float(fx.seed % 9973),
                   u_blur=(float(bd[0]), float(bd[1])))
        return self.out_fbo.read(components=3, alignment=1)

    def release(self):
        for o in [self.scene_fbo, self.scene_tex, self.out_fbo, self.out_tex, *self.vaos.values(), *self.progs.values()]:
            try:
                o.release()
            except Exception:
                pass
        for lv in self.levels:
            for o in (lv[2], lv[3], lv[4], lv[5]):
                try:
                    o.release()
                except Exception:
                    pass
