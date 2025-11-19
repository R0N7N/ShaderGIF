# Shader GIF Batch Renderer

Render ISF/GLSL fragment shaders (`.fs`) into looping GIF previews directly from the command line.

## Setup

```powershell
cd "C:\Users\schibli\Documents\Cursor Playground\ShaderGIF"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```powershell
python shader_gif_renderer.py ^
  "C:\Users\schibli\Documents\HeavyM\ShadersLibrary" ^
  --duration 6 ^
  --fps 30 ^
  --width 768 ^
  --height 768 ^
  --output gif_previews ^
  --input-image sample.png ^
  --uniform iZoom=1.0 ^
  --uniform parallax:vec2=0.5,1.2
```

Arguments:

- `paths`: One or more `.fs` files or directories to batch render.
- `--duration`: Seconds for each animation loop (default 4).
- `--fps`: Frames per second (default 24).
- `--width/--height`: Render resolution (default 512×512).
- `--output`: Folder for generated GIFs (`gif_output` by default).
- `--input-image`: Optional image bound to `inputImage` uniforms.
- `--uniform`: Inject extra uniforms not defined in the shader metadata (`name[:type]=value`). Supported types: `float`, `int`, `bool`, `vec2`, `vec3`.
  - Examples: `--uniform iZoom=1.0` or `--uniform iMouse:vec2=360,240` (use actual numbers, not x,y)

**Note:** Common Shadertoy-style uniforms (`iMouse`, `iResolution`, `iTime`, `iTimeDelta`, `iFrame`) are automatically declared and set with sensible defaults. `iMouse` defaults to the center of the screen.

The renderer parses ISF metadata blocks to auto-declare uniforms and uses default values defined in each shader. Every exported GIF shares the original shader filename with a `.gif` extension.


Example command
```
python shader_gif_renderer.py shaderdir --duration 3 --fps 30 --width 120 --height 68 --output output --uniform iZoom=1.0 --uniform iMouse:vec2=360,240 
```
