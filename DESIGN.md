---
version: alpha
name: SurgiAnnotate Clinical Light
description: Bright, calm and high-clarity default theme for a professional surgical video annotation workstation.
colors:
  canvas: "#F4F8FC"
  surface: "#FFFFFF"
  surface-alt: "#EEF4FA"
  surface-hover: "#E4EFFA"
  surface-pressed: "#D7E8F7"
  surface-input: "#FFFFFF"
  video: "#061525"
  border: "#758BA3"
  text: "#152235"
  muted: "#52657A"
  disabled: "#6D8095"
  focus: "#0B6E99"
  primary: "#146AA8"
  on-primary: "#FFFFFF"
  primary-hover: "#0F568B"
  primary-container: "#DCEEFF"
  on-primary-container: "#073B61"
  success: "#167A4A"
  on-success: "#FFFFFF"
  success-container: "#DDF5E8"
  on-success-container: "#0C4B2D"
  success-text: "#0C4B2D"
  warning: "#9A5A00"
  on-warning: "#FFFFFF"
  warning-container: "#FFF0D8"
  on-warning-container: "#613900"
  warning-text: "#613900"
  danger: "#B42342"
  on-danger: "#FFFFFF"
  danger-container: "#FDE5E9"
  on-danger-container: "#72162A"
  danger-text: "#72162A"
  violet: "#6941C6"
  on-violet: "#FFFFFF"
  violet-container: "#EEE8FF"
  on-violet-container: "#3F2482"
  annotation-phase: "#146AA8"
  on-annotation-phase: "#FFFFFF"
  annotation-task: "#167A4A"
  on-annotation-task: "#FFFFFF"
  annotation-keyframe: "#9A5A00"
  on-annotation-keyframe: "#FFFFFF"
  annotation-rating: "#6941C6"
  on-annotation-rating: "#FFFFFF"
  selection: "#146AA8"
  on-selection: "#FFFFFF"
  scrollbar: "#7890A8"
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

SurgiAnnotate is a clinical production tool, not a consumer media player. The
default experience is bright, calm and deliberately sparse so that long
annotation sessions remain legible under normal office light. Video retains a
near-black stage; the surrounding interface uses cool white and blue-gray
tonal layers to separate navigation from medical imagery without visual noise.

Three approved themes exist: this Clinical Light default, Clinical Dark for
general low-light use, and Theatre Dim for an operating-room-adjacent
environment. Their token documents use the same semantic roles. Components
must use semantic token roles, never copied hexadecimal values.

## Colors

Primary blue is reserved for the current primary action, focus and phase
context. Task, keyframe, rating and destructive states use separate semantic
roles. Semantic colors reinforce labels and icons; status must never depend on
color alone. All normal-size text on a fill meets WCAG AA contrast.

## Typography

Use the body scale for controls and annotation content. Brand and title weights
are reserved for hierarchy. Timecodes use the timecode token only; do not use
an arbitrary monospace substitute in individual components.

## Layout

Use the 4px base scale. The video is the primary canvas. Related controls live
in tonal cards with md spacing; avoid dense clusters of independent buttons.

## Elevation & Depth

Use tonal layers and a one-pixel outline instead of heavy shadows. Dialogs and
menus may use the surface color with a stronger outline. Qt widgets should not
attempt unsupported browser effects such as blur or box shadows.

## Shapes

Use sm rounding for compact inputs, md for cards and standard buttons, and full
only for status pills. Do not mix sharp and heavily rounded shapes in one view.

## Components

There is one primary action per local context. Destructive actions use the
danger token and always require a cancellation-safe confirmation. Keyboard
focus must remain visible with the focus token, including lists, buttons and
inputs.

## Do's and Don'ts

- Do use semantic tokens from the active theme document.
- Do preserve a dark video stage in every theme.
- Do provide a visible keyboard focus indicator.
- Do use text or an icon in addition to status color.
- Do not introduce raw colors in feature widgets.
- Do not use unsupported web-only effects in Qt stylesheets.
- Do not make destructive confirmation default to the destructive choice.
