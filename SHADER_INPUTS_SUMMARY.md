# Shader Inputs Analysis Summary

This document summarizes all input parameters found across all 84 shader files.

## Type Distribution

- **float**: 136 unique parameters (most common)
- **image**: 1 parameter name (`inputImage`, but also `iChannel0`, `iChannel1`, etc.)
- **point2D**: 3 parameters
- **color**: 2 parameters
- **long**: 2 parameters
- **bool**: 2 parameters

## Most Common Parameter Names

### Used in 8+ files:
- `Speed` - 8 files
- `ColorPulse` - 8 files
- `Brightness` - 6 files
- `Zoom` / `zoom` - 10 files total (5 each variant)
- `inputImage` - 24 files

### Used in 3-7 files:
- `Saturation` / `saturation` - 6 files total
- `Contrast` / `contrast` - 7 files total
- `PaletteSelect` / `palette` - 5 files total
- `Morph` / `morph` - 6 files total
- `GlowIntensity` / `glowIntensity` - 3 files total
- `MorphAmount` - 3 files
- `RotationRate` - 2 files
- `GeometryScale` - 2 files

## Special Image Input Names

Some shaders use Shadertoy-style channel names:
- `iChannel0` - Used in 7 files
- `iChannel1` - Referenced in comments (not declared in metadata)

These are automatically handled as `sampler2D` uniforms when declared in the INPUTS metadata.

## Parameter Naming Patterns

1. **CamelCase**: Most HEAVYM shaders use CamelCase (e.g., `ColorPulse`, `GlowIntensity`)
2. **camelCase**: Some shaders use lowercase first letter (e.g., `colorPulse`, `glowIntensity`)
3. **snake_case**: A few use underscores (e.g., `color_speed`, `pulse_rate`)
4. **iPrefix**: Shadertoy-style names (e.g., `iZoom`, `iMouse`, `iColor`, `iChannel0`, `iSteps`)

## Complete Parameter List by Category

### Animation/Speed Controls
- `Speed`, `speed`
- `RotationRate`, `rotationAmount`, `rotation_speed`, `RotateSpeed`
- `TimeMod`, `TimeOffset`, `time`
- `masterSpeed`, `cameraPathSpeed`

### Color/Palette Controls
- `ColorPulse`, `colorPulse`, `ColorPulseSpeed`
- `PaletteSelect`, `palette`, `PaletteIndex`, `PalettePhase`, `PaletteCycleSpeed`, `paletteShift`, `paletteType`
- `ColorShift`, `ColorBoost`, `ColorMix`
- `Saturation`, `saturation`
- `Brightness`, `brightness`
- `Contrast`, `contrast`
- `baseHueShift`, `hueSpeed`, `WallHueShift`

### Morphing/Distortion
- `Morph`, `morph`, `MorphAmount`, `MorphSpeed`, `MorphStrength`, `sceneMorphIntensity`
- `Distortion`, `distortionAmount`, `distortionAmplitude`, `distortionFrequency`, `distortionScale`
- `Twist`, `twistAmount`, `twist_speed`, `TorusTwist`
- `VortexAmount`, `vortexAmount`
- `RadialWarp`, `radialWarp`
- `deform`, `warp_intensity`

### Glow/Effects
- `GlowIntensity`, `glowIntensity`, `GlowAmount`, `GlowAmplitude`, `GlowBias`, `GlowFalloff`, `GlowPulseSpeed`, `glowStrength`
- `GlitchAmount`
- `Shake`, `ShakeAmount`, `shake`
- `Shimmer`
- `FeedbackIntensity`

### Geometry/Scale
- `Zoom`, `zoom`, `iZoom`, `globalZoom`
- `GeometryScale`
- `FractalScale`, `FractalDepth`, `FractalIntensity`, `FractalPower`, `FractalSpin`, `FractalFoldBias`
- `SphereFoldScale`
- `GridTiling`, `LayerCount`, `Layers`

### Audio Reactive
- `audioLevel`, `AudioReactivity`, `audioDistortionReact`

### Post-Processing
- `trailStrength`
- `rgbSplitAmount`
- `colorTripIntensity`, `colorTripSpeed`
- `trippiness`
- `crtEffect`, `randomColorEffect`
- `blendMode`

### Camera Controls
- `camX`, `camY`, `camZ`
- `CamOffset`, `CamOrbitAz`, `CamOrbitEl`, `CamRoll`
- `FOV`
- `FollowBall`, `OrbFollowSpeed`

### Other Specialized
- `iSteps`, `iTimeMultiplier`
- `iMouse`, `iColor`
- `center`, `XYControl`, `controlXY`
- `kaleidoscope`, `Kaleidoscope`
- `pulse`, `Pulse`, `pulseIntensity`, `pulseSpeed`, `pulseDepth`, `pulse_rate`, `PulseRate`, `PulsePattern`, `PulseStrength`
- `intensity`, `Intensity`, `PatternIntensity`
- `threshold`, `opaque`, `sobel`
- `tileShape`, `palette` (as long type)
- `runtime`, `rate`, `offset`, `trace`, `depth`

## Notes for Renderer

All these parameters are automatically:
1. **Parsed** from shader metadata (even with malformed JSON)
2. **Declared** as uniforms in the shader
3. **Set** with default values from metadata
4. **Mapped** to correct GLSL types:
   - `float` → `float`
   - `int` → `int`
   - `long` → `int`
   - `bool` → `bool`
   - `point2D` → `vec2`
   - `point3D` → `vec3`
   - `color` → `vec3`
   - `image` → `sampler2D`
   - `event` → `float`

The renderer handles all 146 unique parameter names across all shader files automatically.

