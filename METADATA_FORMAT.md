# ISF Shader Metadata Format Guide

This document describes the correct format for metadata comments in `.fs` shader files that the batch renderer can parse.

## Basic Structure

The metadata must be wrapped in a C-style comment block:

```glsl
/*{
  "DESCRIPTION": "Your shader description",
  "CATEGORIES": ["category1", "category2"],
  "INPUTS": [
    // Input definitions here
  ],
  "ISFVSN": "2"
}*/
```

## Required Fields

### `DESCRIPTION` (optional)
A string describing what the shader does.

### `CATEGORIES` (optional)
An array of category strings for organizing shaders.

### `INPUTS` (required for shaders with parameters)
An array of input parameter definitions. Each input is an object with the following structure.

### `ISFVSN` (optional)
The ISF version number, typically `"2"`.

## Input Parameter Format

Each input in the `INPUTS` array must be a JSON object with at minimum:

```json
{
  "NAME": "parameterName",
  "TYPE": "float"
}
```

### Supported Types

- **`"float"`** - Floating point number
- **`"int"`** - Integer number
- **`"long"`** - Long integer (maps to `int` in GLSL)
- **`"bool"`** - Boolean value
- **`"point2D"`** - 2D point (maps to `vec2` in GLSL)
- **`"point3D"`** - 3D point (maps to `vec3` in GLSL)
- **`"color"`** - Color value (maps to `vec3` in GLSL, RGB components)
- **`"image"`** - Image/sampler input (maps to `sampler2D` in GLSL). Can use names like `inputImage`, `iChannel0`, `iChannel1`, etc.
- **`"event"`** - Event trigger (maps to `float` in GLSL)

### Optional Fields

- **`"DEFAULT"`** - Default value for the parameter
  - For `float`: `0.5`
  - For `int`: `10`
  - For `bool`: `true` or `false`
  - For `point2D`: `[0.0, 0.0]`
  - For `point3D`: `[0.0, 0.0, 0.0]`
  - For `color`: `[1.0, 0.0, 0.0, 1.0]` (RGBA) or `[1.0, 0.0, 0.0]` (RGB)
  - For `event`: `0.0`

- **`"MIN"`** - Minimum value (for numeric types)
- **`"MAX"` - Maximum value (for numeric types)
- **`"LABEL"`** - Human-readable label (optional, for UI)

## Complete Examples

### Example 1: Simple Float Parameter

```glsl
/*{
  "DESCRIPTION": "My shader",
  "INPUTS": [
    {
      "NAME": "intensity",
      "TYPE": "float",
      "DEFAULT": 1.0,
      "MIN": 0.0,
      "MAX": 5.0,
      "LABEL": "Effect Intensity"
    }
  ]
}*/
```

### Example 2: Multiple Parameters

```glsl
/*{
  "DESCRIPTION": "Colorful shader",
  "CATEGORIES": ["generator", "colorful"],
  "INPUTS": [
    {
      "NAME": "inputImage",
      "TYPE": "image"
    },
    {
      "NAME": "zoom",
      "TYPE": "float",
      "DEFAULT": 1.0,
      "MIN": 0.1,
      "MAX": 5.0
    },
    {
      "NAME": "mousePos",
      "TYPE": "point2D",
      "DEFAULT": [0.5, 0.5],
      "MIN": [0.0, 0.0],
      "MAX": [1.0, 1.0]
    },
    {
      "NAME": "baseColor",
      "TYPE": "color",
      "DEFAULT": [1.0, 0.5, 0.0, 1.0]
    }
  ],
  "ISFVSN": "2"
}*/
```

### Example 3: Minimal Format (Works but not recommended)

```glsl
/*{
  "INPUTS": [
    {"NAME": "speed", "TYPE": "float", "DEFAULT": 1.0}
  ]
}*/
```

## Common Issues and Fixes

### Issue 1: Trailing Commas
**Problem:** JSON doesn't allow trailing commas before `}` or `]`
```json
{
  "NAME": "param",
  "TYPE": "float"  // ❌ Trailing comma
}
```

**Fix:** Remove the trailing comma
```json
{
  "NAME": "param",
  "TYPE": "float"  // ✅ No trailing comma
}
```

**Note:** The renderer attempts to auto-fix trailing commas, but it's better to write correct JSON.

### Issue 2: Comments in JSON
**Problem:** JSON doesn't support `//` comments
```json
{
  "NAME": "param",
  // ❌ This comment breaks JSON
  "TYPE": "float"
}
```

**Fix:** Remove comments or put them outside the JSON block
```glsl
/*{
  "NAME": "param",
  "TYPE": "float"
}*/
// ✅ Comments outside JSON are fine
```

**Note:** The renderer attempts to strip `//` comments, but it's better to avoid them in JSON.

### Issue 3: Missing Quotes
**Problem:** JSON requires quotes around keys and string values
```json
{
  NAME: "param",  // ❌ Missing quotes
  TYPE: float      // ❌ Missing quotes and wrong type
}
```

**Fix:** Always use quotes
```json
{
  "NAME": "param",  // ✅ Properly quoted
  "TYPE": "float"   // ✅ Properly quoted
}
```

### Issue 4: Inconsistent Formatting
**Problem:** Mixing styles can cause parsing issues
```json
{
  "NAME":"param",  // No spaces
  "TYPE" : "float"  // Spaces around colon
}
```

**Fix:** Be consistent (spaces are optional but recommended for readability)
```json
{
  "NAME": "param",   // ✅ Consistent style
  "TYPE": "float"    // ✅ Consistent style
}
```

## Best Practices

1. **Always include `DESCRIPTION`** - Helps identify shaders
2. **Use `CATEGORIES`** - Makes organization easier
3. **Provide `DEFAULT` values** - Ensures shaders work out of the box
4. **Set `MIN`/`MAX` for numeric types** - Prevents invalid values
5. **Use `LABEL` for user-facing parameters** - Better UX
6. **Validate JSON syntax** - Use a JSON validator before committing
7. **Keep formatting consistent** - Makes files easier to read and maintain

## Automatic Uniforms

The renderer automatically declares these uniforms (you don't need to declare them in metadata):

- `TIME` (float) - Current time in seconds
- `FRAMEINDEX` (int) - Current frame number
- `RENDERSIZE` (vec3) - Render resolution (width, height, aspect)
- `DATE` (vec4) - Date/time information
- `inputImage` (sampler2D) - Default input image
- `iMouse` (vec2) - Mouse position (defaults to center)
- `iResolution` (vec3) - Screen resolution
- `iTime` (float) - Same as TIME
- `iTimeDelta` (float) - Frame delta time
- `iFrame` (int) - Same as FRAMEINDEX

## ISF Built-in Variables

These are automatically calculated (you don't need to declare them):

- `isf_FragNormCoord` (vec2) - Normalized fragment coordinates (0.0 to 1.0)
- `isf_FragCoord` (vec2) - Fragment coordinates in pixels

These are available in your shader code automatically.

