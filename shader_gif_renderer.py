#!/usr/bin/env python
"""
Batch render ISF/GLSL fragment shaders into animated GIF previews.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import imageio.v3 as iio
import moderngl
import numpy as np
from PIL import Image


VERTEX_SHADER = """
#version 330
in vec2 in_position;
void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
}
"""


DEFAULT_FRAGMENT_PREFIX = """
#version 330
out vec4 fragColor;
#define gl_FragColor fragColor

// GLSL compatibility macros (for older GLSL syntax)
#define texture2D texture
#define texture2DProj textureProj
#define textureCube texture

// ISF texture sampling macros
#define IMG_THIS_PIXEL(sampler) texture(sampler, isf_FragNormCoord)
#define IMG_NORM_PIXEL(sampler, coord) texture(sampler, coord)
#define IMG_PIXEL(sampler, coord) texture(sampler, coord)
#define IMG_THIS_NORM_PIXEL(sampler) texture(sampler, isf_FragNormCoord)
"""


TYPE_TO_GLSL = {
    "float": "float",
    "int": "int",
    "long": "int",  # long maps to int in GLSL
    "bool": "bool",
    "point2D": "vec2",
    "point3D": "vec3",
    "color": "vec3",
    "event": "bool",  # event types are typically used as boolean triggers
    "image": "sampler2D",
}

EXTRA_TYPE_MAP = {
    "float": ("float", float),
    "int": ("int", int),
    "bool": ("bool", lambda v: bool(int(float(v)))),
    "vec2": ("vec2", lambda v: tuple(float(x) for x in v.split(",")[:2])),
    "vec3": ("vec3", lambda v: tuple(float(x) for x in v.split(",")[:3])),
}


@dataclass
class ShaderInput:
    name: str
    type: str
    default: Any


def parse_metadata(source: str) -> Dict[str, Any]:
    # Find the metadata block between /*{ and }*/
    start_match = re.search(r"/\*\s*\{", source)
    if not start_match:
        return {}
    start_pos = start_match.end() - 1  # Position of the opening {

    # Find matching closing brace by counting braces
    brace_count = 0
    i = start_pos
    while i < len(source):
        if source[i] == "{":
            brace_count += 1
        elif source[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                # Found matching closing brace, check if followed by */ (possibly with whitespace)
                j = i + 1
                while j < len(source) and source[j] in " \t\n\r":
                    j += 1
                if j + 1 < len(source) and source[j : j + 2] == "*/":
                    raw = source[start_pos : i + 1]
                    metadata = try_parse_json_block(raw)
                    if "INPUTS" not in metadata:
                        fallback_inputs = parse_inputs_fallback(raw)
                        if fallback_inputs:
                            metadata["INPUTS"] = fallback_inputs
                    return metadata
                break
        i += 1
    return {}


def try_parse_json_block(block: str) -> Dict[str, Any]:
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        sanitized = sanitize_json_like(block)
        try:
            return json.loads(sanitized)
        except json.JSONDecodeError:
            return {}


def parse_inputs_fallback(block: str) -> List[Dict[str, Any]]:
    """Extract INPUTS entries even from malformed JSON by finding object boundaries."""
    entries: List[Dict[str, Any]] = []
    
    # Find the INPUTS array
    inputs_match = re.search(r'"INPUTS"\s*:\s*\[', block, re.IGNORECASE)
    if not inputs_match:
        return entries
    
    start_pos = inputs_match.end()
    
    # Find matching closing bracket by counting brackets and braces
    bracket_count = 1  # We're inside the INPUTS array
    brace_count = 0
    i = start_pos
    entry_start = None
    
    while i < len(block):
        if block[i] == '[':
            bracket_count += 1
        elif block[i] == ']':
            bracket_count -= 1
            if bracket_count == 0:
                break
        elif block[i] == '{':
            if brace_count == 0:
                entry_start = i
            brace_count += 1
        elif block[i] == '}':
            brace_count -= 1
            if brace_count == 0 and entry_start is not None:
                # Found a complete entry object
                entry_str = block[entry_start:i+1]
                if '"NAME"' in entry_str and '"TYPE"' in entry_str:
                    sanitized = sanitize_json_like(entry_str)
                    try:
                        entry = json.loads(sanitized)
                        if "NAME" in entry and "TYPE" in entry:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        pass
                entry_start = None
        i += 1
    
    return entries


def sanitize_json_like(text: str) -> str:
    """Attempt to fix common JSON issues (trailing commas, comments)."""
    # Remove // comments
    text_no_comments = re.sub(r"//.*", "", text)
    # Remove trailing commas before } or ]
    pattern = re.compile(r",(\s*[}\]])")
    prev = None
    current = text_no_comments
    while prev != current:
        prev = current
        current = pattern.sub(r"\1", current)
    return current


def extract_inputs(metadata: Dict[str, Any]) -> List[ShaderInput]:
    inputs = []
    for entry in metadata.get("INPUTS", []):
        name = entry.get("NAME")
        type_ = entry.get("TYPE")
        if not name or not type_:
            continue
        inputs.append(ShaderInput(name=name, type=type_, default=entry.get("DEFAULT")))
    return inputs


def extract_buffer_names(metadata: Dict[str, Any]) -> List[str]:
    """Extract buffer names from PASSES metadata."""
    buffer_names = []
    passes = metadata.get("PASSES", [])
    for pass_config in passes:
        # Check for TARGET (output buffer)
        target = pass_config.get("TARGET")
        if target:
            buffer_names.append(target)
        # Check for INPUTS in pass (input buffers)
        pass_inputs = pass_config.get("INPUTS", [])
        for inp in pass_inputs:
            name = inp.get("NAME")
            if name and name not in buffer_names:
                buffer_names.append(name)
    return buffer_names


def needs_uniform_declaration(name: str, shader_source: str, is_input: bool = False) -> bool:
    # Check if uniform or variable is already declared
    # Look for "uniform <type> <name>" or "<type> <name> = " patterns
    # Ignore comments to avoid false matches
    lines = shader_source.split('\n')
    code_lines = []
    for line in lines:
        # Remove single-line comments
        if '//' in line:
            line = line[:line.index('//')]
        code_lines.append(line)
    code_without_comments = '\n'.join(code_lines)
    
    # Check for uniform declaration
    uniform_pattern = rf"\buniform\s+[a-zA-Z0-9_]+\s+{re.escape(name)}\b"
    if re.search(uniform_pattern, code_without_comments, re.MULTILINE):
        return False
    
    # For input parameters from metadata, always declare as uniform even if variable exists
    # (the variable might be defined later, but we need the uniform first)
    if is_input:
        # Still check if uniform is already declared
        return True
    
    # Check for variable declaration (e.g., "vec3 iResolution = " or "float iTime = ")
    # Only skip uniform declaration if it's NOT an input parameter
    variable_pattern = rf"\b[a-zA-Z0-9_]+\s+{re.escape(name)}\s*="
    if re.search(variable_pattern, code_without_comments, re.MULTILINE):
        return False
    
    return True


def build_fragment_shader(
    source: str,
    inputs: Iterable[ShaderInput],
    extra_uniforms: Dict[str, str],
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    declarations = [DEFAULT_FRAGMENT_PREFIX.strip()]
    processed: set[str] = set()

    def add_uniform(name: str, glsl_type: str, is_input: bool = False) -> None:
        if name in processed:
            return
        processed.add(name)
        if needs_uniform_declaration(name, source, is_input):
            declarations.append(f"uniform {glsl_type} {name};")

    # Check if RENDERSIZE is used as vec2 (direct multiplication/operation with vec2)
    # If RENDERSIZE.xy, RENDERSIZE.xz, RENDERSIZE.yz, or RENDERSIZE.z is used, it's vec3
    # Note: RENDERSIZE.x and RENDERSIZE.y work on both vec2 and vec3, so don't use those to detect
    # If RENDERSIZE is used directly in multiplication, it might be vec2
    # If vec3(RENDERSIZE, ...) is used, RENDERSIZE must be vec2
    has_rendersize_accessor = bool(re.search(r'\bRENDERSIZE\s*\.(xy|xz|yz|z)\b', source))
    
    # Check for constructor usage: vec3(RENDERSIZE, ...) means RENDERSIZE is vec2
    uses_rendersize_in_vec3_constructor = bool(re.search(r'\bvec3\s*\(\s*RENDERSIZE\s*,', source))
    
    # Check for direct vec2 operations with RENDERSIZE (without accessors)
    # Also check for operations like "vec2 - RENDERSIZE" or "gl_FragCoord.xy - RENDERSIZE"
    uses_rendersize_as_vec2 = False
    if not has_rendersize_accessor:
        uses_rendersize_as_vec2 = bool(
            re.search(r'\b(vec2|isf_FragNormCoord|gl_FragCoord\.xy)\s*[*+-/]\s*RENDERSIZE\b', source) or
            re.search(r'\b(isf_FragNormCoord|vv_FragNormCoord|gl_FragCoord)\.xy\s*[*+-/]\s*RENDERSIZE\b', source) or
            re.search(r'\bRENDERSIZE\s*[*+-/]\s*(vec2|isf_FragNormCoord|gl_FragCoord\.xy)\b', source) or
            re.search(r'\bRENDERSIZE\s*[*+-/]\s*(isf_FragNormCoord|vv_FragNormCoord|gl_FragCoord)\.xy\b', source) or
            re.search(r'\bRENDERSIZE\s*[*+-]\s*\w+\s*[*+-]\s*RENDERSIZE\b', source) or
            uses_rendersize_in_vec3_constructor or
            # Check for subtraction/addition with vec2 expressions like "gl_FragCoord.xy - 0.5*RENDERSIZE"
            re.search(r'\.xy\s*[-+/]\s*[^)]*\s*[*]\s*RENDERSIZE\b', source) or
            re.search(r'[0-9.]+\s*[*]\s*RENDERSIZE\s*[)/]', source) or
            # Check for operations where vec2 is subtracted from or added to RENDERSIZE
            re.search(r'\([^)]*\.xy\s*[-+]\s*[^)]*RENDERSIZE', source) or
            # Check for division operations like "gl_FragCoord.xy / RENDERSIZE"
            re.search(r'\.xy\s*/\s*RENDERSIZE\b', source) or
            re.search(r'\bRENDERSIZE\s*/\s*\.xy\b', source)
        )
    
    required_uniforms = {
        "TIME": "float",
        "FRAMEINDEX": "int",
        "RENDERSIZE": "vec2" if uses_rendersize_as_vec2 else "vec3",
        "DATE": "vec4",
        "inputImage": "sampler2D",
        "iMouse": "vec2",
        "iResolution": "vec3",
        "iTime": "float",
        "iTimeDelta": "float",
        "iFrame": "int",
        "PASSINDEX": "int",
    }
    for name, glsl_type in required_uniforms.items():
        add_uniform(name, glsl_type)

    for name, glsl_type in extra_uniforms.items():
        add_uniform(name, glsl_type)

    for shader_input in inputs:
        glsl_type = TYPE_TO_GLSL.get(shader_input.type)
        if not glsl_type:
            continue
        
        # Special handling for color type: check if it needs vec4 (has alpha component)
        if shader_input.type == "color":
            # Check if shader uses .a accessor on this color
            color_uses_alpha = bool(re.search(rf'\b{re.escape(shader_input.name)}\s*\.a\b', source))
            # Or check if default has 4 components
            default_has_alpha = (
                isinstance(shader_input.default, (list, tuple)) and 
                len(shader_input.default) == 4
            )
            if color_uses_alpha or default_has_alpha:
                glsl_type = "vec4"
        
        add_uniform(shader_input.name, glsl_type, is_input=True)
    
    # Add ISF buffer uniforms (from PASSES metadata)
    if metadata:
        buffer_names = extract_buffer_names(metadata)
        for buffer_name in buffer_names:
            add_uniform(buffer_name, "sampler2D")

    # Inject ISF convenience variables if the shader doesn't already define them
    # Check for actual declarations (not in comments)
    def is_isf_variable_declared(name: str, src: str) -> bool:
        # Remove single-line comments first
        lines = src.split('\n')
        code_lines = []
        for line in lines:
            # Remove single-line comments
            if '//' in line:
                line = line[:line.index('//')]
            code_lines.append(line)
        code_without_comments = '\n'.join(code_lines)
        
        # Look for patterns like: vec2 isf_FragNormCoord, uniform vec2 isf_FragNormCoord, 
        # vec2 isf_FragNormCoord = ..., varying vec2 isf_FragNormCoord, etc.
        pattern = rf"\b(vec2|vec3|uniform\s+vec2|uniform\s+vec3|varying\s+vec2|varying\s+vec3)\s+{re.escape(name)}\s*[=;,\[\)]"
        return re.search(pattern, code_without_comments) is not None
    
    isf_lines: List[str] = []
    if not is_isf_variable_declared("isf_FragCoord", source):
        isf_lines.append("vec2 isf_FragCoord = gl_FragCoord.xy;")
    if not is_isf_variable_declared("isf_FragNormCoord", source):
        isf_lines.append("vec2 isf_FragNormCoord = gl_FragCoord.xy / RENDERSIZE.xy;")
    # VIDVOX ISF built-in variables (same as ISF but with vv_ prefix)
    if not is_isf_variable_declared("vv_FragCoord", source):
        isf_lines.append("vec2 vv_FragCoord = gl_FragCoord.xy;")
    if not is_isf_variable_declared("vv_FragNormCoord", source):
        isf_lines.append("vec2 vv_FragNormCoord = gl_FragCoord.xy / RENDERSIZE.xy;")
    if isf_lines:
        declarations.append("// ISF convenience variables")
        declarations.extend(isf_lines)
        declarations.append("")

    # Replace varying variables with calculated values (for ISF compatibility)
    # Calculate pixel size for neighbor coordinate calculations
    declarations.append("// Calculate pixel size for neighbor sampling")
    declarations.append("vec2 pixelSize = 1.0 / RENDERSIZE.xy;")
    declarations.append("")
    
    # Replace varying declarations in source
    modified_source = source
    # Pattern to match: varying vec2 variable_name;
    varying_pattern = re.compile(r'\bvarying\s+vec2\s+(\w+)\s*;', re.MULTILINE)
    
    def replace_varying(match):
        var_name = match.group(1)
        # Check if it's a coordinate variable (common patterns)
        if 'coord' in var_name.lower() or 'uv' in var_name.lower():
            # Calculate based on variable name patterns
            if 'left' in var_name.lower():
                if 'a' in var_name.lower() or 'above' in var_name.lower():
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(-pixelSize.x, pixelSize.y);"
                elif 'b' in var_name.lower() or 'below' in var_name.lower():
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(-pixelSize.x, -pixelSize.y);"
                else:
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(-pixelSize.x, 0.0);"
            elif 'right' in var_name.lower():
                if 'a' in var_name.lower() or 'above' in var_name.lower():
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(pixelSize.x, pixelSize.y);"
                elif 'b' in var_name.lower() or 'below' in var_name.lower():
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(pixelSize.x, -pixelSize.y);"
                else:
                    return f"vec2 {var_name} = isf_FragNormCoord + vec2(pixelSize.x, 0.0);"
            elif 'above' in var_name.lower() or 'up' in var_name.lower():
                return f"vec2 {var_name} = isf_FragNormCoord + vec2(0.0, pixelSize.y);"
            elif 'below' in var_name.lower() or 'down' in var_name.lower():
                return f"vec2 {var_name} = isf_FragNormCoord + vec2(0.0, -pixelSize.y);"
            else:
                # Default: just use current coord
                return f"vec2 {var_name} = isf_FragNormCoord;"
        else:
            # Unknown varying, just remove the varying keyword
            return f"vec2 {var_name} = vec2(0.0);"
    
    modified_source = varying_pattern.sub(replace_varying, modified_source)

    return "\n".join(declarations) + "\n" + modified_source


def load_texture(ctx: moderngl.Context, image_path: Optional[Path], size: Tuple[int, int]) -> moderngl.Texture:
    if image_path and image_path.exists():
        image = Image.open(image_path).convert("RGBA")
    else:
        image = Image.new("RGBA", size, (255, 255, 255, 255))

    texture = ctx.texture(image.size, 4, image.tobytes())
    texture.build_mipmaps()
    return texture


def set_uniform(program: moderngl.Program, name: str, value: Any) -> None:
    if name not in program:
        return
    uniform = program[name]
    if isinstance(value, (tuple, list)):
        uniform.value = tuple(value)
    else:
        uniform.value = value


def convert_default_value(shader_input: ShaderInput) -> Any:
    default = shader_input.default
    type_ = shader_input.type
    
    # Handle bool and event types - must be integer (0 or 1) in GLSL
    if type_ in {"bool", "event"}:
        if default is None:
            return 0
        # Convert bool/float/int to 0 or 1
        if isinstance(default, bool):
            return 1 if default else 0
        if isinstance(default, (int, float)):
            return 1 if default != 0 else 0
        return 0
    
    if default is None:
        return {
            "float": 0.0,
            "int": 0,
            "long": 0,  # long maps to int
            "point2D": (0.0, 0.0),
            "point3D": (0.0, 0.0, 0.0),
            "color": (1.0, 1.0, 1.0),
            "event": 0,  # event maps to bool, so use 0 (false)
        }.get(type_, 0.0)
    if type_ in {"point2D", "point3D"} and isinstance(default, (list, tuple)):
        return tuple(default[:3])
    if type_ == "color" and isinstance(default, (list, tuple)):
        # Color can be vec3 (RGB) or vec4 (RGBA)
        # Return all components, let the uniform type determine the size
        return tuple(default[:4])
    if isinstance(default, (int, float)):
        return default
    return default


class ShaderBatchRenderer:
    def __init__(
        self,
        resolution: Tuple[int, int],
        fps: int,
        extra_uniforms: Dict[str, Tuple[str, Any]],
    ) -> None:
        self.resolution = resolution
        self.fps = fps
        self.extra_uniform_types = {name: spec[0] for name, spec in extra_uniforms.items()}
        self.extra_uniform_values = {name: spec[1] for name, spec in extra_uniforms.items()}
        self.ctx = moderngl.create_standalone_context()
        quad = np.array(
            [
                -1.0,
                -1.0,
                1.0,
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )
        self.vbo = self.ctx.buffer(quad.tobytes())

    def render_shader(
        self,
        shader_path: Path,
        duration: float,
        output_dir: Path,
        image_input: Optional[Path],
    ) -> Path:
        source = shader_path.read_text(encoding="utf-8")
        metadata = parse_metadata(source)
        inputs = extract_inputs(metadata)
        fragment_source = build_fragment_shader(source, inputs, self.extra_uniform_types, metadata)

        prog = self.ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=fragment_source)
        vao = self.ctx.simple_vertex_array(prog, self.vbo, "in_position")
        fbo = self.ctx.simple_framebuffer(self.resolution, components=4)

        texture = load_texture(self.ctx, image_input, self.resolution)
        texture.use(location=0)

        # Create buffer textures once (for ISF multi-pass shaders)
        buffer_textures = {}
        if metadata:
            buffer_names = extract_buffer_names(metadata)
            for i, buffer_name in enumerate(buffer_names):
                # Create a black texture for each buffer
                buffer_textures[buffer_name] = load_texture(self.ctx, None, self.resolution)

        total_frames = max(1, math.ceil(duration * self.fps))
        frames: List[Image.Image] = []
        for frame_idx in range(total_frames):
            time_value = frame_idx / self.fps
            if "TIME" in prog:
                prog["TIME"].value = time_value
            if "FRAMEINDEX" in prog:
                prog["FRAMEINDEX"].value = frame_idx
            if "RENDERSIZE" in prog:
                # Try to determine if it's vec2 or vec3, with fallback
                rendersize_uniform = prog["RENDERSIZE"]
                is_vec2 = False
                # Check format string if available
                if hasattr(rendersize_uniform, 'fmt'):
                    fmt_str = str(rendersize_uniform.fmt)
                    is_vec2 = '2f' in fmt_str and '3f' not in fmt_str
                
                # Try vec2 first if detected, otherwise default to vec3
                if is_vec2:
                    try:
                        prog["RENDERSIZE"].value = self.resolution
                    except Exception:
                        # Fallback to vec3 if vec2 fails
                        aspect = self.resolution[0] / self.resolution[1] if self.resolution[1] > 0 else 1.0
                        prog["RENDERSIZE"].value = (*self.resolution, aspect)
                else:
                    # vec3: (width, height, aspect) - default
                    aspect = self.resolution[0] / self.resolution[1] if self.resolution[1] > 0 else 1.0
                    prog["RENDERSIZE"].value = (*self.resolution, aspect)
            if "DATE" in prog:
                prog["DATE"].value = (2025.0, 11.0, 19.0, time_value)
            if "inputImage" in prog:
                prog["inputImage"].value = 0
            if "iMouse" in prog:
                # Default to center of screen
                prog["iMouse"].value = (self.resolution[0] * 0.5, self.resolution[1] * 0.5)
            if "iResolution" in prog:
                prog["iResolution"].value = (*self.resolution, 1.0)
            if "iTime" in prog:
                prog["iTime"].value = time_value
            if "iTimeDelta" in prog:
                prog["iTimeDelta"].value = 1.0 / self.fps
            if "iFrame" in prog:
                prog["iFrame"].value = frame_idx
            if "PASSINDEX" in prog:
                # Set to 1 (final pass) for multi-pass shaders
                # Pass 0 renders to buffers, pass 1 renders final output
                prog["PASSINDEX"].value = 1

            # Set buffer textures (from PASSES metadata)
            for i, (buffer_name, buffer_texture) in enumerate(buffer_textures.items()):
                if buffer_name in prog:
                    buffer_texture.use(location=i + 1)  # Start after inputImage (location 0)
                    prog[buffer_name].value = i + 1

            for shader_input in inputs:
                if shader_input.type == "image":
                    if shader_input.name in prog:
                        prog[shader_input.name].value = 0
                    continue
                set_uniform(prog, shader_input.name, convert_default_value(shader_input))

            for name, value in self.extra_uniform_values.items():
                set_uniform(prog, name, value)

            fbo.use()
            self.ctx.clear(0.0, 0.0, 0.0, 1.0)
            vao.render(moderngl.TRIANGLE_STRIP)

            data = fbo.read(components=3, alignment=1)
            img = Image.frombytes("RGB", self.resolution, data).transpose(Image.FLIP_TOP_BOTTOM)
            frames.append(img)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / (shader_path.stem + ".gif")
        durations = int(1000 / self.fps)
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,
            disposal=2,
        )
        return output_path


def gather_shader_files(paths: List[Path]) -> List[Path]:
    all_files: List[Path] = []
    for path in paths:
        if path.is_dir():
            all_files.extend(sorted(path.glob("*.fs")))
        elif path.suffix == ".fs":
            all_files.append(path)
    return all_files


def parse_extra_uniforms(entries: List[str]) -> Dict[str, Tuple[str, Any]]:
    uniforms: Dict[str, Tuple[str, Any]] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Uniform '{entry}' must follow name[:type]=value syntax.")
        name_type, value_str = entry.split("=", 1)
        if ":" in name_type:
            name, type_key = name_type.split(":", 1)
        else:
            name, type_key = name_type, "float"
        type_key = type_key.lower()
        if type_key not in EXTRA_TYPE_MAP:
            raise ValueError(f"Unsupported type '{type_key}' for uniform '{name}'.")
        glsl_type, converter = EXTRA_TYPE_MAP[type_key]
        try:
            value = converter(value_str)
        except ValueError as exc:
            if type_key in ("vec2", "vec3"):
                raise ValueError(
                    f"Failed to parse {type_key} value for uniform '{name}': {exc}. "
                    f"Expected comma-separated numbers like '0.5,1.2' (got '{value_str}')"
                ) from exc
            raise ValueError(
                f"Failed to parse value for uniform '{name}': {exc}. "
                f"Expected a {type_key} value (got '{value_str}')"
            ) from exc
        uniforms[name] = (glsl_type, value)
    return uniforms


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch render .fs shaders to GIF previews.")
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Shader files or directories containing .fs files.",
    )
    parser.add_argument("--duration", type=float, default=4.0, help="Duration in seconds per shader.")
    parser.add_argument("--fps", type=int, default=24, help="Animation frames per second.")
    parser.add_argument("--width", type=int, default=512, help="Render width.")
    parser.add_argument("--height", type=int, default=512, help="Render height.")
    parser.add_argument("--output", type=Path, default=Path("gif_output"), help="Directory to store GIFs.")
    parser.add_argument("--input-image", type=Path, default=None, help="Optional image bound to inputImage uniforms.")
    parser.add_argument(
        "--uniform",
        dest="uniforms",
        action="append",
        default=[],
        help="Extra uniform as name[:type]=value (e.g. iZoom=1.0 or tilt:vec2=0.5,1.2). Repeatable.",
    )

    args = parser.parse_args()
    shader_files = gather_shader_files(args.paths)
    if not shader_files:
        raise SystemExit("No .fs shaders found.")

    extra_uniforms = parse_extra_uniforms(args.uniforms)
    renderer = ShaderBatchRenderer(
        resolution=(args.width, args.height),
        fps=args.fps,
        extra_uniforms=extra_uniforms,
    )
    for shader_path in shader_files:
        print(f"Rendering {shader_path} ...")
        output_path = renderer.render_shader(
            shader_path=shader_path,
            duration=args.duration,
            output_dir=args.output,
            image_input=args.input_image,
        )
        print(f"Saved GIF to {output_path}")


if __name__ == "__main__":
    main()

