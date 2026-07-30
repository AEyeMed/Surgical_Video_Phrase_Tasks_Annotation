---
version: alpha
name: SurgiAnnotate Clinical Dark
description: Low-glare clinical dark theme for focused annotation without sacrificing semantic contrast.
colors:
  canvas: "#0B1220"
  surface: "#142033"
  surface-alt: "#1B2A40"
  surface-hover: "#253852"
  surface-pressed: "#101C2E"
  surface-input: "#0F1A2B"
  video: "#03070D"
  border: "#637D99"
  text: "#F3F7FC"
  muted: "#B1C2D5"
  disabled: "#8B9FB3"
  focus: "#8AC5FF"
  primary: "#2563EB"
  on-primary: "#FFFFFF"
  primary-hover: "#1D4ED8"
  primary-container: "#173B75"
  on-primary-container: "#DCEBFF"
  success: "#087C4A"
  on-success: "#FFFFFF"
  success-container: "#103F2C"
  on-success-container: "#B9F3D3"
  success-text: "#B9F3D3"
  warning: "#9A5700"
  on-warning: "#FFFFFF"
  warning-container: "#4D2D00"
  on-warning-container: "#FFE0AE"
  warning-text: "#FFE0AE"
  danger: "#C21F46"
  on-danger: "#FFFFFF"
  danger-container: "#571228"
  on-danger-container: "#FFD9E1"
  danger-text: "#FFD9E1"
  violet: "#7253C9"
  on-violet: "#FFFFFF"
  violet-container: "#33205F"
  on-violet-container: "#E2D8FF"
  annotation-phase: "#93C5FD"
  on-annotation-phase: "#0C3156"
  annotation-task: "#8FE3B5"
  on-annotation-task: "#073B25"
  annotation-keyframe: "#FFD08A"
  on-annotation-keyframe: "#4A2D00"
  annotation-rating: "#CDB7FF"
  on-annotation-rating: "#2A1555"
  selection: "#2563EB"
  on-selection: "#FFFFFF"
  scrollbar: "#7189A3"
typography:
  brand:
    fontFamily: "Segoe UI, Microsoft YaHei UI, Arial"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 24px
  title-md:
    fontFamily: "Segoe UI, Microsoft YaHei UI, Arial"
    fontSize: 15px
    fontWeight: 700
    lineHeight: 22px
  body-md:
    fontFamily: "Segoe UI, Microsoft YaHei UI, Arial"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 20px
  body-sm:
    fontFamily: "Segoe UI, Microsoft YaHei UI, Arial"
    fontSize: 12px
    fontWeight: 400
    lineHeight: 18px
  label-sm:
    fontFamily: "Segoe UI, Microsoft YaHei UI, Arial"
    fontSize: 11px
    fontWeight: 700
    lineHeight: 16px
    letterSpacing: 0.04em
  timecode:
    fontFamily: "Cascadia Mono, Consolas, Microsoft YaHei UI"
    fontSize: 15px
    fontWeight: 600
    lineHeight: 20px
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xxs: 2px
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  app-shell:
    backgroundColor: "{colors.canvas}"
  interactive-hover:
    backgroundColor: "{colors.surface-hover}"
  interactive-pressed:
    backgroundColor: "{colors.surface-pressed}"
  video-stage:
    backgroundColor: "{colors.video}"
  outline:
    backgroundColor: "{colors.border}"
  text-muted:
    textColor: "{colors.muted}"
  control-disabled:
    textColor: "{colors.disabled}"
  focus-ring:
    backgroundColor: "{colors.focus}"
  button-success:
    backgroundColor: "{colors.success}"
    textColor: "{colors.on-success}"
  notice-success:
    backgroundColor: "{colors.success-container}"
    textColor: "{colors.on-success-container}"
  text-success:
    textColor: "{colors.success-text}"
  button-warning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.on-warning}"
  notice-warning:
    backgroundColor: "{colors.warning-container}"
    textColor: "{colors.on-warning-container}"
  text-warning:
    textColor: "{colors.warning-text}"
  button-violet:
    backgroundColor: "{colors.violet}"
    textColor: "{colors.on-violet}"
  notice-violet:
    backgroundColor: "{colors.violet-container}"
    textColor: "{colors.on-violet-container}"
  annotation-phase:
    backgroundColor: "{colors.annotation-phase}"
    textColor: "{colors.on-annotation-phase}"
  annotation-task:
    backgroundColor: "{colors.annotation-task}"
    textColor: "{colors.on-annotation-task}"
  annotation-keyframe:
    backgroundColor: "{colors.annotation-keyframe}"
    textColor: "{colors.on-annotation-keyframe}"
  annotation-rating:
    backgroundColor: "{colors.annotation-rating}"
    textColor: "{colors.on-annotation-rating}"
  selected-row:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.on-selection}"
  scrollbar:
    backgroundColor: "{colors.scrollbar}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  button-destructive:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.on-danger}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm}"
  text-danger:
    textColor: "{colors.danger-text}"
  input-field:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm}"
  card-standard:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  status-pill:
    backgroundColor: "{colors.primary-container}"
    textColor: "{colors.on-primary-container}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: "{spacing.xs}"
  timeline:
    backgroundColor: "{colors.surface-alt}"
    rounded: "{rounded.md}"
    padding: "{spacing.sm}"
---

## Overview

Clinical Dark is for focused work in a dim office. It is not a simple color
inversion of Clinical Light: the semantic fills retain readable on-fill text,
while annotation roles become light foreground signals against dark surfaces.

## Colors

Blue remains the primary action. Green, amber, violet and red remain stable
annotation and safety semantics. The video stage remains darker than every
surrounding surface to preserve frame contrast.

## Typography

Use the same type scale as Clinical Light. Bright text is reserved for primary
content; muted text remains legible and must not be used for critical actions.

## Layout

Use the same spacing and structure as Clinical Light. Theme changes must not
move controls or change interaction density.

## Elevation & Depth

Depth is expressed with progressively lighter tonal surfaces and outlines.
Avoid black cards on black canvas and avoid glow effects that compete with
video content.

## Shapes

Use the same sm, md and lg roles as Clinical Light.

## Components

Buttons, tables and inputs use the same component roles as Clinical Light.
Every interactive control receives a high-contrast focus outline.

## Do's and Don'ts

- Do use this theme for low-glare focused work.
- Do retain semantic token roles instead of hard-coded bright colors.
- Do keep the video stage near black.
- Do not lower text contrast merely to make the interface feel dim.
