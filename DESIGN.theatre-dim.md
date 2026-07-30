---
version: alpha
name: SurgiAnnotate Theatre Dim
description: Low-luminance operating-room-adjacent theme with calm teal structure and clear safety cues.
colors:
  canvas: "#101615"
  surface: "#18211F"
  surface-alt: "#202C29"
  surface-hover: "#2B3A36"
  surface-pressed: "#121B18"
  surface-input: "#111A17"
  video: "#030807"
  border: "#728B81"
  text: "#F2F7F3"
  muted: "#B6C6BE"
  disabled: "#8A9F96"
  focus: "#8CE2DD"
  primary: "#147E7A"
  on-primary: "#FFFFFF"
  primary-hover: "#0E625F"
  primary-container: "#134541"
  on-primary-container: "#C8F5F1"
  success: "#257A42"
  on-success: "#FFFFFF"
  success-container: "#1C4326"
  on-success-container: "#C6F0C8"
  success-text: "#C6F0C8"
  warning: "#AA6500"
  on-warning: "#FFFFFF"
  warning-container: "#513200"
  on-warning-container: "#FFE0AC"
  warning-text: "#FFE0AC"
  danger: "#B8303F"
  on-danger: "#FFFFFF"
  danger-container: "#551922"
  on-danger-container: "#FFDADF"
  danger-text: "#FFDADF"
  violet: "#6C53C8"
  on-violet: "#FFFFFF"
  violet-container: "#332160"
  on-violet-container: "#E1D8FF"
  annotation-phase: "#80DBD7"
  on-annotation-phase: "#073330"
  annotation-task: "#A2DFA0"
  on-annotation-task: "#163C19"
  annotation-keyframe: "#FFD18A"
  on-annotation-keyframe: "#4B2D00"
  annotation-rating: "#C7B7FF"
  on-annotation-rating: "#291A53"
  selection: "#147E7A"
  on-selection: "#FFFFFF"
  scrollbar: "#788D85"
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

Theatre Dim is intentionally low-luminance for environments where bright white
surfaces are distracting. It is a restrained teal-and-charcoal interface, not
a decorative green skin. It supports prolonged attention to a dark video
stage while preserving clear confirmation and warning cues.

## Colors

Teal drives primary actions and focus. Green, amber, violet and red retain
their semantic annotation roles. Amber and red remain distinct in luminance and
are always accompanied by text or an icon.

## Typography

Use the same type scale as the other approved themes. Keep technical timecodes
in the timecode role and do not reduce normal text below the body scale.

## Layout

The layout and spacing remain identical to Clinical Light. Theme choice changes
appearance only, never workflow or keyboard behavior.

## Elevation & Depth

Use quiet tonal separation and one-pixel outlines. Avoid pure black panels,
bright gradients and glow.

## Shapes

Use the shared sm, md, lg and full rounding roles only.

## Components

Use the shared component roles. The active primary action is teal; destructive
confirmation defaults to cancellation and uses the danger role only at the
point of commitment.

## Do's and Don'ts

- Do use this theme when ambient light is low.
- Do maintain the same focus visibility as the bright theme.
- Do keep safety colors distinct and text-labelled.
- Do not use this theme to hide disabled or destructive states.
